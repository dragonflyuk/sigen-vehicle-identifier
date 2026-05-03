# Sigen DC Charger — Car Identifier Feature
## Implementation Plan for Claude

---

## Context

This plan describes a new feature to be added to the existing Sigen custom integration located at:
```
custom_components/sigen/
```
on a Home Assistant instance. The integration communicates with a Sigenergy ESS (inverter + battery + DC EV charger) via Modbus TCP at `192.168.1.193:502`.

The goal is to automatically identify which of three known EVs is connected to the DC charger, using only the data exposed by the charger's Modbus registers. The system logs session data, learns from user-tagged sessions, and progressively improves its predictions over time.

---

## The Three Cars

| Car | Chemistry | Capacity | Max DC | Key Trait |
|-----|-----------|----------|--------|-----------|
| Renault Zoe 2022 | NMC | ~52kWh | ~50kW | SOC sticks at 100% during V2H until car is switched on; triggers alarm after ~3kWh V2H discharge |
| MG ZS EV 2022 | NMC | ~77kWh | ~76kW | SOC drops normally in all modes |
| Geely EX5 2026 | **LFP** | ~60kWh | ~80kW | LFP chemistry gives a distinct voltage signature |

**Two drivers use all three cars** — presence detection cannot be used to identify the car.

**No car integrations are available** — Renault, MG, and Geely integrations are all ruled out. Identification must come entirely from DC charger Modbus data.

**No RFID reader** on the charger.

**A second AC-only charger** is also in use. It cannot do V2H. It has no smart monitoring.

---

## DC Charger Modbus Registers

Connection: `192.168.1.193:502`, slave ID `1` (shared with inverter).

All registers return Modbus Exception when no EV is connected.

### Running Info — FC04 Read Input Registers

| Address | Integration Key | Type | Gain | Unit | Notes |
|---------|----------------|------|------|------|-------|
| 31500 | `dc_charger_vehicle_battery_voltage` | U16 | ÷10 | V | Pack terminal voltage |
| 31501 | `dc_charger_charging_current` | U16 | ÷10 | A | Always positive |
| 31502–31503 | `dc_charger_output_power` | **S32** | ÷1000 | kW | **Negative during V2H** |
| 31504 | `dc_charger_vehicle_soc` | U16 | ÷10 | % | May stick at 100 for Zoe during V2H |
| 31505–31506 | `dc_charger_current_charging_capacity` | U32 | ÷100 | kWh | Session energy delivered TO car; does not track V2H discharge |
| 31507–31508 | `dc_charger_current_charging_duration` | U32 | ÷1 | s | Session duration |
| 31513 | `dc_charger_running_state` | U16 | — | enum | See states below |

### Parameter Register — FC03 Read Holding

| Address | Key | Type | Notes |
|---------|-----|------|-------|
| 41000 | `dc_charger_start_stop` | U16 W/O | Write 0=Start, 1=Stop |

### Running State Enum Values

```
IDLE                = 0x00
OCCUPIED            = 0x01
PREPARING_COMM      = 0x02
CHARGING            = 0x03
FAULT               = 0x04
SCHEDULED           = 0x05
ENDED               = 0x06
UNAVAILABLE         = 0x07
DISCHARGING         = 0x08   ← V2H mode
ALARM               = 0x09
PREPARING_INSULATION = 0x0A
```

A session is **active** when state is one of: OCCUPIED, PREPARING_COMM, CHARGING, DISCHARGING, ALARM, PREPARING_INSULATION, SCHEDULED.

A session **ends** when state returns to IDLE, ENDED, FAULT, or UNAVAILABLE.

---

## Identification Algorithm

### Key Physics

**LFP vs NMC voltage signature** (strongest discriminator):

LFP cells hold ~3.2V/cell flat across 20–80% SOC. NMC cells slope from ~3.3V to ~4.0V/cell. For a ~400V pack this means at mid-SOC:
- NMC cars (Zoe, MG): `battery_voltage / soc` ≈ **6.8–7.4**
- LFP car (Geely): `battery_voltage / soc` ≈ **7.8–8.4**

