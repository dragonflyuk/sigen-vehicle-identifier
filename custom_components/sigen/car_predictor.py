"""Car identification — rule-based logic with nearest-centroid fallback."""
from __future__ import annotations

import math
import logging
from typing import Any

from .const import (
    CAR_ID_GEELY,
    CAR_ID_ZOE,
    CAR_ID_MG,
    LFP_VSOC_THRESHOLD,
    CAPACITY_THRESHOLD_KWH,
    MIN_SOC_DELTA_FOR_CAPACITY,
    MIN_ENERGY_FOR_CAPACITY,
    MIN_V2H_ENERGY_FOR_DV_DE,
    DV_DE_THRESHOLD,
    MIN_TAGGED_SESSIONS_FOR_CENTROID,
    FEATURE_WEIGHTS,
)

_LOGGER = logging.getLogger(__name__)

# Prediction method identifiers
METHOD_LFP = "lfp_fingerprint"
METHOD_CAPACITY = "capacity_estimate"
METHOD_DV_DE = "dv_de"
METHOD_CENTROID = "nearest_centroid"
METHOD_NONE = "insufficient_data"


def predict(
    session: dict[str, Any],
    all_sessions: list[dict[str, Any]],
    cars: dict[str, Any],
) -> tuple[str | None, float, str]:
    """Return (car_id, confidence, method) for the given session.

    Rules are applied in priority order. Nearest-centroid is used as a
    supplementary fallback once enough tagged sessions exist.
    """
    voltage = session.get("initial_voltage", 0.0)
    soc = session.get("initial_soc", 0.0)
    v_soc_ratio = session.get("v_soc_ratio", 0.0)
    delta_soc = session.get("delta_soc", 0.0)
    total_energy = session.get("total_energy_kwh", 0.0)
    estimated_cap = session.get("estimated_capacity_kwh")
    v2h_energy = session.get("v2h_energy_kwh", 0.0)
    dv_de = session.get("dv_de")
    mode = session.get("mode", "unknown")

    # ── Rule 1: LFP fingerprint ──────────────────────────────────────────
    if soc >= 5.0 and soc <= 95.0 and v_soc_ratio > LFP_VSOC_THRESHOLD:
        return (CAR_ID_GEELY, 0.95, METHOD_LFP)

    # ── Rule 2: Capacity estimate (charging or V2H with moving SOC) ──────
    if delta_soc >= MIN_SOC_DELTA_FOR_CAPACITY and total_energy >= MIN_ENERGY_FOR_CAPACITY:
        if estimated_cap is not None:
            confidence = _capacity_confidence(delta_soc)
            if estimated_cap < CAPACITY_THRESHOLD_KWH:
                return (CAR_ID_ZOE, confidence, METHOD_CAPACITY)
            else:
                return (CAR_ID_MG, confidence, METHOD_CAPACITY)

    # ── Rule 3: dV/dE method (V2H, SOC stuck at ~100%) ──────────────────
    if mode == "discharging" and delta_soc <= 1.0 and v2h_energy >= MIN_V2H_ENERGY_FOR_DV_DE:
        if dv_de is not None:
            if dv_de > DV_DE_THRESHOLD:
                return (CAR_ID_ZOE, 0.70, METHOD_DV_DE)
            else:
                return (CAR_ID_MG, 0.70, METHOD_DV_DE)

    # ── Rule 4: Nearest-centroid (requires training data) ────────────────
    centroid_result = _nearest_centroid(session, all_sessions, cars)
    if centroid_result is not None:
        return centroid_result

    return (None, 0.0, METHOD_NONE)


def _capacity_confidence(delta_soc: float) -> float:
    if delta_soc >= 5.0:
        return 0.90
    if delta_soc >= 2.0:
        return 0.75
    return 0.60


def _nearest_centroid(
    session: dict[str, Any],
    all_sessions: list[dict[str, Any]],
    cars: dict[str, Any],
) -> tuple[str, float, str] | None:
    """Apply nearest-centroid classification if enough tagged sessions exist."""
    tagged = [
        s for s in all_sessions
        if s.get("confirmed_car_id") and s.get("confirmed_car_id") in cars
    ]

    # Group by car
    by_car: dict[str, list[dict]] = {}
    for s in tagged:
        cid = s["confirmed_car_id"]
        by_car.setdefault(cid, []).append(s)

    # Need at least 2 cars with enough sessions to classify
    eligible = {cid: ss for cid, ss in by_car.items() if len(ss) >= MIN_TAGGED_SESSIONS_FOR_CENTROID}
    if len(eligible) < 2:
        return None

    current_features = extract_features(session)

    distances: list[tuple[float, str]] = []
    for car_id, sessions in eligible.items():
        centroid = _compute_centroid(sessions)
        dist = _weighted_distance(current_features, centroid)
        distances.append((dist, car_id))

    distances.sort()
    nearest_dist, nearest_car = distances[0]
    second_dist = distances[1][0] if len(distances) > 1 else nearest_dist * 2

    confidence = _confidence_from_distances(nearest_dist, second_dist)
    return (nearest_car, confidence, METHOD_CENTROID)


def extract_features(session: dict[str, Any]) -> dict[str, float | None]:
    return {
        "v_soc_ratio": session.get("v_soc_ratio"),
        "estimated_capacity_kwh": session.get("estimated_capacity_kwh"),
        "initial_voltage": session.get("initial_voltage"),
        "dv_de": session.get("dv_de"),
        "peak_power_kw": session.get("peak_power_kw"),
    }


def _compute_centroid(sessions: list[dict[str, Any]]) -> dict[str, float | None]:
    """Mean feature vector across a set of sessions, ignoring None values."""
    centroid: dict[str, list[float]] = {}
    for s in sessions:
        for key, val in extract_features(s).items():
            if val is not None:
                centroid.setdefault(key, []).append(val)
    return {k: sum(v) / len(v) for k, v in centroid.items()}


def _weighted_distance(a: dict[str, float | None], b: dict[str, float | None]) -> float:
    """Weighted Euclidean distance; skips features missing from either side."""
    total = 0.0
    weight_sum = 0.0
    for key, weight in FEATURE_WEIGHTS.items():
        va = a.get(key)
        vb = b.get(key)
        if va is None or vb is None:
            continue
        # Normalise by expected range to keep features comparable
        norm = _feature_scale(key)
        diff = (va - vb) / norm if norm else (va - vb)
        total += weight * diff * diff
        weight_sum += weight

    if weight_sum == 0:
        return float("inf")
    return math.sqrt(total / weight_sum)


def _feature_scale(key: str) -> float:
    """Rough scale for each feature to normalise distances."""
    scales = {
        "v_soc_ratio": 2.0,
        "estimated_capacity_kwh": 30.0,
        "initial_voltage": 50.0,
        "dv_de": 3.0,
        "peak_power_kw": 50.0,
    }
    return scales.get(key, 1.0)


def _confidence_from_distances(nearest: float, second: float) -> float:
    if nearest == 0:
        return 0.95
    total = nearest + second
    if total == 0:
        return 0.5
    return round(min(0.90, second / total), 2)
