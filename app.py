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
from spots import SPOTS as SPOT_LIST  # your list

# Turn list-of-spots into id -> spot dict
SPOTS: Dict[str, Dict[str, Any]] = {spot["id"]: spot for spot in SPOT_LIST}

app = FastAPI(title="Fishing Weather Bot")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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
    """
    level_map = {
        "short": "Keep it under 3 short paragraphs.",
        "normal": "Keep it concise but informative, 3–5 short paragraphs.",
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

    return f"""
You are a fishing-savvy weather assistant.

Location: {spot_name}
Days ahead: {days}

Here is the raw daily weather data in JSON:
{weather}

Write a narrative forecast specifically for fly fishers and boat anglers.

Requirements:
- Group the forecast by day with clear headings (e.g. 'Friday', 'Saturday').
- Focus on:
  - Wind and gusts
  - Rain/precipitation
  - Temperature (cold mornings / warm afternoons)
  - Obvious 'go / no-go' windows
- Give direct advice: e.g. 'Good window early morning', 'Afternoon will be rough on the lake'.
- Assume the reader is in New Zealand.

{wind_instruction}
{tone_instruction}
{level_instruction}

Use plain language, no emojis, no bullet points.
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


# ------------- Routes -------------


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "spots": SPOTS,
        },
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
    return {
        "cwd": cwd,
        "static_exists": static_exists,
        "files": files,
    }


# ---------- Te Anau / Moana expedition ----------


@app.get("/api/teanau_expedition")
async def teanau_expedition(days: int = 10):
    """
    Decide if there's a worthwhile Te Anau / Moana expedition window
    in the next N days.

    This is a trip, not a day mission:
      - look for >= 2 consecutive days that are 'good' or 'excellent'
      - uses Moana-specific scoring (aggressive on wind/gusts, relaxed on rain)
    """
    if days < 2 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 2 and 10")

    spot_id = "teanau_moana"
    if spot_id not in SPOTS:
        raise HTTPException(status_code=500, detail="teanau_moana spot not found in SPOTS")

    spot = SPOTS[spot_id]

    # Pull daily weather from Open-Meteo
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

    # 👉 Moana-specific scoring here
    daily = data.get("daily", {})
    day_summaries = build_moana_day_summaries(daily)

    # For an expedition we want at least a 2-day window of 'good' or better.
    windows = find_multi_day_windows(
        day_summaries,
        min_length=2,
        min_label="good",
    )
    best_window = choose_best_window(windows)

    # Turn that into a simple verdict
    if best_window is None:
        verdict = "no-window"
        reason = (
            "No 2+ day stretch of genuinely good/excellent boating weather in this period. "
            "Not worth planning a Te Anau mission from Wanaka."
        )
    else:
        length = best_window["length"]
        start = best_window["start_date"]
        end = best_window["end_date"]
        avg_score = round(best_window["avg_score"])

        if length >= 3 and avg_score >= 80:
            verdict = "go"
            reason = (
                f"{length}-day window ({start} → {end}) with strong scores "
                f"(avg ~{avg_score}). Ideal for a Te Anau / Moana mission."
            )
        elif length >= 2 and avg_score >= 80:
            verdict = "maybe-go"
            reason = (
                f"Solid {length}-day window ({start} → {end}) with good boating weather "
                f"(avg score ~{avg_score}). Worth considering if you're keen."
            )
        else:
            verdict = "hold"
            reason = (
                f"There is a {length}-day stretch ({start} → {end}), but quality is only "
                f"average (avg score ~{avg_score}). Better to wait for a cleaner window."
            )

    return {
        "spot_id": spot_id,
        "spot_name": spot["name"],
        "days_considered": days,
        "verdict": verdict,      # "go" | "maybe-go" | "hold" | "no-window"
        "reason": reason,
        "best_window": best_window,
        "days": day_summaries,   # raw per-day scores
    }


# ---------- Hunter via Lake Hawea ----------


