# spots.py
#
# List of fishing / boating spots the app knows about.
# app.py does:
#   from spots import SPOTS as SPOT_LIST
#   SPOTS = {spot["id"]: spot for spot in SPOT_LIST}

SPOTS = [
    # ---------- Lake Wanaka ----------

    {
        "id": "wanaka_paddock",
        "name": "Lake Wanaka – Paddock Bay",
        "lat": -44.654,      # approx Paddock Bay
        "lon": 169.151,
        "timezone": "Pacific/Auckland",
        "types": ["boating", "fishing"],
        "boat": "fizzboat",
    },
    {
        "id": "wanaka_glendhu",
        "name": "Lake Wanaka – Glendhu Bay",
        "lat": -44.687,      # approx Glendhu Bay
        "lon": 169.063,
        "timezone": "Pacific/Auckland",
        "types": ["boating", "fishing", "camping"],
        "boat": "fizzboat",
    },

    # ---------- Lake Hawea / Hunter access ----------

    {
        "id": "hawea_township",
        "name": "Lake Hawea – Township / Campground ramp (south end, west shore)",
        "lat": -44.645,      # approx Hawea township / campground
        "lon": 169.233,
        "timezone": "Pacific/Auckland",
        "types": ["boating", "fishing"],
        "boat": "fizzboat",
    },
    {
        "id": "hawea_timaru",
        "name": "Lake Hawea – Timaru Creek (east shore, south of Hunter)",
        "lat": -44.516,      # approx Timaru Creek on east shore
        "lon": 169.327,
        "timezone": "Pacific/Auckland",
        "types": ["boating", "fishing"],
        "boat": "fizzboat",
    },
    {
        "id": "hawea_kidds_bush",
        "name": "Lake Hawea – Kidds Bush (northwest shore)",
        "lat": -44.468,      # approx Kidds Bush DOC camp
        "lon": 169.277,
        "timezone": "Pacific/Auckland",
        "types": ["boating", "fishing", "camping"],
        "boat": "fizzboat",
    },

    # This is NOT a launch – used as a reference fishing location
    {
        "id": "hunter_confluence",
        "name": "Hunter River – Mouth / top of Lake Hawea (north end)",
        "lat": -44.420,      # approx Hunter River mouth into Hawea
        "lon": 169.282,
        "timezone": "Pacific/Auckland",
        "types": ["fishing"],
        # no boat profile needed – we travel there via Hawea fizzboat spots
    },

    # ---------- Lake Te Anau / Moana ----------

    {
        "id": "teanau_moana",
        "name": "Lake Te Anau – Moana berth",
        "lat": -45.414,      # approx Te Anau marina area
        "lon": 167.718,
        "timezone": "Pacific/Auckland",
        "types": ["boating"],
        "boat": "moana",     # 33 ft launch permanently moored here
    },

    # ---------- Lake Benmore ----------

    {
        "id": "benmore_haldon",
        "name": "Lake Benmore – Haldon Arm",
        "lat": -44.656,      # approx Haldon Arm area
        "lon": 170.338,
        "timezone": "Pacific/Auckland",
        "types": ["boating", "fishing", "camping"],
        "boat": "fizzboat",
    },

    # ---------- Waikaia / Piano Flat ----------

    {
        "id": "waikaia_piano_flat",
        "name": "Waikaia – Piano Flat DOC",
        "lat": -45.595,      # approx Piano Flat DOC campsite
        "lon": 169.064,
        "timezone": "Pacific/Auckland",
        "types": ["fishing", "camping"],
        # no boat profile – this is camping/river time
    },
]