Threshold `7.6` reliably separates them. This works at any SOC between ~20–80% in both charging and V2H modes.

**Battery capacity estimate** (separates Zoe from MG):

```
estimated_capacity_kwh = energy_exchanged_kwh / (delta_soc / 100)
```
- ~50kWh → Renault Zoe
- ~60kWh → Geely EX5 (backup, LFP fingerprint is primary)
- ~77kWh → MG ZS EV

**V2H energy tracking**: `dc_charger_output_power` is negative during V2H and `dc_charger_current_charging_capacity` does not accumulate. Energy discharged must be computed by integrating `|output_power| × dt` independently.

**Zoe stuck-at-100% SOC during V2H**: When Zoe starts V2H at exactly 100% SOC, the BMS reports 100% throughout (until car is turned on). The Zoe triggers a charger alarm at ~3kWh discharged. At 2–3kW discharge rate, this is 60–90 minutes. Use `dV/dE` (voltage drop per kWh) instead of capacity estimate:
- Zoe (50kWh): ~4.2 V/kWh drop
- MG (77kWh): ~1.9 V/kWh drop

At 1kWh discharged (20–30 minutes at 3kW), the difference is detectable.

### Decision Logic

```
On session start (running_state transitions to active):

1. Read initial_voltage (V) and initial_soc (S)

2. If (V / S) > 7.6:
       → GEELY EX5  (LFP fingerprint, instant, high confidence)

3. Else (NMC car — Zoe or MG):
   
   Wait for energy to accumulate...

   If running_state == CHARGING:
       When delta_soc >= 2% AND energy >= 0.5kWh:
           estimated_capacity = energy / (delta_soc / 100)
           If capacity < 63: → ZOE
           If capacity > 63: → MG ZS EV

   If running_state == DISCHARGING (V2H):
       If delta_soc > 1%:
           (SOC is moving — use capacity estimate same as above)
       Else (SOC stuck at 100%):
           When v2h_energy_discharged >= 1.0 kWh:
               dv_de = (initial_voltage - current_voltage) / v2h_energy_discharged
               If dv_de > 2.8:  → ZOE   (faster voltage drop, smaller pack)
               If dv_de < 2.8:  → MG ZS EV

4. Confidence scoring:
   - Clear LFP signal: 95%
   - Capacity estimate with delta_soc >= 5%: 90%
   - Capacity estimate with delta_soc 2–5%: 75%
   - dV/dE method: 70%
   - Insufficient data yet: report "Learning..."
```

### Minimum Training Data

Do not make predictions until at least **2 tagged sessions** exist per car. Until then, prompt user to tag every session.

---

## Data to Log Per Session

### At Connection (T=0)

```python
{
    "session_id": str,           # UUID
    "charger_name": str,         # inverter device name
    "start_time": str,           # ISO8601
    "end_time": str | None,
    "mode": "charging" | "discharging" | "unknown",
    "initial_voltage": float,    # V
    "initial_soc": float,        # %
    "v_soc_ratio": float,        # initial_voltage / initial_soc
    "day_of_week": int,          # 0=Mon
    "hour_of_day": int,
}
```

### Time Series — Every 30 Seconds

```python
{
    "t": int,           # seconds since session start
    "voltage": float,   # V
    "soc": float,       # %
    "power_kw": float,  # signed — negative = V2H
    "session_energy_kwh": float,   # from dc_charger_current_charging_capacity (charge only)
    "v2h_energy_kwh": float,       # accumulated from |power × dt| (discharge only)
}
```

### Derived Metrics — Updated Progressively

```python
{
    "delta_soc": float,                  # SOC change since start
    "total_energy_kwh": float,           # charging or V2H energy
    "kwh_per_0.1_soc": float,           # total_energy / (delta_soc * 10)
    "estimated_capacity_kwh": float,     # total_energy / (delta_soc / 100)
    "dv_dsoc": float,                    # V per % SOC
    "dv_de": float,                      # V per kWh
    "peak_power_kw": float,
    "peak_current_a": float,
    "avg_power_kw": float,
    "session_duration_s": int,
}
```

