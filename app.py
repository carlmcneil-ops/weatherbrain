import os
from typing import Dict, Any, List

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from openai import OpenAI

from scoring import (
    build_boating_day_summaries,
    build_moana_day_summaries,
    build_waikaia_day_summaries,
    find_multi_day_windows,
    choose_best_window,
    evaluate_waikaia_trip,
)
from brain import score_period, _find_windows, _choose_best_window
from spots import SPOTS as SPOT_LIST  # your list
from caravan_api import router as caravan_router
from scoring_config import (
    load_config as load_admin_config,
    save_config as save_admin_config,
    get_activity_thresholds,
)

# Turn list-of-spots into id -> spot dict
SPOTS: Dict[str, Dict[str, Any]] = {spot["id"]: spot for spot in SPOT_LIST}

app = FastAPI(title="Fishing Weather Bot")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Register caravan endpoints
app.include_router(caravan_router)

# ------------- OpenAI client -------------

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

client = OpenAI()


# ------------- Request/response models -------------


class ForecastRequest(BaseModel):
    spot_id: str = Field(..., description="Key from SPOTS dict, e.g. 'wanaka'")
    days: int = Field(3, ge=1, le=7, description="How many days ahead to look")
    tone: str = Field(
        "calm",
        description="Narrative tone: e.g. calm, blunt, optimistic, cautious",
    )
    detail_level: str = Field(
        "normal",
        description="One of: 'short', 'normal', 'nerdy'",
    )
    wind_sensitive: bool = Field(
        True,
        description="If True, emphasise wind and gusts more in the summary",
    )


class ForecastResponse(BaseModel):
    spot_name: str
    days: int
    raw_weather: Dict[str, Any]
    narrative: str


class BrainDebugResponse(BaseModel):
    spot_name: str
    region_id: str
    activity_id: str
    scored: Dict[str, Any]


# ------------- Helper functions -------------


async def fetch_weather(lat: float, lon: float, days: int, timezone: str) -> Dict[str, Any]:
    """
    Fetch daily weather from Open-Meteo (no API key required).
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "windspeed_10m_max",
            "windgusts_10m_max",
            "winddirection_10m_dominant",
        ],
        "timezone": timezone,
        "forecast_days": days,
    }
    async with httpx.AsyncClient(timeout=10) as http_client:
        resp = await http_client.get(url, params=params)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Weather API error ({resp.status_code})",
            )
        return resp.json()


def build_openai_prompt(
    spot_name: str,
    days: int,
    tone: str,
    detail_level: str,
    wind_sensitive: bool,
    weather: Dict[str, Any],
) -> str:
    """
    Turn raw weather data into a prompt for the model.

    IMPORTANT: We format headings so the front-end regex can recognise them
    and turn "Monday, December 1st ..." into the grey pill.
    """
    level_map = {
        "short": "Keep it under 3 short paragraphs.",
        "normal": "Keep it concise but informative, around 3–5 short paragraphs.",
        "nerdy": "Add more detail, but keep it under 7 short paragraphs.",
    }
    level_instruction = level_map.get(detail_level, level_map["normal"])

    wind_instruction = (
        "This angler is VERY sensitive to wind. Call out windspeed and gusts clearly, "
        "and be brutally honest about when the wind will make fishing unpleasant."
        if wind_sensitive
        else "Mention wind and gusts, but don't obsess over them."
    )

    tone_instruction = (
        f"The overall tone should be {tone} and realistic. "
        "Write like a local guide who actually fishes there."
    )

    lower_name = spot_name.lower()

    # Activity-specific instruction:
    # 1) Waikaia – wade fishing only, no boats.
    if "waikaia" in lower_name:
        activity_instruction = (
            "Write for fly fishers on foot only. "
            "This is a river valley with wade fishing and camping, no boats or lake craft. "
            "Do NOT mention boating or boat anglers anywhere in your forecast."
        )

    # 2) Te Anau / Moana – very conservative boating rules.
    elif "te anau" in lower_name or "moana" in lower_name:
        activity_instruction = (
            "Write for a boater running a launch called Moana on Lake Te Anau. "
            "This skipper is very conservative about lake conditions. "
            "As a rule of thumb:\n"
            "- Sustained winds above about 12 km/h OR gusts above about 45 km/h "
            "should usually be treated as rough, unpleasant, or no-go for relaxed boating.\n"
            "- Strong winds combined with heavy rain should be treated as 'no-go' for boating.\n"
            "Be very blunt about when the lake will be lumpy, ugly, or unsafe, and clearly "
            "flag those days as no-go for boating. Only describe a day as a 'good window' "
            "for Moana if winds and gusts are genuinely light and conditions are relaxed."
        )

    # 3) Everything else – normal lakes / coasts.
    else:
        activity_instruction = (
            "Write for both fly fishers and boat anglers where appropriate. "
            "If boating is obviously unrealistic at this location, focus on fishing only."
        )

    return f"""