@app.get("/api/hunter_expedition")
async def hunter_expedition(days: int = 10):
    """
    Decide if there's a worthwhile Hawea → Hunter mission window
    in the next N days.

    Notes:
      - This can be a one-day hit-and-run (there and back in a day).
      - We still prefer 2+ day windows if they exist, but a single
        really good day is enough to green-light a Hunter mission.
    """
    if days < 1 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 1 and 10")

    # We'll treat Timaru Creek & Township as candidate launch zones
    lake_spot_ids = ["hawea_timaru", "hawea_township"]
    fishing_spot_id = "hunter_confluence"

    for sid in lake_spot_ids + [fishing_spot_id]:
        if sid not in SPOTS:
            raise HTTPException(status_code=500, detail=f"spot '{sid}' not found in SPOTS")

    async def fetch_lake_plan(spot_id: str) -> Dict[str, Any]:
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

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, timeout=10)
            resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        day_summaries = build_boating_day_summaries(daily)

        # IMPORTANT CHANGE:
        # Allow 1-day windows of "good" or better for hit-and-run missions.
        windows = find_multi_day_windows(
            day_summaries,
            min_length=1,      # was 2 before
            min_label="good",  # only care about "good" or better
        )
        best_window = choose_best_window(windows)

        return {
            "spot_id": spot_id,
            "spot_name": spot["name"],
            "days": day_summaries,
            "windows": windows,
            "best_window": best_window,
        }

    # Get lake plans for Timaru & Township
    lake_plans = []
    for sid in lake_spot_ids:
        lake_plans.append(await fetch_lake_plan(sid))

    # Choose the better of the two lake options based on best_window
    best_lake_plan = None
    for plan in lake_plans:
        bw = plan["best_window"]
        if bw is None:
            continue
        if best_lake_plan is None:
            best_lake_plan = plan
        else:
            current = plan["best_window"]
            chosen = best_lake_plan["best_window"]
            if (
                current["length"] > chosen["length"]
                or (
                    current["length"] == chosen["length"]
                    and current["avg_score"] > chosen["avg_score"]
                )
            ):
                best_lake_plan = plan

    # No good days at all
    if best_lake_plan is None:
        verdict = "no-window"
        reason = (
            "No 'good' or better day on Lake Hawea in this period. "
            "Not worth planning a Hunter mission from Wanaka."
        )
        return {
            "lake_options": lake_plans,
            "fishing_spot_id": fishing_spot_id,
            "fishing_spot_name": SPOTS[fishing_spot_id]["name"],
            "days_considered": days,
            "verdict": verdict,
            "reason": reason,
            "chosen_lake_spot_id": None,
            "chosen_lake_spot_name": None,
            "best_window": None,
        }

    # We have at least one 'good' or better window (length can be 1+)
    bw = best_lake_plan["best_window"]
    length = bw["length"]
    start = bw["start_date"]
    end = bw["end_date"]
    avg_score = round(bw["avg_score"])

    # Verdict logic – now supports 1-day hit-and-run
    if length >= 2 and avg_score >= 80:
        verdict = "go"
        reason = (
            f"{length}-day window on Lake Hawea ({start} → {end}) with strong scores "
            f"(avg ~{avg_score}). Great for a Hunter mission with the option to stay over."
        )
    elif length == 1 and avg_score >= 80:
        verdict = "go"
        reason = (
            f"One standout day on Lake Hawea ({start}) with strong conditions "
            f"(score ~{avg_score}). Ideal for a hit-and-run Hunter mission."
        )
    elif length == 1 and avg_score >= 60:
        verdict = "maybe-go"
        reason = (
            f"One decent day on Lake Hawea ({start}) (score ~{avg_score}). "
            "OK for a quick Hunter blast if you're keen and flexible."
        )
    else:
        verdict = "hold"
        reason = (
            f"There is a {length}-day stretch on Hawea ({start} → {end}), "
            f"but quality is only average (score ~{avg_score}). "
            "Better to wait for a cleaner Hunter window."
        )

    return {
        "lake_options": lake_plans,
        "fishing_spot_id": fishing_spot_id,
        "fishing_spot_name": SPOTS[fishing_spot_id]["name"],
        "days_considered": days,
        "verdict": verdict,  # "go" | "maybe-go" | "hold" | "no-window"
        "reason": reason,
        "chosen_lake_spot_id": best_lake_plan["spot_id"],
        "chosen_lake_spot_name": best_lake_plan["spot_name"],
        "best_window": bw,
    }


# ---------- Waikaia camping / fishing ----------


