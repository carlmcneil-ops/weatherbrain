# scoring_config.py
import json
from pathlib import Path
from typing import Dict, Any
from threading import Lock

_CONFIG_PATH = Path("config/scoring_admin.json")
_CONFIG_LOCK = Lock()

# Reasonable defaults so the UI has something to show the first time
_DEFAULT_CONFIG: Dict[str, Any] = {
    "regions": {
        "hunter": {
            "label": "Hunter River via Lake Hawea",
            "activities": {
                "boating_fizz": {
                    "label": "Fizz boat mission",
                    "window_min_length": 2,
                    "go_threshold": 80,
                    "maybe_threshold": 70,
                    "notes": "Top/mid lake, Wanaka-based Hunter mission."
                }
            }
        },
        "te_anau": {
            "label": "Lake Te Anau – Moana",
            "activities": {
                "boating_moana": {
                    "label": "Moana berth missions",
                    "window_min_length": 2,
                    "go_threshold": 80,
                    "maybe_threshold": 75,
                    "notes": "Moana on Lake Te Anau from Wanaka."
                }
            }
        },
        "waikaia": {
            "label": "Waikaia / Piano Flat",
            "activities": {
                "river_fishing": {
                    "label": "Camping + river fishing",
                    "window_min_length": 2,
                    "go_threshold": 75,
                    "maybe_threshold": 70,
                    "notes": "Score thresholds for Waikaia river trips."
                }
            }
        }
    }
}


def _ensure_file_exists() -> None:
    if not _CONFIG_PATH.parent.exists():
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _CONFIG_PATH.exists():
        with _CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(_DEFAULT_CONFIG, f, indent=2)


def load_config() -> Dict[str, Any]:
    with _CONFIG_LOCK:
        _ensure_file_exists()
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)


def save_config(cfg: Dict[str, Any]) -> None:
    with _CONFIG_LOCK:
        _ensure_file_exists()
        with _CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)


def get_activity_thresholds(region_id: str, activity_id: str) -> Dict[str, int]:
    """
    Look up window_min_length / go_threshold / maybe_threshold
    for a given region + activity from scoring_admin.json.

    Falls back to sensible defaults if anything is missing.
    """
    cfg: Dict[str, Any] = load_config()
    regions = cfg.get("regions", {})
    region = regions.get(region_id, {})
    activities = region.get("activities", {})
    act = activities.get(activity_id, {})

    window_min_length = int(act.get("window_min_length", 2))
    go_threshold = int(act.get("go_threshold", 80))
    maybe_threshold = int(act.get("maybe_threshold", 70))

    return {
        "window_min_length": window_min_length,
        "go_threshold": go_threshold,
        "maybe_threshold": maybe_threshold,
    }