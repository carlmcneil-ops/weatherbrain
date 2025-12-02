"""
region_profiles.py

Data-only configuration for WeatherBrain region + activity profiles.

Nothing in here talks to FastAPI or OpenAI.
It’s purely parameters that the scoring “brain” will use later.

Right now this module is *not* wired into scoring.py.
That hookup happens in a later step.
"""

from typing import Dict, Any

# Type alias for clarity – we’re not being super strict here.
RegionProfiles = Dict[str, Dict[str, Any]]


REGION_PROFILES: RegionProfiles = {
    # ------------------------------------------------------------------
    # Hunter – fizz boat missions (generic lake / open fetch)
    # ------------------------------------------------------------------
"hunter": {
        "label": "Hunter – fizz boat missions",
        "timezone": "Pacific/Auckland",
        "default_activity": "boating_fizz",

        "activities": {
            "boating_fizz": {
                "label": "Fizzboat – Hunter",

                # Hunter = more sendy, less fussy than Moana.
                "weights": {
                    "wind": 0.50,
                    "rain": 0.15,
                    "temp": 0.20,
                    "cloud": 0.15,
                },

                # Wind bands for Hunter fizz missions (km/h).
                # Slightly more tolerant than Moana: if it's rideable, it's in.
                "wind_bands": [
                    {
                        "max_wind": 10,
                        "max_gust": 18,
                        "score": 95,
                        "label": "glassy",
                        "description": "Light winds, easy boating, minimal chop.",
                    },
                    {
                        "max_wind": 16,
                        "max_gust": 28,
                        "score": 85,
                        "label": "breezy",
                        "description": "Breezy but still comfortable for a fizz boat.",
                    },
                    {
                        "max_wind": 22,
                        "max_gust": 35,
                        "score": 70,
                        "label": "lumpy",
                        "description": "Lumpy but workable if you’re keen.",
                    },
                    {
                        "max_wind": 28,
                        "max_gust": 45,
                        "score": 45,
                        "label": "hard_work",
                        "description": "Hard work, only go if you really want it.",
                    },
                    {
                        "max_wind": 999,
                        "max_gust": 999,
                        "score": 15,
                        "label": "no_go",
                        "description": "Too windy – not worth it.",
                    },
                ],

                # Daily rain total (mm) – Hunter is tolerant of some showers.
                "rain_bands": [
                    {
                        "max": 0.5,
                        "score": 95,
                        "label": "dry",
                        "description": "Essentially dry.",
                    },
                    {
                        "max": 3.0,
                        "score": 85,
                        "label": "light_showers",
                        "description": "Light showers, still an easy day out.",
                    },
                    {
                        "max": 8.0,
                        "score": 60,
                        "label": "wet",
                        "description": "Wet day but still fishable/boatable if you’re motivated.",
                    },
                    {
                        "max": 999,
                        "score": 30,
                        "label": "soaking",
                        "description": "Soaking – most people will stay home.",
                    },
                ],

                "temp_bands": [
                    {
                        "min": 5,
                        "max": 10,
                        "score": 65,
                        "label": "chilly",
                        "description": "Chilly but manageable with decent gear.",
                    },
                    {
                        "min": 11,
                        "max": 20,
                        "score": 90,
                        "label": "comfortable",
                        "description": "Comfortable for a day on the water.",
                    },
                    {
                        "min": 21,
                        "max": 28,
                        "score": 80,
                        "label": "warm",
                        "description": "Warm day, bring sunscreen.",
                    },
                    {
                        "min": -999,
                        "max": 4,
                        "score": 40,
                        "label": "cold",
                        "description": "Cold – not a deal breaker but less pleasant.",
                    },
                ],

                "window_logic": {
                    # Hunter can be a single-day hit-and-run.
                    "min_good_days": 1,
                    # Slightly more relaxed than Moana: 65+ counts as a 'good' day.
                    "min_score_for_good": 65,
                    "min_window_length": 1,
                },
            }
        },
    },

    # ------------------------------------------------------------------
    # Te Anau – Moana (Logan 33, more capable cruiser)
    # ------------------------------------------------------------------
    "te_anau": {
        "label": "Te Anau – Moana",
        "timezone": "Pacific/Auckland",
        "default_activity": "boating_moana",

        "activities": {
            "boating_moana": {
                "label": "Moana – overnight cruising",

                "weights": {
                    "wind": 0.45,
                    "rain": 0.25,
                    "temp": 0.20,
                    "cloud": 0.10,
                },

                "wind_bands": [
                    {
                        "max_wind": 12,
                        "max_gust": 25,
                        "score": 90,
                        "label": "ideal",
                        "description": "Light to moderate winds, easy cruising.",
                    },
                    {
                        "max_wind": 20,
                        "max_gust": 35,
                        "score": 70,
                        "label": "ok",
                        "description": "Fresh but fine for a solid launch.",
                    },
                    {
                        "max_wind": 26,
                        "max_gust": 45,
                        "score": 45,
                        "label": "lumpy",
                        "description": "Lumpy – ok in short hops if you’re experienced.",
                    },
                    {
                        "max_wind": 999,
                        "max_gust": 999,
                        "score": 25,
                        "label": "stay_in_harbour",
                        "description": "Too rough for a relaxed trip.",
                    },
                ],

                "rain_bands": [
                    {
                        "max": 1.0,
                        "score": 90,
                        "label": "showers_ok",
                        "description": "Showers about, typical Fiordland day.",
                    },
                    {
                        "max": 5.0,
                        "score": 65,
                        "label": "rainy_but_fine",
                        "description": "Steady rain but Moana can handle it.",
                    },
                    {
                        "max": 999,
                        "score": 30,
                        "label": "soaking",
                        "description": "Hosing down – not a trip for everyone.",
                    },
                ],

                "temp_bands": [
                    {
                        "min": 3,
                        "max": 8,
                        "score": 60,
                        "label": "cold_but_ok",
                        "description": "Cold, but cabin and gear make it fine.",
                    },
                    {
                        "min": 9,
                        "max": 18,
                        "score": 85,
                        "label": "comfortable",
                        "description": "Comfortable inside and out.",
                    },
                    {
                        "min": 19,
                        "max": 25,
                        "score": 80,
                        "label": "warm",
                        "description": "Warm cruising conditions.",
                    },
                ],

                "window_logic": {
                    "min_good_days": 2,        # Moana trips tend to be multi-day
                    "min_score_for_good": 65,
                    "min_window_length": 2,
                },
            }
        },
    },

    # ------------------------------------------------------------------
    # Waikaia – river fishing missions
    # ------------------------------------------------------------------
    "waikaia": {
        "label": "Waikaia River – fishing",
        "timezone": "Pacific/Auckland",
        "default_activity": "river_fishing",

        "activities": {
            "river_fishing": {
                "label": "Waikaia – trout mission",

                "weights": {
                    "wind": 0.20,
                    "rain": 0.40,
                    "temp": 0.20,
                    "cloud": 0.10,
                    "flow": 0.10,  # will matter once we wire river flow data in
                },

                # River flow bands assume you’ll feed in “river_flow” later.
                "flow_bands": [
                    {
                        "min": 8,
                        "max": 18,
                        "score": 95,
                        "label": "prime",
                        "description": "Prime flow – classic Waikaia.",
                    },
                    {
                        "min": 19,
                        "max": 25,
                        "score": 75,
                        "label": "ok",
                        "description": "Ok but getting up.",
                    },
                    {
                        "min": 26,
                        "max": 35,
                        "score": 45,
                        "label": "high",
                        "description": "High and pushy.",
                    },
                    {
                        "min": 36,
                        "max": 999,
                        "score": 20,
                        "label": "flooded",
                        "description": "Basically blown out.",
                    },
                ],

                "rain_bands": [
                    {
                        "max": 0.5,
                        "score": 95,
                        "label": "dry",
                        "description": "Dry or near enough.",
                    },
                    {
                        "max": 3.0,
                        "score": 75,
                        "label": "light_rain",
                        "description": "Light rain, river should hold.",
                    },
                    {
                        "max": 10.0,
                        "score": 40,
                        "label": "dirtying",
                        "description": "Enough rain that colour and level become an issue.",
                    },
                    {
                        "max": 999,
                        "score": 20,
                        "label": "blown_out",
                        "description": "Likely blown out or close to it.",
                    },
                ],

                "wind_bands": [
                    {
                        "max_wind": 8,
                        "max_gust": 15,
                        "score": 90,
                        "label": "easy_casting",
                        "description": "Gentle breeze, easy casting.",
                    },
                    {
                        "max_wind": 15,
                        "max_gust": 25,
                        "score": 70,
                        "label": "workable",
                        "description": "Workable, just a bit of line management.",
                    },
                    {
                        "max_wind": 22,
                        "max_gust": 35,
                        "score": 45,
                        "label": "hard_work",
                        "description": "Hard work, cross-wind mends and ugly casts.",
                    },
                    {
                        "max_wind": 999,
                        "max_gust": 999,
                        "score": 25,
                        "label": "gnarly",
                        "description": "Pretty grim – possible, but not fun.",
                    },
                ],

                "temp_bands": [
                    {
                        "min": 6,
                        "max": 12,
                        "score": 80,
                        "label": "cool",
                        "description": "Cool but great trout temps.",
                    },
                    {
                        "min": 13,
                        "max": 20,
                        "score": 90,
                        "label": "mint",
                        "description": "Mint temps – classic fishing day.",
                    },
                    {
                        "min": -999,
                        "max": 5,
                        "score": 40,
                        "label": "cold",
                        "description": "Cold – trout still feed but less comfy for you.",
                    },
                ],

                "window_logic": {
                    "min_good_days": 1,
                    "min_score_for_good": 70,
                    "min_window_length": 1,
                },
            }
        },
    },
}