You are a fishing-savvy weather assistant.

Location: {spot_name}
Days ahead: {days}

Here is the raw daily weather data in JSON:
{weather}

Write a narrative forecast.
{activity_instruction}

ABSOLUTE FORMAT RULES (THESE ARE CRITICAL):
- Do NOT use any markdown at all. No asterisks, no **bold**, no bullet points, no numbered lists, no tables.
- Use normal sentence case. Every sentence must start with a capital letter.
- For EACH forecast day:
  - The FIRST words of the paragraph must be the day and date in this exact style:
      Monday, December 1st looks like...
      Tuesday, December 2nd brings...
      Wednesday, December 3rd remains...
    (weekday, comma, full month name, day number with st/nd/rd/th, then the rest of the sentence).
  - Keep the day/date and the rest of that first sentence on the SAME LINE. Do not put the day/date on its own line.
  - Separate each day's block with a single blank line.
- After describing all days, you MAY add one final summary paragraph starting with
  "In summary," on its own normal paragraph line.
- Do NOT wrap titles or dates in any special characters.
- Use plain text sentences only.

- When describing wind, include wind direction in simple compass terms (e.g. "light NE", "fresh NW").
  Use the dominant wind direction from the JSON and turn degrees into direction roughly like:
    0–22 = N, 23–67 = NE, 68–112 = E, 113–157 = SE,
    158–202 = S, 203–247 = SW, 248–292 = W, 293–337 = NW, 338–360 = N.

CONTENT FOCUS:
- For each day, focus on:
  - Wind and gusts (very important)
  - Rain / precipitation
  - Temperature (cold mornings / warm afternoons)
  - Obvious 'go / no-go' windows for both fly fishing and boating (only if boating is realistic for this location)
- Give direct advice: e.g. "Good window early morning", "Afternoon will be rough on the lake".
- Assume the reader is in New Zealand.

