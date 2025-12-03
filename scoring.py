# scoring.py
#
# Pure scoring logic for boating days, Moana on Te Anau, and Waikaia trips.
# No FastAPI / HTTP here – just numbers in, scores out.

from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# Generic boating scoring (used for fizzboat / generic lake logic)
# ---------------------------------------------------------------------------

def score_boating_day(wind_kmh: float, gust_kmh: float, rain_mm: float) -> Dict[str, Any]:
    """
    Score a single day for general boating (fizzboat / generic lake).

    Returns:
        {
            "score": int 0–100,
            "label": "excellent" | "good" | "ok" | "marginal" | "no-go",
            "reason": short string
        }
    """
    # Very calm – basically glassy lake conditions.
    if wind_kmh <= 9 and gust_kmh <= 15 and rain_mm <= 1:
        return {
            "score": 95,
            "label": "excellent",
            "reason": "Very light winds and almost no rain – ideal boating conditions.",
        }

    # Still good, maybe a touch breezier, but nothing scary.
    if wind_kmh <= 15 and gust_kmh <= 25 and rain_mm <= 3:
        return {
            "score": 80,
            "label": "good",
            "reason": "Generally light to moderate winds with only small amounts of rain.",
        }

    # Usable but not special – you’d go if you were keen, not if you were fussy.
    if wind_kmh <= 20 and gust_kmh <= 30 and rain_mm <= 5:
        return {
            "score": 60,
            "label": "ok",
            "reason": "Moderate breeze and/or some rain – workable but not especially pleasant.",
        }

    # Starting to get into “only if you have to move the boat” territory.
    if wind_kmh <= 25 and gust_kmh <= 35 and rain_mm <= 8:
        return {
            "score": 40,
            "label": "marginal",
            "reason": "Fresh winds or steady rain – possible but not recommended for a relaxed trip.",
        }

    # Above this, we just call it off.
    return {
        "score": 10,
        "label": "no-go",
        "reason": "Strong winds and/or significant rain – not worth taking the boat out.",
    }


def build_boating_day_summaries(daily: Dict[str, List[float]]) -> List[Dict[str, Any]]:
    """
    Take the 'daily' block from the Open-Meteo response and return
    a list of per-day boating summaries with scores (generic boating).
    """
    times = daily.get("time", [])
    winds = daily.get("windspeed_10m_max", [])
    gusts = daily.get("windgusts_10m_max", [])
    rain = daily.get("precipitation_sum", [])

    out: List[Dict[str, Any]] = []

    for i, date_str in enumerate(times):
        # Defensive: if arrays are jagged, skip bad indices
        try:
            w = float(winds[i])
            g = float(gusts[i])
            r = float(rain[i])
        except (IndexError, ValueError):
            continue

        score_result = score_boating_day(w, g, r)
        out.append(
            {
                "date": date_str,
                "wind_kmh": w,
                "gust_kmh": g,
                "rain_mm": r,
                "score": score_result["score"],
                "label": score_result["label"],
                "reason": score_result["reason"],
            }
        )

    return out


# ---------------------------------------------------------------------------
# Multi-day window search (shared helper)
# ---------------------------------------------------------------------------

def find_multi_day_windows(
    days: List[Dict[str, Any]],
    min_length: int = 2,
    min_label: str = "good",
) -> List[Dict[str, Any]]:
    """
    Find runs of consecutive days that meet or exceed a given label.

    For Te Anau / Hunter, you care about 2–3 day windows where conditions are 'good' or better.
    """
    label_rank = {
        "no-go": 0,
        "marginal": 1,
        "ok": 2,
        "good": 3,
        "excellent": 4,
    }
    min_rank = label_rank.get(min_label, 3)

    windows: List[Dict[str, Any]] = []
    start_idx: Optional[int] = None

    for i, day in enumerate(days):
        rank = label_rank.get(day.get("label", ""), 0)
        if rank >= min_rank:
            if start_idx is None:
                start_idx = i
        else:
            if start_idx is not None:
                length = i - start_idx
                if length >= min_length:
                    window_days = days[start_idx:i]
                    avg_score = sum(d["score"] for d in window_days) / length
                    windows.append(
                        {
                            "start_date": window_days[0]["date"],
                            "end_date": window_days[-1]["date"],
                            "length": length,
                            "avg_score": avg_score,
                        }
                    )
                start_idx = None

    # Handle trailing window at end of list
    if start_idx is not None:
        length = len(days) - start_idx
        if length >= min_length:
            window_days = days[start_idx:]
            avg_score = sum(d["score"] for d in window_days) / length
            windows.append(
                {
                    "start_date": window_days[0]["date"],
                    "end_date": window_days[-1]["date"],
                    "length": length,
                    "avg_score": avg_score,
                }
            )

    return windows


