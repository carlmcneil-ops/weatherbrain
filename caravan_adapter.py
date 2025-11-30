from __future__ import annotations

from typing import Dict, Any, List
from datetime import datetime
from collections import defaultdict

from caravan_regions import CARAVAN_REGIONS
from caravan_engine import find_best_caravan_windows


def _iso_date(dt: datetime) -> str:
    return dt.date().isoformat()


def build_caravan_daily_forecast(raw_weather: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Take the raw_weather blob from ForecastResponse and turn it into
    the simple daily dicts that caravan_engine expects.

    RETURN SHAPE:
    {
        "benmore_mackenzie": [
            {
                "date": "2025-12-01",
                "tow_wind": 15.0,
                "tow_gust": 25.0,
                "camp_wind": 8.0,
                "camp_rain": 1.5,
                "camp_rain_prev48": 5.0,
                "tow_dir": "NW",
                "camp_dir": "NW",
                "tow_kn": 15.0,
                "camp_kn": 8.0,
            },
            ...
        ],
        "waikaia_five_rivers": [...],
        ...
    }

    ⚠️ YOU / YOUR DEV ONLY NEED TO EDIT THE BIT THAT READS FIELDS FROM raw_weather.
    Everything else can stay as-is.
    """

    # For now we assume raw_weather has something like:
    # {
    #   "hours": [
    #       {
    #           "time": "2025-12-01T06:00:00Z",
    #           "wind_kn": 12.3,
    #           "wind_gust_kn": 20.1,
    #           "wind_dir": "NW",
    #           "rain_mm": 0.4,
    #           "region_id": "benmore_mackenzie"  # or similar tag
    #       },
    #       ...
    #   ]
    # }
    #
    # If your real structure is different, only this loop needs changing.

    hours: List[Dict[str, Any]] = raw_weather.get("hours", [])

    # buckets[region_id][date] -> list of hourly points
    buckets: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for h in hours:
        # TODO: match these keys to YOUR real raw_weather keys
        # If names differ, just change them here.
        region_id = h.get("region_id")
        if not region_id:
            # if you don't tag by region yet, you can just dump everything into one region
            # or use lat/lon here later
            continue

        time_str = h.get("time")
        if not time_str:
            continue

        try:
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except Exception:
            continue

        date_key = _iso_date(dt)
        buckets[region_id][date_key].append(h)

    # Now aggregate per region per day into the compact caravan day dicts
    result: Dict[str, List[Dict[str, Any]]] = {}

    for region in CARAVAN_REGIONS:
        rid = region["id"]
        if rid not in buckets:
            continue

        day_map = buckets[rid]
        day_list: List[Dict[str, Any]] = []

        for date_key, points in sorted(day_map.items()):
            if not points:
                continue

            # Simple averages / sums. Tweak later if needed.
            wind_vals = [p.get("wind_kn", 0.0) for p in points]
            gust_vals = [p.get("wind_gust_kn", p.get("gust_kn", 0.0)) for p in points]
            rain_vals = [p.get("rain_mm", 0.0) for p in points]

            avg_wind = sum(wind_vals) / len(wind_vals) if wind_vals else 0.0
            max_gust = max(gust_vals) if gust_vals else 0.0
            rain_24 = sum(rain_vals)

            # Take the most common dir that day
            dirs = [p.get("wind_dir") for p in points if p.get("wind_dir")]
            dir_text = dirs[0] if dirs else ""

            # For now we use tow & camp the same; later we can split “highway” vs “camp” if you like
            day_list.append(
                {
                    "date": date_key,
                    "tow_wind": avg_wind,
                    "tow_gust": max_gust,
                    "camp_wind": avg_wind,
                    "camp_rain": rain_24,
                    "camp_rain_prev48": 0.0,  # TODO: roll 48h if you care
                    "tow_dir": dir_text,
                    "camp_dir": dir_text,
                    "tow_kn": avg_wind,
                    "camp_kn": avg_wind,
                }
            )

        result[rid] = sorted(day_list, key=lambda d: d["date"])

    return result


def compute_caravan_windows_from_raw(raw_weather: Dict[str, Any],
                                     min_nights: int = 2) -> Dict[str, Any]:
    """
    Glue function:
    - takes raw_weather from ForecastResponse,
    - builds daily caravan forecast,
    - runs the caravan engine,
    - returns a nice dict ready for the API.
    """
    from caravan_regions import CARAVAN_REGIONS  # local import to avoid cycles

    forecast_by_region = build_caravan_daily_forecast(raw_weather)
    windows = find_best_caravan_windows(
        regions=CARAVAN_REGIONS,
        forecast_by_region=forecast_by_region,
        min_nights=min_nights,
    )

    # Text snippets like we tested
    texts: List[str] = []
    for w in windows:
        region_name = w["region_name"]
        start = w["start_date"]
        end = w["end_date"]
        nights = w["nights"]
        days = w["days"]

        first = days[0]
        notes = ", ".join(n for n in first.notes if n)

        tow_dir = getattr(first, "tow_dir", "")
        tow_kn = getattr(first, "tow_kn", 0)
        camp_dir = getattr(first, "camp_dir", "")
        camp_kn = getattr(first, "camp_kn", 0)

        text = (
            f"{region_name} – {nights} nights look mint\n"
            f"{notes}.\n"
            f"Tow: {tow_dir} {round(tow_kn)} kn.\n"
            f"Camp: {camp_dir} {round(camp_kn)} kn."
        )
        texts.append(text)

    return {
        "windows": windows,
        "summary_text": "\n----------------------------------------\n".join(texts),
    }