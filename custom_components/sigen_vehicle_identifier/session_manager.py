"""DC charger session lifecycle manager."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from . import car_predictor
from .const import (
    ACTIVE_STATES,
    DEFAULT_CARS,
    DOMAIN,
    END_STATES,
    LOW_CONFIDENCE_THRESHOLD,
    MAX_SESSIONS,
    NOTIFICATION_ID,
    RUNNING_STATE_CHARGING,
    RUNNING_STATE_DISCHARGING,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class DCChargerSessionManager:
    """Manages DC charger session lifecycle, logging, and car prediction."""

    def __init__(self, hass: HomeAssistant, charger_name: str) -> None:
        self._hass = hass
        self._charger_name = charger_name
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cars: dict[str, Any] = {}
        self._sessions: list[dict[str, Any]] = []
        self._current_session: dict[str, Any] | None = None
        self._last_update_time: datetime | None = None
        self._last_state: int | None = None

    # ── Startup / shutdown ────────────────────────────────────────────────

    async def async_load(self) -> None:
        """Load stored car profiles and sessions."""
        data = await self._store.async_load()
        if data is None:
            self._cars = {
                cid: dict(car) | {"created": datetime.now(timezone.utc).isoformat()}
                for cid, car in DEFAULT_CARS.items()
            }
            self._sessions = []
            await self._async_save()
        else:
            self._cars = data.get("cars", {})
            self._sessions = data.get("sessions", [])
            # Add any new default cars that were added in a code update
            for cid, car in DEFAULT_CARS.items():
                if cid not in self._cars:
                    self._cars[cid] = dict(car) | {"created": datetime.now(timezone.utc).isoformat()}

    # ── Main update hook (called by coordinator each poll cycle) ──────────

    async def on_data_update(self, dc_charger_data: dict[str, Any] | None) -> None:
        """Process a fresh DC charger poll result."""
        now = datetime.now(timezone.utc)

        if dc_charger_data is None:
            # Registers threw an exception → no EV connected
            if self._current_session is not None:
                await self._end_session(now)
            self._last_update_time = now
            return

        state = dc_charger_data.get("dc_charger_running_state")

        if state in ACTIVE_STATES:
            if self._current_session is None:
                await self._start_session(dc_charger_data, now)
            else:
                await self._update_session(dc_charger_data, now)
        elif state in END_STATES and self._current_session is not None:
            await self._end_session(now)

        self._last_state = state
        self._last_update_time = now

    # ── Session lifecycle ─────────────────────────────────────────────────

    async def _start_session(self, data: dict[str, Any], now: datetime) -> None:
        voltage = data.get("dc_charger_vehicle_battery_voltage", 0.0)
        soc = data.get("dc_charger_vehicle_soc", 0.0)
        v_soc_ratio = (voltage / soc) if soc and soc > 0 else 0.0

        self._current_session = {
            "session_id": str(uuid.uuid4()),
            "charger_name": self._charger_name,
            "start_time": now.isoformat(),
            "end_time": None,
            "mode": "unknown",
            "initial_voltage": voltage,
            "initial_soc": soc,
            "v_soc_ratio": v_soc_ratio,
            "day_of_week": now.weekday(),
            "hour_of_day": now.hour,
            "timeseries": [],
            # Derived metrics
            "delta_soc": 0.0,
            "total_energy_kwh": 0.0,
            "estimated_capacity_kwh": None,
            "dv_de": None,
            "peak_power_kw": 0.0,
            "peak_current_a": 0.0,
            "avg_power_kw": 0.0,
            "session_duration_s": 0,
            "v2h_energy_kwh": 0.0,
            # Prediction fields
            "predicted_car_id": None,
            "prediction_confidence": None,
            "prediction_method": "insufficient_data",
            "prediction_updated_at": None,
            "confirmed_car_id": None,
            "user_corrected": False,
        }
        self._last_update_time = now

        _LOGGER.debug("DC charger session started: %s", self._current_session["session_id"])

        await self._update_prediction(notify=True)

    async def _update_session(self, data: dict[str, Any], now: datetime) -> None:
        session = self._current_session
        assert session is not None

        dt_seconds = (
            (now - self._last_update_time).total_seconds()
            if self._last_update_time
            else 0.0
        )

        voltage = data.get("dc_charger_vehicle_battery_voltage", 0.0)
        soc = data.get("dc_charger_vehicle_soc", 0.0)
        power_kw = data.get("dc_charger_output_power", 0.0)
        current_a = data.get("dc_charger_charging_current", 0.0)
        charging_cap_kwh = data.get("dc_charger_current_charging_capacity", 0.0)

        # Session duration
        session["session_duration_s"] = int(
            (now - datetime.fromisoformat(session["start_time"])).total_seconds()
        )

        # Mode detection
        if power_kw < -0.05:
            session["mode"] = "discharging"
        elif power_kw > 0.05:
            session["mode"] = "charging"

        # V2H energy integration using real elapsed time
        if power_kw < -0.05:
            session["v2h_energy_kwh"] += abs(power_kw) * dt_seconds / 3600.0

        # Total energy: register tracks charge-only; integrate discharge separately
        if session["mode"] == "discharging":
            session["total_energy_kwh"] = session["v2h_energy_kwh"]
        else:
            session["total_energy_kwh"] = charging_cap_kwh

        # SOC delta (always positive)
        session["delta_soc"] = abs(soc - session["initial_soc"])

        # Capacity estimate
        if session["delta_soc"] > 0 and session["total_energy_kwh"] > 0:
            session["estimated_capacity_kwh"] = session["total_energy_kwh"] / (session["delta_soc"] / 100.0)

        # dV/dE: voltage drop per kWh discharged
        if session["v2h_energy_kwh"] > 0:
            voltage_drop = session["initial_voltage"] - voltage
            session["dv_de"] = voltage_drop / session["v2h_energy_kwh"]

        # Running averages / peaks
        session["peak_power_kw"] = max(session["peak_power_kw"], abs(power_kw))
        session["peak_current_a"] = max(session["peak_current_a"], current_a)
        duration = session["session_duration_s"]
        if duration > 0:
            # Approximate running average using current reading
            session["avg_power_kw"] = session["total_energy_kwh"] / (duration / 3600.0)

        # Append timeseries sample
        elapsed = int((now - datetime.fromisoformat(session["start_time"])).total_seconds())
        session["timeseries"].append({
            "t": elapsed,
            "voltage": voltage,
            "soc": soc,
            "power_kw": power_kw,
            "session_energy_kwh": charging_cap_kwh,
            "v2h_energy_kwh": session["v2h_energy_kwh"],
        })

        await self._update_prediction(notify=True)

    async def _end_session(self, now: datetime) -> None:
        session = self._current_session
        assert session is not None

        session["end_time"] = now.isoformat()

        # Auto-increment car stats for high-confidence, uncontested predictions
        predicted = session.get("predicted_car_id")
        confidence = session.get("prediction_confidence") or 0.0
        if predicted and confidence >= LOW_CONFIDENCE_THRESHOLD and not session.get("confirmed_car_id"):
            car = self._cars.get(predicted)
            if car:
                car["session_count"] += 1
                car["correct_predictions"] += 1

        # Remove timeseries to reduce storage size for old sessions, keeping summary
        session_to_store = {k: v for k, v in session.items() if k != "timeseries"}
        session_to_store["timeseries_samples"] = len(session.get("timeseries", []))

        self._sessions.append(session_to_store)
        if len(self._sessions) > MAX_SESSIONS:
            self._sessions = self._sessions[-MAX_SESSIONS:]

        _LOGGER.debug(
            "DC charger session ended: %s (predicted: %s @ %.0f%%)",
            session["session_id"],
            predicted,
            (confidence or 0) * 100,
        )

        # Notify user if car wasn't confirmed and confidence was low
        if predicted and confidence < LOW_CONFIDENCE_THRESHOLD and not session.get("confirmed_car_id"):
            await self._send_session_end_notification(session)

        self._current_session = None
        await self._async_save()

        # Dismiss in-session notification
        self._hass.async_create_task(
            self._hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": NOTIFICATION_ID},
            )
        )

    # ── Prediction ────────────────────────────────────────────────────────

    async def _update_prediction(self, notify: bool = False) -> None:
        session = self._current_session
        if session is None:
            return

        prev_method = session.get("prediction_method")
        prev_car = session.get("predicted_car_id")

        car_id, confidence, method = car_predictor.predict(
            session, self._sessions, self._cars
        )

        session["predicted_car_id"] = car_id
        session["prediction_confidence"] = confidence
        session["prediction_method"] = method
        session["prediction_updated_at"] = datetime.now(timezone.utc).isoformat()

        # Send notification on first prediction or when method improves
        changed = (car_id != prev_car) or (method != prev_method)
        if notify and changed and car_id:
            if confidence < LOW_CONFIDENCE_THRESHOLD:
                await self._send_low_confidence_notification(car_id, confidence)

    # ── Notifications ─────────────────────────────────────────────────────

    async def _send_low_confidence_notification(self, car_id: str, confidence: float) -> None:
        car_name = self._cars.get(car_id, {}).get("name", car_id)
        car_list = "\n".join(
            f"• **{car['name']}**" for car in self._cars.values()
        )
        await self._hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": NOTIFICATION_ID,
                "title": "DC Charger Session Started",
                "message": (
                    f"Predicted: **{car_name}** ({confidence:.0%} confidence).\n\n"
                    f"To confirm or correct, use the **Car on Charger** select entity "
                    f"or call the `{DOMAIN}.confirm_session_car` service.\n\n"
                    f"Configured cars:\n{car_list}"
                ),
            },
        )

    async def _send_session_end_notification(self, session: dict[str, Any]) -> None:
        car_id = session.get("predicted_car_id")
        car_name = self._cars.get(car_id, {}).get("name", "Unknown") if car_id else "Unknown"
        confidence = session.get("prediction_confidence") or 0.0
        await self._hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": f"{NOTIFICATION_ID}_ended",
                "title": "DC Charger Session Ended — Please Confirm Car",
                "message": (
                    f"Predicted: **{car_name}** ({confidence:.0%} confidence).\n\n"
                    f"Session ID: `{session['session_id']}`\n"
                    f"Call `{DOMAIN}.confirm_session_car` to confirm or correct."
                ),
            },
        )

    # ── Public API ────────────────────────────────────────────────────────

    def get_current_session(self) -> dict[str, Any] | None:
        return self._current_session

    def get_sessions(self) -> list[dict[str, Any]]:
        return self._sessions

    def get_cars(self) -> dict[str, Any]:
        return self._cars

    def get_car_names(self) -> list[str]:
        return [car["name"] for car in self._cars.values()]

    def get_car_id_by_name(self, name: str) -> str | None:
        for cid, car in self._cars.items():
            if car["name"] == name:
                return cid
        return None

    async def async_confirm_car(self, car_id: str, session_id: str | None = None) -> bool:
        """Confirm or correct the car for the current or last session."""
        if car_id not in self._cars:
            _LOGGER.warning("confirm_car: unknown car_id %s", car_id)
            return False

        session: dict[str, Any] | None = None
        if session_id:
            session = next(
                (s for s in self._sessions if s.get("session_id") == session_id), None
            )
        elif self._current_session:
            session = self._current_session
        elif self._sessions:
            session = self._sessions[-1]

        if session is None:
            return False

        old_predicted = session.get("predicted_car_id")
        session["confirmed_car_id"] = car_id
        session["user_corrected"] = car_id != old_predicted

        # Update car stats
        car = self._cars.get(car_id)
        if car:
            car["session_count"] = car.get("session_count", 0) + 1
            if not session["user_corrected"]:
                car["correct_predictions"] = car.get("correct_predictions", 0) + 1

        await self._async_save()

        # Dismiss notifications
        self._hass.async_create_task(
            self._hass.services.async_call(
                "persistent_notification",
                "dismiss",
                {"notification_id": NOTIFICATION_ID},
            )
        )
        return True

    async def async_add_car(self, name: str, color: str) -> str:
        base = name.lower().replace(" ", "_").replace("-", "_")
        car_id = base
        n = 1
        while car_id in self._cars:
            car_id = f"{base}_{n}"
            n += 1
        self._cars[car_id] = {
            "name": name,
            "color": color,
            "created": datetime.now(timezone.utc).isoformat(),
            "session_count": 0,
            "correct_predictions": 0,
        }
        await self._async_save()
        return car_id

    async def async_remove_car(self, car_id: str) -> None:
        self._cars.pop(car_id, None)
        await self._async_save()

    async def async_export_sessions(self, path: str) -> None:
        import json
        data = {
            "cars": self._cars,
            "sessions": self._sessions,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)

    # ── Storage ───────────────────────────────────────────────────────────

    async def _async_save(self) -> None:
        await self._store.async_save({"cars": self._cars, "sessions": self._sessions})
