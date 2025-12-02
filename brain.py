"""
brain.py

Core scoring engine for WeatherBrain 2.0.

This module will become the single place where we:
- take normalised daily weather
- apply region + activity profiles
- produce scored days and multi-day windows

Right now nothing imports this file yet.
We will hook it into app.py in a later step.
"""

from typing import Dict, Any, List, Optional

from region_profiles import REGION_PROFILES


DayWeather = Dict[str, Any]


def _label_from_score(score: float) -> str:
    """Map a 0–100 score to a simple label."""
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 55:
        return "ok"
    if score >= 40:
        return "marginal"
    return "no-go"


def _score_simple_bands(value: float, bands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score a single numeric value against simple bands with 'max' threshold.

    Returns the band dict plus a 'score' key.
    """
    chosen = None
    for band in bands:
        max_v = band.get("max", None)
        if max_v is None:
            # If a band forgot 'max', just skip it.
            continue
        if value <= float(max_v):
            chosen = band
            break

    if chosen is None and bands:
        chosen = bands[-1]

    if chosen is None:
        return {"score": 50, "label": "unknown", "description": "No band matched."}

    return {
        "score": float(chosen.get("score", 50)),
        "label": chosen.get("label", "unknown"),
        "description": chosen.get("description", ""),
    }


def _score_temp_bands(temp_min: float, temp_max: float, bands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score temperature using min/max bands.

    We look for a band where the range overlaps sensibly with the day's range.
    If none found, we fallback to the band whose midpoint is closest to the avg temp.
    """
    avg = (float(temp_min) + float(temp_max)) / 2.0
    candidates: List[Dict[str, Any]] = []
    for band in bands:
        b_min = float(band.get("min", -999))
        b_max = float(band.get("max", 999))
        # Overlap if avg is within the band.
        if b_min <= avg <= b_max:
            candidates.append(band)

    chosen = candidates[0] if candidates else None

    if chosen is None and bands:
        # Fallback: closest midpoint
        best_band = None
        best_delta = None
        for band in bands:
            b_min = float(band.get("min", -999))
            b_max = float(band.get("max", 999))
            mid = (b_min + b_max) / 2.0
            delta = abs(mid - avg)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_band = band
        chosen = best_band

    if chosen is None:
        return {"score": 50, "label": "unknown", "description": "No temp band matched."}

    return {
        "score": float(chosen.get("score", 50)),
        "label": chosen.get("label", "unknown"),
        "description": chosen.get("description", ""),
    }


def _score_wind_bands(wind_kmh: float, gust_kmh: float, bands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Score wind/gust using 'wind_bands'.

    We pick the first band whose max_wind and max_gust both cover the values.
    If none match, we fall back to the last band.
    """
    chosen = None
    for band in bands:
        max_wind = float(band.get("max_wind", 999))
        max_gust = float(band.get("max_gust", 999))
        if wind_kmh <= max_wind and gust_kmh <= max_gust:
            chosen = band
            break

    if chosen is None and bands:
        chosen = bands[-1]

    if chosen is None:
        return {"score": 50, "label": "unknown", "description": "No wind band matched."}

    return {
        "score": float(chosen.get("score", 50)),
        "label": chosen.get("label", "unknown"),
        "description": chosen.get("description", ""),
    }


def score_day(region_id: str, activity_id: str, day: DayWeather) -> Dict[str, Any]:
    """Score a single day for a given region + activity profile.

    Expects 'day' to have at least:
      - date (str)
      - wind_kmh (float)
      - gust_kmh (float)
      - rain_mm (float)
      - temp_min (float)
      - temp_max (float)
    Extra fields are passed through in 'raw'.
    """
    region = REGION_PROFILES.get(region_id)
    if region is None:
        raise ValueError(f"Unknown region_id: {region_id}")

    activities = region.get("activities", {})
    profile = activities.get(activity_id)
    if profile is None:
        raise ValueError(f"Unknown activity_id '{activity_id}' for region '{region_id}'")

    weights = profile.get("weights", {})
    wind_weight = float(weights.get("wind", 0.0))
    rain_weight = float(weights.get("rain", 0.0))
    temp_weight = float(weights.get("temp", 0.0))
    cloud_weight = float(weights.get("cloud", 0.0))
    flow_weight = float(weights.get("flow", 0.0))

    total_weight = wind_weight + rain_weight + temp_weight + cloud_weight + flow_weight
    if total_weight <= 0:
        total_weight = 1.0

    # ---- Individual components ----
    wind_info = _score_wind_bands(
        float(day.get("wind_kmh", 0.0)),
        float(day.get("gust_kmh", 0.0)),
        profile.get("wind_bands", []),
    )

    rain_info = _score_simple_bands(
        float(day.get("rain_mm", 0.0)),
        profile.get("rain_bands", []),
    )

    # temp bands expect a min + max; if missing, we fudge a bit
    t_min = day.get("temp_min", day.get("temp_c", 0.0))
    t_max = day.get("temp_max", day.get("temp_c", t_min))
    temp_info = _score_temp_bands(
        float(t_min),
        float(t_max),
        profile.get("temp_bands", []),
    )

    # Optional flow (for rivers)
    flow_info = None
    if flow_weight > 0 and "flow_bands" in profile:
        flow_value = float(day.get("river_flow", day.get("flow", 0.0)))
        flow_info = _score_simple_bands(flow_value, profile.get("flow_bands", []))

    # We ignore cloud for now (no bands defined yet), but keep the slot open.
    cloud_info = None  # placeholder for future use

    # ---- Combine into a single score ----
    component_scores = []
    if wind_weight > 0:
        component_scores.append((wind_info["score"], wind_weight))
    if rain_weight > 0:
        component_scores.append((rain_info["score"], rain_weight))
    if temp_weight > 0:
        component_scores.append((temp_info["score"], temp_weight))
    if flow_info is not None and flow_weight > 0:
        component_scores.append((flow_info["score"], flow_weight))

    if component_scores:
        weighted_sum = sum(score * w for score, w in component_scores)
        applied_weight = sum(w for _, w in component_scores)
        final_score = weighted_sum / applied_weight
    else:
        final_score = 50.0

    label = _label_from_score(final_score)

    reasons: Dict[str, Any] = {
        "wind": wind_info,
        "rain": rain_info,
        "temp": temp_info,
    }
    if flow_info is not None:
        reasons["flow"] = flow_info

    return {
        "date": day.get("date"),
        "score": round(final_score),
        "label": label,
        "reasons": reasons,
        "raw": day,
    }


def _find_windows(
    days: List[Dict[str, Any]],
    min_score: float,
    min_length: int,
) -> List[Dict[str, Any]]:
    """Find contiguous windows where score >= min_score for at least min_length days."""
    windows: List[Dict[str, Any]] = []
    start_idx: Optional[int] = None

    for i, d in enumerate(days):
        if d.get("score", 0) >= min_score:
            if start_idx is None:
                start_idx = i
        else:
            if start_idx is not None:
                length = i - start_idx
                if length >= min_length:
                    window_days = days[start_idx:i]
                    avg_score = sum(dd["score"] for dd in window_days) / length
                    windows.append(
                        {
                            "start_date": window_days[0]["date"],
                            "end_date": window_days[-1]["date"],
                            "length": length,
                            "avg_score": avg_score,
                        }
                    )
                start_idx = None

    # Trailing window at end
    if start_idx is not None:
        length = len(days) - start_idx
        if length >= min_length:
            window_days = days[start_idx:]
            avg_score = sum(dd["score"] for dd in window_days) / length
            windows.append(
                {
                    "start_date": window_days[0]["date"],
                    "end_date": window_days[-1]["date"],
                    "length": length,
                    "avg_score": avg_score,
                }
            )

    return windows


def _choose_best_window(windows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Pick the best window; for now, longest length then highest avg_score."""
    if not windows:
        return None

    # Sort by (length desc, avg_score desc)
    sorted_windows = sorted(
        windows,
        key=lambda w: (w.get("length", 0), w.get("avg_score", 0.0)),
        reverse=True,
    )
    return sorted_windows[0]


def score_period(
    region_id: str,
    activity_id: str,
    days: List[DayWeather],
) -> Dict[str, Any]:
    """Score a period of days for a given region + activity.

    This is the function the UI / API will eventually call.

    Returns:
        {
          "days": [...],
          "windows": [...],
          "best_window": {...} or None,
          "expedition_verdict": "go" | "maybe-go" | "no-window",
        }
    """
    region = REGION_PROFILES.get(region_id)
    if region is None:
        raise ValueError(f"Unknown region_id: {region_id}")

    activities = region.get("activities", {})
    profile = activities.get(activity_id)
    if profile is None:
        raise ValueError(f"Unknown activity_id '{activity_id}' for region '{region_id}'")

    window_logic = profile.get("window_logic", {})
    min_score_for_good = float(window_logic.get("min_score_for_good", 70))
    min_window_length = int(window_logic.get("min_window_length", 1))
    min_good_days = int(window_logic.get("min_good_days", min_window_length))

    # Score each day
    scored_days: List[Dict[str, Any]] = [score_day(region_id, activity_id, d) for d in days]

    # Find good windows
    windows = _find_windows(scored_days, min_score_for_good, min_window_length)
    best_window = _choose_best_window(windows)

    # Expedition verdict: simple for now, we can make this smarter later.
    if best_window is None:
        verdict = "no-window"
    else:
        length = best_window.get("length", 0)
        avg_score = float(best_window.get("avg_score", 0.0))
        if length >= min_good_days and avg_score >= (min_score_for_good + 10):
            verdict = "go"
        else:
            verdict = "maybe-go"

    return {
        "days": scored_days,
        "windows": windows,
        "best_window": best_window,
        "expedition_verdict": verdict,
    }