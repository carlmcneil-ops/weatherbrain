import os
from typing import Dict, Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

from spots import SPOTS  # expects a dict like {"wanaka": {"name": "...", "lat": ..., "lon": ..., "timezone": "..."}}

# ------------- OpenAI client -------------

# Make sure OPENAI_API_KEY is set in your environment before running:
# export OPENAI_API_KEY="sk-xxxxx"
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

client = OpenAI()

# ------------- FastAPI app -------------

app = FastAPI(title="Fishing Weather Bot")

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


@app.get("/health")
async def health_check():
    return {"status": "ok"}


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