def choose_best_window(windows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    From a list of windows (each with start_date, end_date, length, avg_score),
    pick the 'best' one.

    Rules:
      - Prefer longer windows
      - If equal length, prefer higher average score
    """
    if not windows:
        return None

    sorted_windows = sorted(
        windows,
        key=lambda w: (w.get("length", 0), w.get("avg_score", 0.0)),
        reverse=True,
    )
    return sorted_windows[0]


# ---------------------------------------------------------------------------
# Moana / Te Anau-specific scoring
# ---------------------------------------------------------------------------

def score_moana_day(wind_kmh: float, gust_kmh: float, rain_mm: float) -> Dict[str, Any]:
    """
    Scoring specifically for Moana on Lake Te Anau.

    Still conservative, but allows genuinely light-to-moderate days
    to count as 'ok' or 'good' instead of everything being no-go.
    """

    # Absolute no-go: really rough or very wet.
    if wind_kmh >= 22 or gust_kmh >= 55 or rain_mm >= 20:
        return {
            "score": 10,
            "label": "no-go",
            "reason": "Strong winds and/or heavy rain – Te Anau will be ugly and unsafe for relaxed boating in Moana.",
        }

    # Marginal: fresh, lumpy, or quite wet but not completely insane.
    if wind_kmh >= 14 or gust_kmh >= 45 or rain_mm >= 12:
        return {
            "score": 35,
            "label": "marginal",
            "reason": "Fresh winds or steady rain – lumpy lake conditions. Only go if you really need to move the boat.",
        }

    # Good: genuinely gentle conditions.
    if wind_kmh <= 8 and gust_kmh <= 25 and rain_mm <= 5:
        return {
            "score": 85,
            "label": "good",
            "reason": "Light breeze and low rain – nice relaxed cruise for Moana on Lake Te Anau.",
        }

    # OK: anything in between – workable but not hero stuff.
    return {
        "score": 65,
        "label": "ok",
        "reason": "Moderate breeze or a bit of rain – workable for Moana, but expect some chop and movement.",
    }


def build_moana_day_summaries(daily: Dict[str, List[float]]) -> List[Dict[str, Any]]:
    """
    Take the 'daily' block from Open-Meteo and score it using the Moana/Te Anau rules.
    """
    times = daily.get("time", [])
    winds = daily.get("windspeed_10m_max", [])
    gusts = daily.get("windgusts_10m_max", [])
    rain = daily.get("precipitation_sum", [])

    out: List[Dict[str, Any]] = []

    for i, date_str in enumerate(times):
        try:
            w = float(winds[i])
            g = float(gusts[i])
            r = float(rain[i])
        except (IndexError, ValueError):
            continue

        score_result = score_moana_day(w, g, r)
        out.append(
            {
                "date": date_str,
                "wind_kmh": w,
                "gust_kmh": g,
                "rain_mm": r,
                "score": score_result["score"],
                "label": score_result["label"],
                "reason": score_result["reason"],
            }
        )

    return out


# ---------------------------------------------------------------------------
# Waikaia-specific scoring (camping + fishing)
# ---------------------------------------------------------------------------

def score_waikaia_day(wind_kmh: float, rain_mm: float) -> Dict[str, Any]:
    """
    Scoring for Waikaia / Piano Flat.

    - Too wet or too windy ⇒ no-go.
    - Decent weather ⇒ 'good' for camping + river time.
    """
    # Hard "this will be grim"
    if rain_mm >= 20 or wind_kmh >= 40:
        return {
            "score": 10,
            "label": "no-go",
            "reason": "Wet or windy enough that you’ll regret the trip.",
        }

    # Marginal – doable, but you'll be damp / buffeted.
    if rain_mm >= 12 or wind_kmh >= 30:
        return {
            "score": 40,
            "label": "marginal",
            "reason": "Fresh wind or steady rain — campsite will get damp, river visibility drops.",
        }

    # Genuinely decent.
    if rain_mm <= 5 and wind_kmh <= 20:
        return {
            "score": 75,
            "label": "good",
            "reason": "Decent conditions – fine for camping and river time.",
        }

    # In-between “ok but blowing like 40 bastards”.
    return {
        "score": 60,
        "label": "ok",
        "reason": "Moderate breeze or some rain — still workable.",
    }


def build_waikaia_day_summaries(daily: Dict[str, List[float]]) -> List[Dict[str, Any]]:
    """
    Build per-day Waikaia summaries from Open-Meteo daily data.
    (Note: we only care about wind speed and rain here.)
    """
    times = daily.get("time", [])
    winds = daily.get("windspeed_10m_max", [])
    rain = daily.get("precipitation_sum", [])

    out: List[Dict[str, Any]] = []

    for i, date_str in enumerate(times):
        try:
            w = float(winds[i])
            r = float(rain[i])
        except (IndexError, ValueError):
            continue

        score_result = score_waikaia_day(w, r)
        out.append(
            {
                "date": date_str,
                "wind_kmh": w,
                "rain_mm": r,
                "score": score_result["score"],
                "label": score_result["label"],
                "reason": score_result["reason"],
            }
        )

    return out


def evaluate_waikaia_trip(
    days: List[Dict[str, Any]],
    min_length: int = 2,
    min_label: str = "good",
) -> Dict[str, Any]:
    """
    Given a list of Waikaia per-day dicts (from build_waikaia_day_summaries),
    work out if there is a worthwhile multi-day camping/fishing window.
    """
    windows = find_multi_day_windows(days, min_length=min_length, min_label=min_label)
    best_window = choose_best_window(windows)

    if not best_window:
        return {
            "verdict": "no-window",
            "reason": "No multi-day Waikaia window worth camping/fishing.",
            "windows": windows,
            "best_window": None,
        }

    length = best_window["length"]
    start = best_window["start_date"]
    end = best_window["end_date"]
    avg_score = round(best_window["avg_score"])

    # Simple tiering for now
    if length >= 3 and avg_score >= 80:
        verdict = "go"
        reason = (
            f"{length}-day Waikaia window ({start} → {end}) looks excellent "
            f"(avg ~{avg_score}). Great for a proper Waikaia mission."
        )
    else:
        verdict = "maybe-go"
        reason = (
            f"{length}-day Waikaia window ({start} → {end}) looks reasonable "
            f"(avg ~{avg_score}). Worth a crack if you’re keen."
        )

    return {
        "verdict": verdict,
        "reason": reason,
        "windows": windows,
        "best_window": best_window,
    }