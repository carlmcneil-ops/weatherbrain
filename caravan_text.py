"""
Text helpers for caravan windows.

We take the raw windows from caravan_engine.find_best_caravan_windows(...)
and turn them into human-readable trip blurbs.
"""

from __future__ import annotations
from typing import Dict, Any, List

from caravan_engine import CaravanDayScore


def _compress_camp(bits: List[str]) -> str:
    """
    Turn lots of 'Camp: ...' notes into one human sentence.
    """
    if not bits:
        return "Camp conditions look fine."

    lower = [b.lower() for b in bits]

    has_light_breeze = any("light breeze" in b for b in lower)
    has_breezy_ok = any("breezy but okay" in b or "breezy" in b for b in lower)
    has_odd_shower = any("odd shower" in b for b in lower)
    has_onoff_showers = any("on/off showers" in b for b in lower)
    has_basically_dry = any("basically dry" in b for b in lower)
    has_proper_rain = any("proper rain" in b for b in lower)

    parts: List[str] = []

    # Wind at camp
    if has_light_breeze:
        parts.append("light breeze")
    elif has_breezy_ok:
        parts.append("breezy")

    # Rain
    if has_proper_rain:
        parts.append("proper rain on the cards")
    elif has_onoff_showers or has_odd_shower:
        parts.append("occasional showers")

    # Dryness
    if has_basically_dry and not has_proper_rain:
        parts.append("mostly dry")

    if not parts:
        return "Camp conditions look fine."

    # Capitalise first word
    return parts[0].capitalize() + (
        ", " + ", ".join(parts[1:]) if len(parts) > 1 else ""
    )


def _compress_ground(bits: List[str]) -> str:
    """
    Turn 'Ground: ...' notes into one short line.
    """
    if not bits:
        return ""

    lower = [b.lower() for b in bits]

    if any("likely muddy" in b for b in lower):
        return "Ground likely muddy."
    if any("could be soft" in b for b in lower):
        return "Ground could be soft."
    if any("reasonably dry" in b for b in lower):
        return "Ground reasonably dry."

    # Fallback – join raw phrases
    return ", ".join(bits)


def _compress_tow(bits: List[str]) -> str:
    """
    Pick the 'worst' towing line so we don't list every variant.
    """
    if not bits:
        return "Towing looks easy the whole route."

    # Rank: severe > moderate > light
    severe: List[str] = []
    moderate: List[str] = []
    light: List[str] = []

    for n in bits:
        l = n.lower()
        if "strong winds" in l or "severe" in l:
            severe.append(n)
        elif "moderate winds" in l or "noticeable" in l:
            moderate.append(n)
        elif "light winds" in l or "mild" in l:
            light.append(n)
        else:
            moderate.append(n)

    if severe:
        return " / ".join(sorted(set(severe)))
    if moderate:
        return " / ".join(sorted(set(moderate)))
    if light:
        return " / ".join(sorted(set(light)))

    return "Towing looks easy the whole route."


def summarise_window(window: Dict[str, Any]) -> str:
    """
    Turn a caravan 'window' dict into a short description.

    Expects the shape returned by caravan_engine.find_best_caravan_windows:
      {
        "region_id": "...",
        "region_name": "...",
        "start_date": "YYYY-MM-DD",
        "end_date": "YYYY-MM-DD",
        "nights": 3,
        "avg_score": 82.5,
        "days": [CaravanDayScore, ...]
      }
    """
    region_name: str = window["region_name"]
    nights: int = window["nights"]
    days: List[CaravanDayScore] = window["days"]

    # Collect phrases from notes
    camp_raw: List[str] = []
    ground_raw: List[str] = []
    tow_raw: List[str] = []

    for d in days:
        for note in d.notes:
            if note.startswith("Camp:"):
                camp_raw.append(note.replace("Camp:", "").strip())
            elif note.startswith("Ground:"):
                ground_raw.append(note.replace("Ground:", "").strip())
            elif note.startswith("Towing:") or note.startswith("Gusts:"):
                tow_raw.append(note.strip())

    # Build lines
    title = f"{region_name} – {nights} night{'s' if nights != 1 else ''} look mint"

    camp_line = _compress_camp(camp_raw)
    ground_line = _compress_ground(ground_raw)
    tow_line = _compress_tow(tow_raw)

    lines: List[str] = [title, camp_line]
    if ground_line:
        lines.append(ground_line)
    lines.append(tow_line)

    return "\n".join(lines)