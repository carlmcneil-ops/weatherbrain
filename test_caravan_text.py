"""
Small text harness for the caravan engine.

Goal: produce guide-style text like:

Benmore / Mackenzie – 2 nights look mint
Light breeze, basically dry, odd shower, reasonably dry, could be soft.
Tow: NW 10–25 kn — light winds, mild gusts.
Camp: NW 8 kn — light breeze in camp.
"""

from __future__ import annotations

from typing import Dict, List, Any, Optional

from caravan_regions import CARAVAN_REGIONS
from caravan_engine import find_best_caravan_windows, _score_towing, _score_camping


# -----------------------------
# Helpers
# -----------------------------


def to_knots(kph: float) -> int:
    """Rough convert km/h → knots."""
    return int(round(kph / 1.852))  # close enough for humans


def format_knots(steady_kph: float) -> str:
    return f"{to_knots(steady_kph)} kn"


def format_knots_range(steady_kph: float, gust_kph: Optional[float]) -> str:
    if gust_kph is None:
        return format_knots(steady_kph)
    return f"{to_knots(steady_kph)}–{to_knots(gust_kph)} kn"


def pick_region(regions: List[Dict[str, Any]], region_id: str) -> Dict[str, Any]:
    for r in regions:
        if r["id"] == region_id:
            return r
    raise KeyError(region_id)


def camp_summary_from_notes(notes: List[str]) -> str:
    camp_bits: List[str] = []
    ground_bits: List[str] = []

    for n in notes:
        if n.startswith("Camp: "):
            camp_bits.append(n.replace("Camp: ", "").rstrip("."))
        elif n.startswith("Ground: "):
            ground_bits.append(n.replace("Ground: ", "").rstrip("."))

    bits = camp_bits + ground_bits
    if not bits:
        return ""
    # lowercase first letter of first bit for smoother sentence
    bits[0] = bits[0][0].upper() + bits[0][1:]
    return ", ".join(bits) + "."


def tow_phrases_from_notes(notes: List[str]) -> str:
    tow = None
    gust = None
    for n in notes:
        if n.startswith("Towing: "):
            tow = n.replace("Towing: ", "").rstrip(".")
        elif n.startswith("Gusts: "):
            gust = n.replace("Gusts: ", "").rstrip(".")

    parts: List[str] = []
    if tow:
        parts.append(tow)
    if gust:
        # make it flow nicer: "mild gusts" not "Gusts: mild"
        if gust.lower().startswith("gusts"):
            parts.append(gust)
        else:
            parts.append(gust.lower())

    return ", ".join(parts)


def camp_breeze_from_notes(notes: List[str]) -> str:
    """Grab the main 'Camp: ...' breeze description if present."""
    for n in notes:
        if n.startswith("Camp: "):
            txt = n.replace("Camp: ", "").rstrip(".")
            return txt
    return ""


# -----------------------------
# Dummy forecast for testing
# -----------------------------


def make_dummy_forecast():
    """
    Build a tiny fake forecast set for two regions so we can see nice text.

    Wind / rain values are in km/h + mm, just like the main engine.
    """

    # Grab two known regions by id (adjust if your IDs differ)
    regions_by_id = {r["id"]: r for r in CARAVAN_REGIONS}

    benmore = regions_by_id.get("benmore_mackenzie") or regions_by_id.get(
        "benmore_mackenzie_basin", list(regions_by_id.values())[0]
    )
    waikaia = regions_by_id.get("waikaia_five_rivers") or regions_by_id.get(
        "waikaia_five", list(regions_by_id.values())[1]
    )

    regions = [benmore, waikaia]

    # Numbers chosen to line up roughly with your earlier smoke test output
    forecast_by_region: Dict[str, List[Dict[str, Any]]] = {
        benmore["id"]: [
            {
                "date": "2025-12-01",
                "tow_wind": 18.0,
                "tow_gust": 35.0,
                "camp_wind": 10.0,
                "camp_rain": 0.5,
                "camp_rain_prev48": 3.0,
                "tow_dir": "NW",
                "camp_dir": "NW",
            },
            {
                "date": "2025-12-02",
                "tow_wind": 20.0,
                "tow_gust": 32.0,
                "camp_wind": 14.0,
                "camp_rain": 3.0,
                "camp_rain_prev48": 7.0,
                "tow_dir": "NW",
                "camp_dir": "NW",
            },
            {
                "date": "2025-12-03",
                "tow_wind": 48.0,
                "tow_gust": 70.0,
                "camp_wind": 12.0,
                "camp_rain": 1.0,
                "camp_rain_prev48": 5.0,
                "tow_dir": "NW",
                "camp_dir": "NW",
            },
        ],
        waikaia["id"]: [
            {
                "date": "2025-12-01",
                "tow_wind": 18.0,
                "tow_gust": 35.0,
                "camp_wind": 10.0,
                "camp_rain": 0.5,
                "camp_rain_prev48": 3.0,
                "tow_dir": "SW",
                "camp_dir": "SW",
            },
            {
                "date": "2025-12-02",
                "tow_wind": 20.0,
                "tow_gust": 32.0,
                "camp_wind": 14.0,
                "camp_rain": 3.0,
                "camp_rain_prev48": 7.0,
                "tow_dir": "SW",
                "camp_dir": "SW",
            },
            {
                "date": "2025-12-03",
                "tow_wind": 48.0,
                "tow_gust": 70.0,
                "camp_wind": 12.0,
                "camp_rain": 1.0,
                "camp_rain_prev48": 5.0,
                "tow_dir": "SW",
                "camp_dir": "SW",
            },
        ],
    }

    return regions, forecast_by_region


