"""
Caravan scoring engine.

Regions come from caravan_regions.CARAVAN_REGIONS as simple dicts:
    { "id": "benmore_mackenzie", "name": "Benmore / Mackenzie", ... }

A "day" dict is expected to look like:
{
    "date": "2025-12-01",
    "tow_wind": 12.0,           # km/h along the main highway
    "tow_gust": 25.0,           # km/h gusts along the route
    "camp_wind": 8.0,           # km/h at camp in the evening
    "camp_rain": 0.5,           # mm in the coming 24h at camp
    "camp_rain_prev48": 5.0,    # mm in the *previous* 48h at camp
    "overnight_low": 8.0,       # °C (ignored for now – you said no temp)
}
"""

from __future__ import annotations

from typing import Dict, List, Any
from dataclasses import dataclass

from caravan_regions import CARAVAN_REGIONS


# -----------------------------
# Data structures
# -----------------------------

@dataclass
class CaravanDayScore:
    date: str
    region_id: str
    score: float
    tow_ok: bool
    camp_ok: bool
    notes: List[str]


# -----------------------------
# Scoring helpers
# -----------------------------

def _score_towing(tow_wind: float, tow_gust: float) -> (float, bool, List[str]):
    """
    Score towing comfort/safety.

    Very simple for now – units assumed km/h.
    """
    score = 0.0
    ok = True
    notes: List[str] = []

    # Base wind (steady)
    if tow_wind <= 20:
        score += 20
        notes.append("Towing: light winds")
    elif tow_wind <= 35:
        score += 10
        notes.append("Towing: moderate winds")
    elif tow_wind <= 45:
        score -= 10
        notes.append("Towing: fresh and a bit pushy")
    else:
        score -= 30
        ok = False
        notes.append("Towing: strong winds – not fun with a van")

    # Gusts
    if tow_gust <= 30:
        score += 10
        notes.append("Gusts: mild")
    elif tow_gust <= 50:
        notes.append("Gusts: noticeable")
    else:
        score -= 25
        ok = False
        notes.append("Gusts: severe")

    return score, ok, notes


def _score_camping(
    wind: float,
    rain: float,
    rain_prev48: float,
) -> (float, bool, List[str]):
    """
    Score how pleasant camping is.

    Per your call: we ignore temperature, just wind + wetness.
    """
    score = 0.0
    ok = True
    notes: List[str] = []

    # Wind at camp
    if wind <= 15:
        score += 20
        notes.append("Camp: light breeze")
    elif wind <= 30:
        score += 5
        notes.append("Camp: breezy but okay")
    else:
        score -= 20
        ok = False
        notes.append("Camp: very windy, not pleasant")

    # Rain in next 24h
    if rain < 1:
        score += 15
        notes.append("Camp: basically dry")
    elif rain < 5:
        score += 5
        notes.append("Camp: odd shower")
    elif rain < 15:
        notes.append("Camp: on/off showers")
    else:
        score -= 25
        ok = False
        notes.append("Camp: proper rain on the cards")

    # Last 48h – mud/bog factor
    if rain_prev48 < 5:
        score += 5
        notes.append("Ground: reasonably dry")
    elif rain_prev48 < 20:
        notes.append("Ground: could be soft")
    else:
        score -= 10
        notes.append("Ground: likely muddy")

    return score, ok, notes


# -----------------------------
# Public API
# -----------------------------

def score_caravan_day(region: Dict[str, Any], day: Dict[str, Any]) -> CaravanDayScore:
    """
    Score a single day for a given caravan region.

    `region` is a dict from CARAVAN_REGIONS.
    `day` is a dict with the forecast-like fields described at the top.
    """
    region_id = region["id"]

    tow_score, tow_ok, tow_notes = _score_towing(
        tow_wind=day.get("tow_wind", 0.0),
        tow_gust=day.get("tow_gust", 0.0),
    )
    camp_score, camp_ok, camp_notes = _score_camping(
        wind=day.get("camp_wind", 0.0),
        rain=day.get("camp_rain", 0.0),
        rain_prev48=day.get("camp_rain_prev48", 0.0),
    )

    total = 50.0 + tow_score + camp_score  # baseline 50 so it doesn't sit negative all the time

    return CaravanDayScore(
        date=day["date"],
        region_id=region_id,
        score=total,
        tow_ok=tow_ok,
        camp_ok=camp_ok,
        notes=tow_notes + camp_notes,
    )


def find_best_caravan_windows(
    regions: List[Dict[str, Any]],
    forecast_by_region: Dict[str, List[Dict[str, Any]]],
    min_nights: int = 2,
    max_gap_days: int = 0,
) -> List[Dict[str, Any]]:
    """
    Given:
      - regions: list of region dicts (from CARAVAN_REGIONS)
      - forecast_by_region: { region_id: [day1_dict, day2_dict, ...] }

    Return a list of "windows" like:
      {
        "region_id": "...",
        "region_name": "...",
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD",
        "nights": 3,
        "avg_score": 82.5,
        "days": [CaravanDayScore, ...]
      }

    Simple algorithm:
    - score each day
    - keep runs of consecutive camp_ok + tow_ok days
    - only return runs with length >= min_nights
    - max_gap_days reserved for later if we want gaps inside a window.
    """
    windows: List[Dict[str, Any]] = []

    # name lookup
    region_name_by_id = {r["id"]: r["name"] for r in CARAVAN_REGIONS}

    for region in regions:
        rid = region["id"]
        days = forecast_by_region.get(rid, [])
        if not days:
            continue

        scored: List[CaravanDayScore] = [
            score_caravan_day(region, d) for d in days
        ]

        current_run: List[CaravanDayScore] = []

        def flush_run():
            nonlocal current_run, windows
            if len(current_run) >= min_nights:
                avg_score = sum(d.score for d in current_run) / len(current_run)
                windows.append(
                    {
                        "region_id": rid,
                        "region_name": region_name_by_id.get(rid, rid),
                        "start_date": current_run[0].date,
                        "end_date": current_run[-1].date,
                        "nights": len(current_run),
                        "avg_score": avg_score,
                        "days": current_run[:],
                    }
                )
            current_run = []

        for ds in scored:
            if ds.camp_ok and ds.tow_ok:
                current_run.append(ds)
            else:
                flush_run()

        flush_run()

    windows.sort(key=lambda w: w["avg_score"], reverse=True)
    return windows