def score_waikaia_day(wind_kmh: float, rain_mm: float) -> Dict[str, Any]:
    """
    Very simple Waikaia scoring for now:
    - Big rain or big wind = no-go
    - Light wind and low rain = good
    """
    # Hard no: properly wet or properly howling
    if rain_mm >= 15 or wind_kmh >= 40:
        return {
            "score": 10,
            "label": "no-go",
            "reason": "Wet or windy enough that you’ll regret the trip.",
        }

    # Good: light / moderate breeze, small rain
    if wind_kmh <= 20 and rain_mm <= 5:
        return {
            "score": 75,
            "label": "good",
            "reason": "Decent conditions – fine for camping and river time.",
        }

    # Ok but a bit grim
    if wind_kmh <= 30 and rain_mm <= 10:
        return {
            "score": 60,
            "label": "ok",
            "reason": "Moderate breeze or some rain — still workable.",
        }

    # Marginal in between
    return {
        "score": 40,
        "label": "marginal",
        "reason": "Fresh wind or steady rain — campsite will get damp, river visibility drops.",
    }


@app.get("/api/waikaia_trip")
async def waikaia_trip(days: int = 7):
    """
    Look for a Waikaia camping/fishing window in the next N days.
    """
    if days < 1 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 1 and 10")

    spot_id = "waikaia_piano_flat"
    if spot_id not in SPOTS:
        raise HTTPException(status_code=500, detail="waikaia_piano_flat spot not found")

    spot = SPOTS[spot_id]

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

    day_summaries: List[Dict[str, Any]] = []
    for i, date_str in enumerate(times):
        try:
            w = float(winds[i])
            r = float(rain[i])
        except (IndexError, ValueError):
            continue

        scored = score_waikaia_day(w, r)
        day_summaries.append(
            {
                "date": date_str,
                "wind_kmh": w,
                "rain_mm": r,
                "score": scored["score"],
                "label": scored["label"],
                "reason": scored["reason"],
            }
        )

    # Look for 2+ days of 'good' or better
    windows = find_multi_day_windows(day_summaries, min_length=2, min_label="good")
    best_window = choose_best_window(windows)

    if best_window is None:
        verdict = "no-window"
        reason = "No multi-day Waikaia window worth camping/fishing."
    else:
        length = best_window["length"]
        start = best_window["start_date"]
        end = best_window["end_date"]
        avg_score = round(best_window["avg_score"])
        if length >= 3 and avg_score >= 75:
            verdict = "go"
            reason = (
                f"{length}-day Waikaia window ({start} → {end}) with solid conditions "
                f"(avg ~{avg_score})."
            )
        elif length >= 2 and avg_score >= 70:
            verdict = "maybe-go"
            reason = (
                f"{length}-day Waikaia window ({start} → {end}) looks reasonable "
                f"(avg ~{avg_score}). Worth a crack if you’re keen."
            )
        else:
            verdict = "hold"
            reason = (
                f"There is a {length}-day stretch ({start} → {end}), but it’s only average "
                f"(avg ~{avg_score})."
            )

    return {
        "spot_id": spot_id,
        "spot_name": spot["name"],
        "days_considered": days,
        "days": day_summaries,
        "verdict": verdict,
        "reason": reason,
        "windows": windows,
        "best_window": best_window,
    }


# ---------- Daily “What should Carl do?” briefing ----------


@app.get("/api/daily_briefing")
async def daily_briefing(days: int = 10):
    """
    High-level "What should Carl do?" planner.

    Checks:
      - Te Anau / Moana expedition
      - Hunter mission via Lake Hawea
      - Waikaia camping/fishing

    Returns one best option + the raw plans.
    """
    if days < 2 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 2 and 10")

    # Call the internal route handlers directly instead of hitting our own HTTP API
    teanau = await teanau_expedition(days=days)
    hunter = await hunter_expedition(days=days)
    waikaia = await waikaia_trip(days=min(days, 7))

    def verdict_rank(verdict: str) -> int:
        order = {
            "go": 3,
            "maybe-go": 2,
            "hold": 1,
            "no-window": 0,
        }
        return order.get(verdict, 0)

    options = [
        {
            "id": "teanau_expedition",
            "kind": "boating",
            "label": "Te Anau / Moana mission",
            "data": teanau,
            "rank": verdict_rank(teanau.get("verdict", "no-window")),
        },
        {
            "id": "hunter_expedition",
            "kind": "boating+fishing",
            "label": "Hunter via Lake Hawea",
            "data": hunter,
            "rank": verdict_rank(hunter.get("verdict", "no-window")),
        },
        {
            "id": "waikaia_trip",
            "kind": "camping+fishing",
            "label": "Waikaia – Piano Flat camping/fishing",
            "data": waikaia,
            "rank": verdict_rank(waikaia.get("verdict", "no-window")),
        },
    ]

    best = max(options, key=lambda o: o["rank"])

    if best["rank"] == 0:
        summary = (
            "No decent multi-day windows for Te Anau, Hunter or Waikaia in this period. "
            "Best move is to stay home, tie flies, or muck around on the local lakes."
        )
    else:
        v = best["data"].get("verdict")
        reason = best["data"].get("reason", "")
        if best["id"] == "teanau_expedition":
            summary = f"Best play is Te Anau / Moana: verdict '{v}'. {reason}"
        elif best["id"] == "hunter_expedition":
            summary = f"Best play is a Hunter mission via Lake Hawea: verdict '{v}'. {reason}"
        else:
            summary = f"Best play is a Waikaia camping/fishing trip: verdict '{v}'. {reason}"

    return {
        "days_considered": days,
        "summary": summary,
        "teanau": teanau,
        "hunter": hunter,
        "waikaia": waikaia,
        "best_option": {
            "id": best["id"],
            "label": best["label"],
            "verdict": best["data"].get("verdict"),
            "reason": best["data"].get("reason"),
        },
    }