# -----------------------------
# Formatting a window (style B)
# -----------------------------


def format_window(window: Dict[str, Any], first_day_raw: Dict[str, Any]) -> str:
    """
    Turn a caravan window into friendly text:

    Region – 2 nights look mint
    Light breeze, basically dry, odd shower, reasonably dry, could be soft.
    Tow: NW 10–25 kn — light winds, mild gusts.
    Camp: NW 8 kn — light breeze in camp.
    """
    region_name = window["region_name"]
    nights = window["nights"]

    if nights == 1:
        nights_text = "1 night looks ok"
    elif nights == 2:
        nights_text = "2 nights look mint"
    else:
        nights_text = f"{nights} nights look mint"

    # Re-score this day using the same helpers the engine uses so the notes match.
    _, _, tow_notes = _score_towing(
        tow_wind=first_day_raw["tow_wind"],
        tow_gust=first_day_raw["tow_gust"],
    )
    _, _, camp_notes = _score_camping(
        wind=first_day_raw["camp_wind"],
        rain=first_day_raw["camp_rain"],
        rain_prev48=first_day_raw["camp_rain_prev48"],
    )
    notes = tow_notes + camp_notes

    # Line 2 – camp / ground summary
    camp_summary = camp_summary_from_notes(notes)

    # Line 3 – tow line with knots + phrases
    tow_dir = first_day_raw["tow_dir"]
    tow_range_txt = format_knots_range(
        first_day_raw["tow_wind"], first_day_raw["tow_gust"]
    )
    tow_phrase = tow_phrases_from_notes(notes)
    tow_suffix = f" — {tow_phrase}" if tow_phrase else ""
    tow_line = f"Tow: {tow_dir} {tow_range_txt}{tow_suffix}."

    # Line 4 – camp line with knots + breeze phrase
    camp_dir = first_day_raw["camp_dir"]
    camp_kn = format_knots(first_day_raw["camp_wind"])
    camp_breeze = camp_breeze_from_notes(notes)
    if camp_breeze:
        camp_line = f"Camp: {camp_dir} {camp_kn} — {camp_breeze}."
    else:
        camp_line = f"Camp: {camp_dir} {camp_kn}."

    lines = [
        f"{region_name} – {nights_text}",
        camp_summary,
        tow_line,
        camp_line,
    ]

    return "\n".join(line for line in lines if line.strip())


# -----------------------------
# Main
# -----------------------------


def main():
    regions, forecast_by_region = make_dummy_forecast()

    windows = find_best_caravan_windows(
        regions,
        forecast_by_region,
        min_nights=2,
    )

    print("=== Caravan text test ===\n")

    if not windows:
        print("No decent caravan windows found in the dummy data.")
        return

    for w in windows:
        rid = w["region_id"]
        # Use the first day of the window as the "representative" for text
        start_date = w["start_date"]
        raw_day = next(
            d for d in forecast_by_region[rid] if d["date"] == start_date
        )

        print(format_window(w, raw_day))
        print("-" * 40)


if __name__ == "__main__":
    main()