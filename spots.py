# spots.py
# Core fishing / boating / camping spots used by Carl's Weather Brain.

SPOTS = [
    {
        "id": "wanaka_paddock",
        "name": "Lake Wanaka – Paddock Bay",
        "lat": -44.71,
        "lon": 169.03,
        "drive_minutes": 15,
        "types": ["boating"],
        "exposure": "sheltered",
        "wind_multiplier": 0.6,
        "gust_multiplier": 0.7,
    },
    {
        "id": "hawea_timaru",
        "name": "Lake Hawea – Timaru Creek",
        "lat": -44.52,
        "lon": 169.32,
        "drive_minutes": 35,
        "types": ["boating"],
        "exposure": "exposed",
    },
    {
        "id": "hawea_township",
        "name": "Lake Hawea – Township",
        "lat": -44.62,
        "lon": 169.23,
        "drive_minutes": 20,
        "types": ["boating", "camping", "lake_fishing"],
        "exposure": "moderate",
    },
    {
        "id": "wanaka_glendhu",
        "name": "Lake Wanaka – Glendhu Bay",
        "lat": -44.71,
        "lon": 169.00,
        "drive_minutes": 15,
        "types": ["boating", "camping"],
        "exposure": "moderate",
    },
    {
        "id": "hawea_kidds_bush",
        "name": "Lake Hawea – Kidds Bush",
        "lat": -44.43,
        "lon": 169.37,
        "drive_minutes": 45,
        "types": ["camping", "boating"],
        "exposure": "exposed",
    },
    {
        "id": "benmore_haldon",
        "name": "Lake Benmore – Haldon Arm",
        "lat": -44.58,
        "lon": 170.15,
        "drive_minutes": 180,
        "types": ["camping", "boating", "lake_fishing"],
        "exposure": "moderate",
    },
    {
        "id": "maka_cameron_flat",
        "name": "Makarora – Cameron Flat",
        "lat": -44.18,
        "lon": 169.28,
        "drive_minutes": 70,
        "types": ["fly_fishing", "camping"],
        "exposure": "moderate",
    },
    {
        "id": "matukituki_valley",
        "name": "Matukituki Valley – Raspberry Creek",
        "lat": -44.56,
        "lon": 168.77,
        "drive_minutes": 60,
        "types": ["fly_fishing", "camping"],
        "exposure": "moderate",
    },
    {
        "id": "hunter_confluence",
        "name": "Hunter River – Top of Lake Hawea",
        "lat": -44.20,
        "lon": 169.23,
        "drive_minutes": 90,
        "types": ["fly_fishing_special"],
        "clarity_model": "hunter_rain_blend",
        "alpine_sources": [
            {"lat": -44.18, "lon": 169.28},  # Makarora approx
            {"lat": -44.20, "lon": 169.32},  # Cameron Flat approx
        ],
        "valley_source": {"lat": -44.62, "lon": 169.23},  # Hawea township approx
    },
    {
        "id": "waikaia_piano_flat",
        "name": "Waikaia – Piano Flat DOC",
        "lat": -45.73,
        "lon": 168.57,
        "drive_minutes": 170,
        "types": ["fly_fishing", "camping"],
        "clarity_model": "flow_or_rain",
        "exposure": "moderate",
    },
    {
        "id": "teanau_moana",
        "name": "Lake Te Anau – Moana berth",
        "lat": -45.41,
        "lon": 167.72,
        "drive_minutes": 0,  # no towing required; boat’s already there
        "types": ["boating"],
        "exposure": "moderate",
        "priority_multi_day_calm": True,  # special rule for the launch
    },
]