{wind_instruction}
{tone_instruction}
""".strip()


def summarise_weather_with_ai(prompt: str) -> str:
    """
    Call OpenAI to turn structured weather into a narrative.
    """
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You turn weather into honest, practical forecasts for anglers.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.6,
    )
    return response.choices[0].message.content.strip()


# ------------- Web UI ------------------


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "spots": SPOTS},
    )


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/debug/static")
async def debug_static():
    cwd = os.getcwd()
    static_exists = os.path.isdir("static")
    files: List[str] = []
    if static_exists:
        files = os.listdir("static")
    return {"cwd": cwd, "static_exists": static_exists, "files": files}


@app.get("/api/spots")
async def list_spots():
    return {
        spot_id: {
            "name": spot.get("name"),
            "lat": spot.get("lat"),
            "lon": spot.get("lon"),
            "types": spot.get("types"),
        }
        for spot_id, spot in SPOTS.items()
    }


# ------------------- Expeditions --------------------------


@app.get("/api/teanau_expedition")
async def teanau_expedition(days: int = 10):
    """
    Te Anau / Moana expedition, now using admin-config thresholds.

    Logic:
    - Score each day with build_moana_day_summaries().
    - First, look for windows of at least `window_min_length` days
      where the day label is >= "good".
    - If none exist, fall back to windows where the label is >= "ok".
    - Once we have a best_window, use go_threshold / maybe_threshold
      from the admin config to decide GO / MAYBE-GO / HOLD.
    """
    if days < 2 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 2 and 10")

    spot_id = "teanau_moana"
    if spot_id not in SPOTS:
        raise HTTPException(status_code=500, detail="teanau_moana spot not found in SPOTS")

    spot = SPOTS[spot_id]
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": spot["lat"],
        "longitude": spot["lon"],
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "windspeed_10m_max,windgusts_10m_max"
        ),
        "forecast_days": days,
        "timezone": "Pacific/Auckland",
    }
    async with httpx.AsyncClient(timeout=10) as client_http:
        resp = await client_http.get(url, params=params)
        resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily", {})
    day_summaries = build_moana_day_summaries(daily)

        # Pull thresholds from admin config
    thresh = get_activity_thresholds("te_anau", "boating_moana")
    window_min_length = thresh["window_min_length"]
    go_threshold = thresh["go_threshold"]
    maybe_threshold = thresh["maybe_threshold"]

    # Build a simple list of {date, score} for numeric window finding
    scored_days = [
        {"date": d["date"], "score": d.get("score", 0)}
        for d in day_summaries
        if "date" in d
    ]

    # Minimum score a day must have to be part of any window.
    # Using min(go, maybe) means if you drag both down in admin,
    # you genuinely allow softer windows.
    min_score_for_window = min(go_threshold, maybe_threshold)

    windows = _find_windows(
        scored_days,
        min_score=min_score_for_window,
        min_length=window_min_length,
    )
    best_window = _choose_best_window(windows)

    if best_window is None:
        verdict = "no-window"
        reason = (
            f"No {window_min_length}+ day window on Lake Te Anau "
            f"with scores above ~{min_score_for_window}. Skip it this period."
        )
    else:
        length = best_window["length"]
        start = best_window["start_date"]
        end = best_window["end_date"]
        avg_score = round(best_window["avg_score"])

        if avg_score >= go_threshold:
            verdict = "go"
        elif avg_score >= maybe_threshold:
            verdict = "maybe-go"
        else:
            verdict = "hold"

        reason = (
            f"{length}-day window ({start} → {end}) avg ~{avg_score} "
            f"based on your current thresholds."
        )

    return {
        "spot_id": spot_id,
        "spot_name": spot["name"],
        "days_considered": days,
        "verdict": verdict,
        "reason": reason,
        "best_window": best_window,
        "days": day_summaries,
    }


# ----------------- WeatherBrain v2 Hunter ------------------


@app.get("/api/hunter_expedition_v2")
async def hunter_expedition_v2(days: int = 10):
    """
    Hunter via Lake Hawea – WeatherBrain 2.0 version,
    with verdict driven by admin-config thresholds.
    """
    if days < 1 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 1 and 10")

    region_id = "hunter"
    activity_id = "boating_fizz"

    # thresholds from admin config
    cfg = get_activity_thresholds(region_id, activity_id)
    win_min = cfg["window_min_length"]
    go_thr = cfg["go_threshold"]
    maybe_thr = cfg["maybe_threshold"]

    # We care about the top / mid lake, not the ramp.
    spot_id = "hunter_confluence"
    if spot_id not in SPOTS:
        raise HTTPException(status_code=500, detail="hunter_confluence spot not found in SPOTS")

    spot = SPOTS[spot_id]
    lat = spot["lat"]
    lon = spot["lon"]
    timezone = spot.get("timezone", "Pacific/Auckland")

    # 1. Fetch raw weather (same pattern as /api/brain_debug)
    weather = await fetch_weather(lat, lon, days, timezone)
    daily = weather.get("daily", {})

    times = daily.get("time", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    rain = daily.get("precipitation_sum", [])
    wind = daily.get("windspeed_10m_max", [])
    gust = daily.get("windgusts_10m_max", [])

    # 2. Build DayWeather list for the brain
    day_weather: List[Dict[str, Any]] = []
    for i, date_str in enumerate(times):
        try:
            day_weather.append(
                {
                    "date": date_str,
                    "temp_max": float(tmax[i]),
                    "temp_min": float(tmin[i]),
                    "rain_mm": float(rain[i]),
                    "wind_kmh": float(wind[i]),
                    "gust_kmh": float(gust[i]),
                }
            )
        except (IndexError, ValueError):
            continue

    # 3. Use the WeatherBrain 2.0 scoring engine for this region/activity.
    scored = score_period(region_id, activity_id, day_weather)

    windows = scored.get("windows") or []
    best_window = scored.get("best_window")

    # 4. Apply thresholds from scoring_config.json
    if not windows or best_window is None:
        verdict = "no-window"
        reason = (
            f"WeatherBrain 2.0 can't find a clean Hunter window of at least "
            f"{win_min} day(s) at the top/mid of Lake Hawea. Better to wait."
        )
        best_window_out = None
    else:
        length = best_window["length"]
        start = best_window["start_date"]
        end = best_window["end_date"]
        avg_score = round(best_window["avg_score"])

        if length >= win_min and avg_score >= go_thr:
            verdict = "go"
            reason = (
                f"WeatherBrain 2.0 calls a GO window for the Hunter: "
                f"{length} days ({start} → {end}) averaging ~{avg_score}. "
                "Launch from Lake Hawea – Township / Campground ramp "
                "(south end, west shore)."
            )
        elif length >= win_min and avg_score >= maybe_thr:
            verdict = "maybe-go"
            reason = (
                f"WeatherBrain 2.0 sees a workable but not perfect Hunter window: "
                f"{length} days ({start} → {end}), average score ~{avg_score}. "
                "Worth a crack if you’re keen."
            )
        else:
            verdict = "hold"
            reason = (
                f"There is a {length}-day stretch at the Hunter / top of Lake Hawea "
                f"({start} → {end}), average score ~{avg_score}, but with your "
                "current thresholds it still lands as HOLD."
            )

        best_window_out = best_window

    return {
        "days_considered": days,
        "lake_plans": [
            {
                "spot_id": spot_id,
                "spot_name": spot["name"],
                "scored": scored,
            }
        ],
        "chosen_lake_spot_id": spot_id,
        "chosen_lake_spot_name": spot["name"],
        "verdict": verdict,        # "go" | "maybe-go" | "hold" | "no-window"
        "reason": reason,
        "best_window": best_window_out,
        "profile": {
            "region_id": region_id,
            "activity_id": activity_id,
        },
    }


@app.get("/api/hunter_expedition")
async def hunter_expedition(days: int = 10):
    """
    Backwards-compatible wrapper around hunter_expedition_v2.

    Returns (as closely as possible) the original hunter_expedition shape so
    existing UI code that expects lake_options / best_window keeps working.
    """
    v2 = await hunter_expedition_v2(days=days)

    spot_id = "hunter_confluence"
    spot_name = SPOTS.get(spot_id, {}).get(
        "name", "Hunter River Mouth / Top of Lake Hawea"
    )

    lake_options: List[Dict[str, Any]] = []
    for plan in v2.get("lake_plans", []):
        scored = plan.get("scored", {})
        lake_options.append(
            {
                "spot_id": plan.get("spot_id"),
                "spot_name": plan.get("spot_name"),
                "days": scored.get("days", []),
                "windows": scored.get("windows", []),
                "best_window": scored.get("best_window"),
            }
        )

    return {
        "lake_options": lake_options,
        "fishing_spot_id": spot_id,
        "fishing_spot_name": spot_name,
        "days_considered": v2.get("days_considered"),
        "verdict": v2.get("verdict"),
        "reason": v2.get("reason"),
        "chosen_lake_spot_id": v2.get("chosen_lake_spot_id"),
        "chosen_lake_spot_name": v2.get("chosen_lake_spot_name"),
        "best_window": v2.get("best_window"),
    }


# ------------------------- Waikaia -------------------------


def score_waikaia_day(wind_kmh: float, rain_mm: float) -> Dict[str, Any]:
    if rain_mm >= 15 or wind_kmh >= 40:
        return {"score": 10, "label": "no-go", "reason": "Wet or windy."}
    if wind_kmh <= 20 and rain_mm <= 5:
        return {"score": 75, "label": "good", "reason": "Decent."}
    if wind_kmh <= 30 and rain_mm <= 10:
        return {"score": 60, "label": "ok", "reason": "Workable."}
    return {"score": 40, "label": "marginal", "reason": "Fresh wind or steady rain."}


@app.get("/api/waikaia_trip")
async def waikaia_trip(days: int = 7):
    """
    Waikaia / Piano Flat trip – now hooked to admin thresholds.
    """
    if days < 1 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 1 and 10")

    sid = "waikaia_piano_flat"
    if sid not in SPOTS:
        raise HTTPException(status_code=500, detail="waikaia_piano_flat missing")

    spot = SPOTS[sid]
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": spot["lat"],
        "longitude": spot["lon"],
        "daily": (
            "temperature_2m_max,temperature_2m_min,precipitation_sum,"
            "windspeed_10m_max"
        ),
        "forecast_days": days,
        "timezone": "Pacific/Auckland",
    }
    async with httpx.AsyncClient() as client_http:
        resp = await client_http.get(url, params=params, timeout=10)
        resp.raise_for_status()
    data = resp.json()

    daily = data.get("daily", {})
    times = daily.get("time", [])
    winds = daily.get("windspeed_10m_max", [])
    rain = daily.get("precipitation_sum", [])

    scored_days = []
    for i, d in enumerate(times):
        try:
            w = float(winds[i])
            r = float(rain[i])
            s = score_waikaia_day(w, r)
            scored_days.append(
                {"date": d, "wind_kmh": w, "rain_mm": r, **s}
            )
        except Exception:
            continue

    # thresholds from admin config
    thresh = get_activity_thresholds("waikaia", "river_fishing")
    window_min_length = thresh["window_min_length"]
    go_threshold = thresh["go_threshold"]
    maybe_threshold = thresh["maybe_threshold"]

        # First try: multi-day windows where each day is at least "good"
    windows = find_multi_day_windows(
        scored_days,
        min_length=window_min_length,
        min_label="good",
    )
    best = choose_best_window(windows)
    label_floor_used = "good"

    # Fallback: allow "ok" or better if no good-only window exists
    if best is None:
        windows = find_multi_day_windows(
            scored_days,
            min_length=window_min_length,
            min_label="ok",
        )
        best = choose_best_window(windows)
        label_floor_used = "ok"

    # Still nothing? Then it's genuinely not worth a Waikaia mission.
    if best is None:
        return {
            "spot_id": sid,
            "spot_name": spot["name"],
            "days_considered": days,
            "days": scored_days,
            "verdict": "no-window",
            "reason": f"No {window_min_length}+ day Waikaia window at 'ok' or better.",
            "windows": windows,
            "best_window": None,
        }

    length = best["length"]
    start = best["start_date"]
    end = best["end_date"]
    avg_score = round(best["avg_score"])

    # Now your thresholds actually matter
    if avg_score >= go_threshold:
        verdict = "go"
    elif avg_score >= maybe_threshold:
        verdict = "maybe-go"
        # everything else is effectively "hold"
    else:
        verdict = "hold"

    return {
        "spot_id": sid,
        "spot_name": spot["name"],
        "days_considered": days,
        "days": scored_days,
        "windows": windows,
        "best_window": best,
        "verdict": verdict,
        "reason": (
            f"{length}-day Waikaia window ({start} → {end}) "
            f"avg ~{avg_score} using '{label_floor_used}' as the floor."
        ),
    }


# ------------------- Daily Briefing ------------------------


@app.get("/api/daily_briefing")
async def daily_briefing(days: int = 10):
    """
    Uses expedition endpoints (which themselves use the admin thresholds).
    """
    if days < 2 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 2 and 10")

    teanau = await teanau_expedition(days=days)
    hunter = await hunter_expedition_v2(days=days)
    waikaia = await waikaia_trip(days=min(days, 7))

    def vr(x):
        return {"go": 3, "maybe-go": 2, "hold": 1, "no-window": 0}.get(x, 0)

    options = [
        ("teanau_expedition", "boating", teanau),
        ("hunter_expedition", "boating+fishing", hunter),
        ("waikaia_trip", "camping+fishing", waikaia),
    ]

    best = max(options, key=lambda o: vr(o[2].get("verdict", "no-window")))
    best_data = best[2]

    if vr(best_data.get("verdict")) == 0:
        summary = "No decent multi-day windows anywhere. Stay home, tie flies."
    else:
        summary = f"{best_data.get('reason', '')}"

    return {
        "days_considered": days,
        "summary": summary,
        "teanau": teanau,
        "hunter": hunter,
        "waikaia": waikaia,
        "best_option": {
            "id": best[0],
            "label": best[1],
            "verdict": best_data.get("verdict"),
            "reason": best_data.get("reason"),
        },
    }


# ---------------------- UI FORECAST ------------------------


@app.post("/api/forecast", response_model=ForecastResponse)
async def get_forecast(payload: ForecastRequest):
    if payload.spot_id not in SPOTS:
        raise HTTPException(status_code=404, detail="Unknown spot_id")

    spot = SPOTS[payload.spot_id]
    weather = await fetch_weather(
        spot["lat"],
        spot["lon"],
        payload.days,
        spot.get("timezone", "Pacific/Auckland"),
    )

    prompt = build_openai_prompt(
        spot_name=spot["name"],
        days=payload.days,
        tone=payload.tone,
        detail_level=payload.detail_level,
        wind_sensitive=payload.wind_sensitive,
        weather=weather,
    )
    narrative = summarise_weather_with_ai(prompt)

    return ForecastResponse(
        spot_name=spot["name"],
        days=payload.days,
        raw_weather=weather,
        narrative=narrative,
    )


# ---------------------- Brain Debug ------------------------


@app.post("/api/brain_debug", response_model=BrainDebugResponse)
async def brain_debug(payload: ForecastRequest):
    """
    Transparent WeatherBrain scoring for a given spot_id.
    """
    if payload.spot_id not in SPOTS:
        raise HTTPException(status_code=404, detail="Unknown spot_id")

    spot = SPOTS[payload.spot_id]
    lat, lon = spot["lat"], spot["lon"]
    timezone = spot.get("timezone", "Pacific/Auckland")

    weather = await fetch_weather(lat, lon, payload.days, timezone)
    daily = weather.get("daily", {})

    days_list = []
    times = daily.get("time", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    rain = daily.get("precipitation_sum", [])
    wind = daily.get("windspeed_10m_max", [])
    gust = daily.get("windgusts_10m_max", [])

    for i, d in enumerate(times):
        try:
            days_list.append(
                {
                    "date": d,
                    "temp_max": float(tmax[i]),
                    "temp_min": float(tmin[i]),
                    "rain_mm": float(rain[i]),
                    "wind_kmh": float(wind[i]),
                    "gust_kmh": float(gust[i]),
                }
            )
        except Exception:
            continue

    if payload.spot_id == "teanau_moana":
        region_id = "te_anau"
        activity_id = "boating_moana"
    elif payload.spot_id == "waikaia_piano_flat":
        region_id = "waikaia"
        activity_id = "river_fishing"
    else:
        region_id = "hunter"
        activity_id = "boating_fizz"

    scored = score_period(region_id, activity_id, days_list)

    return BrainDebugResponse(
        spot_name=spot["name"],
        region_id=region_id,
        activity_id=activity_id,
        scored=scored,
    )


# ------------------- Admin config API (JSON) -------------------


@app.get("/api/admin/config")
async def get_admin_config():
    """
    Return the current scoring/config JSON for the admin UI.
    """
    try:
        cfg = load_admin_config()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load config: {e}",
        )
    return cfg


@app.post("/api/admin/config")
async def update_admin_config(request: Request):
    """
    Replace scoring_config.json with the posted JSON body.

    Strict validation:
      - Must be a dict
      - Must contain "regions"
      - At least one activity must exist
    """
    try:
        new_cfg = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload — could not parse",
        )

    if not isinstance(new_cfg, dict):
        raise HTTPException(
            status_code=400,
            detail="Config must be a JSON object",
        )

    regions = new_cfg.get("regions")
    if not isinstance(regions, dict):
        raise HTTPException(
            status_code=400,
            detail="Config must contain a 'regions' object",
        )

    has_activities = False
    for r in regions.values():
        acts = r.get("activities")
        if isinstance(acts, dict) and acts:
            has_activities = True
            break

    if not has_activities:
        raise HTTPException(
            status_code=400,
            detail="Config must define at least one region with activities",
        )

    try:
        save_admin_config(new_cfg)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save config: {e}",
        )

    return {"status": "ok", "saved": True}


# ---------------------- Admin config UI ------------------------


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """
    Simple admin UI so we can tweak scoring/model params without touching code.
    Renders templates/admin.html.
    """
    try:
        config = load_admin_config()
    except Exception:
        config = {}

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "config": config,
        },
    )


# ---------------------- ADMIN THRESHOLD DEBUG ------------------------


@app.get("/api/debug/thresholds")
async def debug_thresholds():
    """
    Dump the effective window/go/maybe thresholds per region/activity
    after reading scoring_config.json.
    """
    cfg = load_admin_config()
    out: Dict[str, Dict[str, Any]] = {}

    for region_id, region in cfg.get("regions", {}).items():
        out[region_id] = {}
        for act_id in region.get("activities", {}).keys():
            out[region_id][act_id] = get_activity_thresholds(region_id, act_id)

    return out