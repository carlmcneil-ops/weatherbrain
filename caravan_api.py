# caravan_api.py
#
# Caravan trip endpoint:
# - uses Open-Meteo daily data
# - adapts it into the shape caravan_engine expects
# - returns JSON with caravan windows & scored days

from typing import Dict, Any, List
import httpx
from fastapi import APIRouter, HTTPException

from caravan_engine import find_best_caravan_windows
from caravan_regions import CARAVAN_REGIONS
from caravan_text import summarise_window
from scoring_config import get_activity_thresholds

router = APIRouter()

CARAVAN_REGION_ID = "caravan_mode"
CARAVAN_ACTIVITY_ID = "general_caravan"


def _get_caravan_thresholds() -> Dict[str, int]:
    """
    Fetch caravan thresholds from the admin config.

    For now we only actually *use* window_min_length.
    go_threshold / maybe_threshold are parked for later.
    """
    return get_activity_thresholds(CARAVAN_REGION_ID, CARAVAN_ACTIVITY_ID)


async def _fetch_daily_for_region(region: Dict[str, Any], days: int) -> Dict[str, Any]:
    """
    Fetch daily weather for a caravan region using Open-Meteo.
    """
    lat = region["lat"]
    lon = region["lon"]
    timezone = region.get("timezone", "Pacific/Auckland")

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "windspeed_10m_max,windgusts_10m_max"
        ),
        "forecast_days": days,
        "timezone": timezone,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Weather API error for region {region['id']} ({resp.status_code})",
            )
        return resp.json().get("daily", {})


def _build_caravan_days(daily: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    """
    Adapt Open-Meteo 'daily' block into the caravan day shape that
    caravan_engine.score_caravan_day expects.
    """
    times = daily.get("time", [])
    winds = daily.get("windspeed_10m_max", [])
    gusts = daily.get("windgusts_10m_max", [])
    rain = daily.get("precipitation_sum", [])

    days: List[Dict[str, Any]] = []

    for i, date_str in enumerate(times):
        try:
            w = float(winds[i])
            g = float(gusts[i])
            r = float(rain[i])
        except (IndexError, ValueError, TypeError):
            continue

        prev_1 = float(rain[i - 1]) if i - 1 >= 0 else 0.0
        prev_2 = float(rain[i - 2]) if i - 2 >= 0 else 0.0
        prev48 = prev_1 + prev_2

        days.append(
            {
                "date": date_str,
                "tow_wind": w,
                "tow_gust": g,
                "camp_wind": w,
                "camp_rain": r,
                "camp_rain_prev48": prev48,
                # directions can be wired in later
            }
        )

    return days


def _serialise_window(window: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert CaravanDayScore objects inside a window into plain dicts
    so FastAPI / JSON can serialise them.
    """
    days_out: List[Dict[str, Any]] = []
    for d in window.get("days", []):
        days_out.append(
            {
                "date": d.date,
                "region_id": d.region_id,
                "score": d.score,
                "tow_ok": d.tow_ok,
                "camp_ok": d.camp_ok,
                "notes": d.notes,
            }
        )

    return {
        "region_id": window["region_id"],
        "region_name": window["region_name"],
        "start_date": window["start_date"],
        "end_date": window["end_date"],
        "nights": window["nights"],
        "avg_score": window["avg_score"],
        "days": days_out,
    }


@router.get("/api/caravan")
async def caravan_endpoint(days: int = 7, min_nights: int = 2):
    """
    Main caravan endpoint:
      1. For each caravan region → fetch a multi-day forecast
      2. Adapt to caravan day dicts
      3. Run caravan_engine.find_best_caravan_windows
      4. Return JSON-ready windows
    """
    if days < 1 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 1 and 10")

    # Always take min nights from admin config so you can tune it there.
    cfg = _get_caravan_thresholds()
    min_nights = int(cfg.get("window_min_length", 2))

    forecast_by_region: Dict[str, List[Dict[str, Any]]] = {}

    for region in CARAVAN_REGIONS:
        rid = region["id"]
        daily = await _fetch_daily_for_region(region, days)
        forecast_by_region[rid] = _build_caravan_days(daily)

    raw_windows = find_best_caravan_windows(
        regions=CARAVAN_REGIONS,
        forecast_by_region=forecast_by_region,
        min_nights=min_nights,
    )

    windows = [_serialise_window(w) for w in raw_windows]

    return {
        "days_considered": days,
        "min_nights": min_nights,
        "region_count": len(CARAVAN_REGIONS),
        "windows": windows,
    }
    
@router.get("/api/caravan_text")
async def caravan_text(days: int = 7, min_nights: int = 2):
    """
    Convenience endpoint that returns a human-readable summary
    of the best caravan window, plus the underlying windows.
    """
    # Re-use the main caravan endpoint so behaviour stays consistent.
    base = await caravan_endpoint(days=days, min_nights=min_nights)

    windows = base.get("windows", [])
    if not windows:
        return {
            "days_considered": base.get("days_considered", days),
            "min_nights": base.get("min_nights", min_nights),
            "region_count": base.get("region_count", 0),
            "summary": "No suitable caravan windows found.",
            "best_window": None,
            "windows": [],
        }

    best = windows[0]
    summary_text = summarise_window(best)

    return {
        "days_considered": base.get("days_considered", days),
        "min_nights": base.get("min_nights", min_nights),
        "region_count": base.get("region_count", len(windows)),
        "summary": summary_text,
        "best_window": best,
        "windows": windows,
    }

    return {
        "days_considered": days,
        "min_nights": min_nights,
        "region_count": base.get("region_count", len(windows)),
        "summary": summary_text,
        "best_window": best,
        "windows": windows,
    }