# ---------- Generic forecast endpoint for the UI ----------


@app.post("/api/forecast", response_model=ForecastResponse)
async def get_forecast(payload: ForecastRequest):
    """
    Main endpoint the UI will hit.
    """
    if payload.spot_id not in SPOTS:
        raise HTTPException(status_code=404, detail="Unknown spot_id")

    spot = SPOTS[payload.spot_id]
    lat = spot["lat"]
    lon = spot["lon"]
    timezone = spot.get("timezone", "Pacific/Auckland")

    # 1. Fetch raw weather
    weather = await fetch_weather(lat, lon, payload.days, timezone)

    # 2. Build prompt for the model
    prompt = build_openai_prompt(
        spot_name=spot["name"],
        days=payload.days,
        tone=payload.tone,
        detail_level=payload.detail_level,
        wind_sensitive=payload.wind_sensitive,
        weather=weather,
    )

    # 3. Get narrative from OpenAI
    narrative = summarise_weather_with_ai(prompt)

    return ForecastResponse(
        spot_name=spot["name"],
        days=payload.days,
        raw_weather=weather,
        narrative=narrative,
    )


# ---------- Boating plan preview across lakes ----------


@app.get("/api/boating_plan_preview")
async def boating_plan_preview(days: int = 7):
    """
    Preview boating conditions for the next N days across key spots.

    Bias:
      - Te Anau / Moana berth is primary.
      - Hunter access via Lake Hawea is secondary.
      - Other boating lakes are treated as backup suggestions.
    """
    if days < 1 or days > 10:
        raise HTTPException(status_code=400, detail="days must be between 1 and 10")

    # Primary + secondary boating spots
    primary_id = "teanau_moana"
    hunter_ids = ["hawea_timaru", "hawea_township"]
    other_boat_spots = [
        sid
        for sid, s in SPOTS.items()
        if "boating" in (s.get("types") or [])
        and sid not in [primary_id, *hunter_ids]
    ]

    async def fetch_daily_for_spot(spot_id: str) -> Dict[str, Any]:
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
        async with httpx.AsyncClient() as client_http:
            resp = await client_http.get(url, params=params, timeout=10)
            resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        day_summaries = build_moana_day_summaries(daily)
        windows = find_multi_day_windows(day_summaries, min_length=2, min_label="good")
        return {
            "spot_id": spot_id,
            "spot_name": spot["name"],
            "days": day_summaries,
            "good_windows": windows,
        }

    results: Dict[str, Any] = {}

    # Primary: Te Anau / Moana
    if primary_id in SPOTS:
        results["primary"] = await fetch_daily_for_spot(primary_id)

    # Hunter access options
    hunter_results: List[Dict[str, Any]] = []
    for sid in hunter_ids:
        if sid in SPOTS:
            hunter_results.append(await fetch_daily_for_spot(sid))
    results["hunter_options"] = hunter_results

    # Other boating lakes as backup
    backup_results: List[Dict[str, Any]] = []
    for sid in other_boat_spots:
        backup_results.append(await fetch_daily_for_spot(sid))
    results["other_boating_spots"] = backup_results

    return results