### Prediction Fields

```python
{
    "predicted_car_id": str | None,
    "prediction_confidence": float,      # 0.0–1.0
    "prediction_method": str,            # "lfp_fingerprint" | "capacity_estimate" | "dv_de" | "insufficient_data"
    "prediction_updated_at": str,        # ISO8601
    "confirmed_car_id": str | None,      # set by user
    "user_corrected": bool,              # true if confirmed != predicted
}
```

---

## Storage

Two files in HA `.storage/` directory (use `homeassistant.helpers.storage`):

### `sigen_car_profiles` (domain key)

```json
{
    "version": 1,
    "cars": {
        "car_abc123": {
            "name": "Renault Zoe",
            "color": "#FFD700",
            "created": "2026-04-30T10:00:00",
            "session_count": 12,
            "correct_predictions": 10
        }
    }
}
```

### `sigen_sessions` (domain key)

```json
{
    "version": 1,
    "sessions": [
        { ...full session object as above... }
    ]
}
```

Keep last 200 sessions maximum. Sessions are used as training data for the classifier.

---

## New Files to Create

### `custom_components/sigen/car_predictor.py`

Responsibilities:
- `extract_features(session)` — build feature vector from session data
- `predict(session, all_sessions, cars)` → `(car_id, confidence, method)`
- `compute_centroid(sessions_for_car)` — mean feature vector per car
- `weighted_distance(features_a, features_b, weights)` — distance metric
- `confidence_from_distances(nearest, second_nearest)` — score

Feature weights:
```python
FEATURE_WEIGHTS = {
    "v_soc_ratio":              4.0,  # chemistry discriminator
    "estimated_capacity_kwh":   4.0,  # size discriminator
    "initial_voltage":          2.0,
    "dv_de":                    1.5,
    "peak_power_kw":            1.0,
}
```

The predictor should also apply the rule-based logic first (LFP fingerprint, capacity threshold) and fall back to nearest-centroid only when rules are uncertain.

### `custom_components/sigen/session_manager.py`

Responsibilities:
- Detect session start/end from `dc_charger_running_state` changes
- Sample all DC charger registers every 30 seconds during active session
- Accumulate V2H energy from `|output_power × dt|`
- Compute derived metrics progressively
- Trigger prediction updates at key milestones (T=0, 0.5kWh, 1kWh, 2% SOC change)
- Load/save sessions via HA storage
- Expose current session state to coordinator

Key class:
```python
class DCChargerSessionManager:
    def __init__(self, hass, storage, predictor):
        ...

    async def on_data_update(self, dc_charger_data: dict) -> None:
        """Called by coordinator on each poll cycle."""
        ...

    def get_current_session(self) -> dict | None:
        ...

    async def confirm_car(self, car_id: str) -> None:
        """User confirms or corrects car for current/last session."""
        ...
```

---

## Files to Modify

### `coordinator.py`

- Instantiate `DCChargerSessionManager` in `__init__`
- Call `session_manager.on_data_update(dc_charger_data)` after each successful DC charger poll
- Expose `session_manager` as an attribute so entities can read it

### `sensor.py` / `static_sensor.py`

Add to `DC_CHARGER_SENSORS`:

```python
SigenergySensorEntityDescription(
    key="identified_car",
    name="Identified Car",
    icon="mdi:car-electric",
),
SigenergySensorEntityDescription(
    key="prediction_confidence",
    name="Car ID Confidence",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:percent",
    entity_category=EntityCategory.DIAGNOSTIC,
),
SigenergySensorEntityDescription(
    key="session_capacity_estimate",
    name="Session Battery Capacity Estimate",
    device_class=SensorDeviceClass.ENERGY_STORAGE,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    state_class=SensorStateClass.MEASUREMENT,
    icon="mdi:battery-unknown",
    entity_category=EntityCategory.DIAGNOSTIC,
),
SigenergySensorEntityDescription(
    key="session_id",
    name="Session ID",
    icon="mdi:identifier",
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
),
```

These sensors read from `coordinator.session_manager.get_current_session()`.

### `select.py`

Add a new select entity `DC_CHARGER_CAR_SELECTS`:

```python
SigenergySelectEntityDescription(
    key="car_override",
    name="Car on Charger",
    icon="mdi:car-electric",
    # options populated dynamically from car profiles
)
```

When user changes this select, call `coordinator.session_manager.confirm_car(car_id)`.

### `config_flow.py` — Options Flow

Add a new options flow step for car management:
- List existing cars with session count and accuracy
- Add car (name + colour picker)
- Remove car (with confirmation)
- This is separate from the main connection setup flow

### `services.yaml`

```yaml
confirm_session_car:
  name: Confirm Session Car
  description: Confirm or correct the identified car for the current or most recent DC charger session
  fields:
    car_id:
      name: Car ID
      required: true
      selector:
        text:

export_sessions:
  name: Export Session Log
  description: Export all DC charger session data to a JSON file in /homeassistant/
```

---

## Notifications

When a session starts and confidence is below 85%, or when there is insufficient training data, fire a persistent HA notification:

```
Title: "DC Charger Session Started"
Message: "Predicted: Renault Zoe (72% confidence). Correct?"
Actions: [car name buttons for each configured car]
```

Use `hass.components.persistent_notification` or `mobile_app` actionable notifications if available.

---

## Implementation Order

1. **`session_manager.py`** — session lifecycle, 30s sampling, V2H energy accumulation, storage
2. **`car_predictor.py`** — feature extraction, rule-based logic, nearest-centroid fallback
3. **`coordinator.py` changes** — wire session manager in, expose to entities
4. **New sensor entities** — identified car, confidence, capacity estimate, session ID
5. **Car correction select entity** — `select.py`
6. **Options flow** — car profile management
7. **Services** — confirm_session_car, export_sessions
8. **Notifications** — session start prompt when confidence low

---

## Existing Integration Structure (reference)

```
custom_components/sigen/
├── __init__.py
├── manifest.json           version 1.2.0, requires pymodbus>=3.8.3
├── const.py
├── modbus.py               Modbus TCP client, register probing, read/write
├── modbusregisterdefinitions.py   All register definitions
├── coordinator.py          SigenergyDataUpdateCoordinator
├── sensor.py               SigenergySensor, PVStringSensor etc
├── static_sensor.py        SS class with all sensor descriptions
├── calculated_sensor.py    SCS class with derived sensors
├── switch.py               DC_CHARGER_SWITCHES (dc_charging switch uses 41000)
├── number.py               DC_CHARGER_NUMBERS = [] (empty)
├── select.py               DC_CHARGER_SELECTS = [] (empty)
├── binary_sensor.py
├── sigen_entity.py         Base entity class
├── common.py
├── config_flow.py          Multi-step config + options flow
├── diagnostics.py
├── services.yaml
├── strings.json
└── translations/en.json
```

The integration is a single config entry for the whole plant. The DC charger is exposed as a child device of the inverter. DC charger data is fetched by `coordinator.async_read_dc_charger_data(inverter_name)` in `modbus.py` (line 1097).

---

## Key Constraints to Respect

- V2H discharge rate is 2–3kW (system-imposed, not car-limited)
- Zoe alarms after ~3kWh of V2H discharge
- `dc_charger_current_charging_capacity` does NOT track V2H energy — must integrate power
- `dc_charger_output_power` is signed S32 (negative = discharging to home)
- pymodbus version installed: **3.13.0** — API uses `device_id=` kwarg, not `slave=`
- HA path mapping: `/homeassistant` = HA config dir (not `/config`)
- Do not break any existing Sigen integration functionality
- Read-only mode must be respected for write operations (check `read_only` flag before writing)
