"""
Client + parsers for NEA's official real-time open data (data.gov.sg v2 API).

These are the data feeds the Weather Agent's tools read from. Everything here
is plain Python (no LLM) so it can be unit-tested offline with fixtures.

Endpoints (all published by NEA / Meteorological Service Singapore):
  two-hr-forecast, twenty-four-hr-forecast, four-day-outlook, psi, pm25
"""

from __future__ import annotations

import difflib
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable

# Standard library only, so this module ships unchanged inside the Gateway Lambda.

BASE_URL = "https://api-open.data.gov.sg/v2/real-time/api"
REGIONS = ["north", "south", "east", "west", "central"]
CACHE_TTL_SECONDS = 60
MAX_RETRIES = 5

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()


class NEADataError(RuntimeError):
    """Raised when an NEA feed cannot be fetched or parsed."""


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _urllib_get(url: str, headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:  # 4xx/5xx still carry a JSON body
        return e.code, json.loads(e.read() or b"{}")


def fetch(
    endpoint: str,
    *,
    http_get: Callable[[str, dict[str, str]], tuple[int, dict[str, Any]]] = _urllib_get,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Fetch a data.gov.sg real-time endpoint and return its `data` payload.

    Cached for CACHE_TTL_SECONDS. Retries on rate limiting (HTTP 429 or API
    code 24) with backoff. Set DATA_GOV_SG_API_KEY for higher rate limits.

    Replay mode: if NEA_REPLAY_DIR is set, the payload is read from
    <dir>/<endpoint>.json instead (used to evaluate recorded/scenario conditions).
    """
    if replay_dir := os.environ.get("NEA_REPLAY_DIR"):
        with open(os.path.join(replay_dir, f"{endpoint}.json"), encoding="utf-8") as f:
            return json.load(f)["data"]

    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(endpoint)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]

    headers = {"User-Agent": "sg-weather-agent/1.0"}
    if api_key := os.environ.get("DATA_GOV_SG_API_KEY"):
        headers["x-api-key"] = api_key

    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            status, body = http_get(f"{BASE_URL}/{endpoint}", headers)
        except (OSError, ValueError) as e:
            last_error = f"{type(e).__name__}: {e}"
            sleep(2 * (attempt + 1))
            continue

        if status == 429 or body.get("code") == 24:
            last_error = body.get("errorMsg") or "rate limited"
            sleep(10 + 2 * attempt)  # API asks callers to wait ~10s
            continue
        if status != 200 or body.get("code") != 0 or body.get("data") is None:
            raise NEADataError(f"{endpoint}: HTTP {status}, {body.get('errorMsg') or body}")

        with _cache_lock:
            _cache[endpoint] = (time.monotonic(), body["data"])
        return body["data"]

    raise NEADataError(f"{endpoint}: failed after {MAX_RETRIES} attempts ({last_error})")


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


# --------------------------------------------------------------------------- #
# NEA classification bands
# --------------------------------------------------------------------------- #
# 24-hr PSI descriptors and health advisory, per NEA (haze.gov.sg).
PSI_BANDS = [
    (50, "Good"),
    (100, "Moderate"),
    (200, "Unhealthy"),
    (300, "Very Unhealthy"),
    (math.inf, "Hazardous"),
]

PSI_ADVISORY = {
    "Good": "Normal activities for everyone.",
    "Moderate": "Normal activities for everyone.",
    "Unhealthy": (
        "Healthy persons: reduce prolonged or strenuous outdoor physical exertion. "
        "Elderly, pregnant women, children: minimise prolonged or strenuous outdoor exertion. "
        "Persons with chronic lung or heart disease: avoid prolonged or strenuous outdoor exertion."
    ),
    "Very Unhealthy": (
        "Healthy persons: avoid prolonged or strenuous outdoor physical exertion. "
        "Elderly, pregnant women, children: minimise outdoor activity. "
        "Persons with chronic lung or heart disease: avoid outdoor activity."
    ),
    "Hazardous": (
        "Healthy persons: minimise outdoor activity. "
        "Elderly, pregnant women, children and persons with chronic lung or heart disease: avoid outdoor activity."
    ),
}

# 1-hr PM2.5 concentration bands (µg/m³), per NEA.
PM25_BANDS = [
    (55, "Band I (Normal)"),
    (150, "Band II (Elevated)"),
    (250, "Band III (High)"),
    (math.inf, "Band IV (Very High)"),
]


def psi_descriptor(value: float) -> str:
    return next(label for upper, label in PSI_BANDS if value <= upper)


def pm25_band(value: float) -> str:
    return next(label for upper, label in PM25_BANDS if value <= upper)


# --------------------------------------------------------------------------- #
# Parsers (raw `data` payload -> compact dict for the LLM)
# --------------------------------------------------------------------------- #
def _match_area(query: str, areas: list[str]) -> str | None:
    q = query.strip().lower()
    by_lower = {a.lower(): a for a in areas}
    if q in by_lower:
        return by_lower[q]
    partial = [a for a in areas if q in a.lower() or a.lower() in q]
    if len(partial) == 1:
        return partial[0]
    close = difflib.get_close_matches(q, list(by_lower), n=1, cutoff=0.75)
    return by_lower[close[0]] if close else None


def parse_two_hour(data: dict[str, Any], area: str = "") -> dict[str, Any]:
    item = data["items"][0]
    forecasts = {f["area"]: f["forecast"] for f in item["forecasts"]}
    vp = item.get("valid_period", {})
    out: dict[str, Any] = {
        "source": "NEA 2-hour nowcast (data.gov.sg two-hr-forecast)",
        "issued_at": item.get("timestamp") or item.get("update_timestamp"),
        "valid_period": vp.get("text") or f"{vp.get('start')} to {vp.get('end')}",
    }
    if area:
        match = _match_area(area, list(forecasts))
        if match is None:
            out["error"] = f"Area '{area}' not found."
            out["available_areas"] = sorted(forecasts)
            return out
        out["area"] = match
        out["forecast"] = forecasts[match]
        return out

    summary: dict[str, list[str]] = {}
    for name, fc in sorted(forecasts.items()):
        summary.setdefault(fc, []).append(name)
    out["areas_by_forecast"] = summary
    out["area_count"] = len(forecasts)
    return out


def parse_24_hour(data: dict[str, Any]) -> dict[str, Any]:
    rec = data["records"][0]
    g = rec["general"]
    return {
        "source": "NEA 24-hour forecast (data.gov.sg twenty-four-hr-forecast)",
        "issued_at": rec.get("updatedTimestamp") or rec.get("timestamp"),
        "valid_period": g["validPeriod"]["text"],
        "general": {
            "forecast": g["forecast"]["text"],
            "temperature_c": {"low": g["temperature"]["low"], "high": g["temperature"]["high"]},
            "relative_humidity_pct": {"low": g["relativeHumidity"]["low"], "high": g["relativeHumidity"]["high"]},
            "wind": {
                "direction": g["wind"]["direction"],
                "speed_kmh": f"{g['wind']['speed']['low']} - {g['wind']['speed']['high']}",
            },
        },
        "periods": [
            {
                "period": p["timePeriod"]["text"],
                "regions": {r: v["text"] for r, v in p["regions"].items()},
            }
            for p in rec["periods"]
        ],
    }


def parse_four_day(data: dict[str, Any]) -> dict[str, Any]:
    rec = data["records"][0]
    return {
        "source": "NEA 4-day outlook (data.gov.sg four-day-outlook)",
        "issued_at": rec.get("updatedTimestamp"),
        "days": [
            {
                "day": f["day"],
                "date": (f.get("timestamp") or "")[:10],
                "forecast": f["forecast"]["summary"] or f["forecast"]["text"],
                "temperature_c": {"low": f["temperature"]["low"], "high": f["temperature"]["high"]},
                "relative_humidity_pct": {"low": f["relativeHumidity"]["low"], "high": f["relativeHumidity"]["high"]},
                "wind": {
                    "direction": f["wind"]["direction"],
                    "speed_kmh": f"{f['wind']['speed']['low']} - {f['wind']['speed']['high']}",
                },
            }
            for f in rec["forecasts"]
        ],
    }


def parse_haze(psi_data: dict[str, Any], pm25_data: dict[str, Any], region: str = "") -> dict[str, Any]:
    psi_item = psi_data["items"][0]
    pm_item = pm25_data["items"][0]
    psi24 = psi_item["readings"]["psi_twenty_four_hourly"]
    pm1h = pm_item["readings"]["pm25_one_hourly"]

    regions = REGIONS
    if region:
        r = region.strip().lower()
        if r not in REGIONS:
            return {"error": f"Region '{region}' not recognised.", "available_regions": REGIONS}
        regions = [r]

    per_region = {}
    for r in regions:
        psi = psi24.get(r)
        pm = pm1h.get(r)
        per_region[r] = {
            "psi_24h": psi,
            "psi_descriptor": psi_descriptor(psi) if psi is not None else None,
            "pm25_1h_ugm3": pm,
            "pm25_band": pm25_band(pm) if pm is not None else None,
            "health_advisory": PSI_ADVISORY[psi_descriptor(psi)] if psi is not None else None,
        }

    all_psi = [v for v in psi24.values() if v is not None]
    psi_min, psi_max = min(all_psi), max(all_psi)
    worst = psi_descriptor(psi_max)
    return {
        "source": "NEA air quality (data.gov.sg psi, pm25)",
        "psi_as_of": psi_item.get("timestamp"),
        "pm25_as_of": pm_item.get("timestamp"),
        "national_psi_24h_range": f"{psi_min} - {psi_max}" if psi_min != psi_max else str(psi_min),
        "national_psi_descriptor": (
            psi_descriptor(psi_min) if psi_descriptor(psi_min) == worst else f"{psi_descriptor(psi_min)} to {worst}"
        ),
        "regions": per_region,
        "health_advisory_worst_region": PSI_ADVISORY[worst],
        "notes": (
            "Each region has its own health advisory based on its 24-hr PSI; use the region's advisory "
            "for location-specific questions. 24-hr PSI is NEA's reference for health advisories; 1-hr PM2.5 bands are for "
            "planning immediate activities. Hazy conditions are indicated by PSI > 100."
        ),
    }


# --------------------------------------------------------------------------- #
# Tool implementations shared by the local agent and the Gateway Lambda
# --------------------------------------------------------------------------- #
def get_two_hour_forecast(area: str = "") -> dict[str, Any]:
    return parse_two_hour(fetch("two-hr-forecast"), area)


def get_24_hour_forecast() -> dict[str, Any]:
    return parse_24_hour(fetch("twenty-four-hr-forecast"))


def get_four_day_outlook() -> dict[str, Any]:
    return parse_four_day(fetch("four-day-outlook"))


def get_haze_conditions(region: str = "") -> dict[str, Any]:
    return parse_haze(fetch("psi"), fetch("pm25"), region)


TOOL_IMPLS: dict[str, Callable[..., dict[str, Any]]] = {
    f.__name__: f for f in [get_two_hour_forecast, get_24_hour_forecast, get_four_day_outlook, get_haze_conditions]
}

# MCP tool schemas registered on the AgentCore Gateway target. Descriptions match the local @tool docstrings.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_two_hour_forecast",
        "description": "Get NEA's 2-hour weather nowcast for Singapore's ~47 towns/areas. "
        "Pass an area (e.g. Tampines, Jurong West) or leave empty for all areas grouped by condition.",
        "inputSchema": {"type": "object", "properties": {
            "area": {"type": "string", "description": "Optional town/area name. Empty = all areas."}}},
    },
    {
        "name": "get_24_hour_forecast",
        "description": "Get NEA's 24-hour forecast for Singapore: overall conditions, temperature range, relative "
        "humidity, wind, and per-region (north/south/east/west/central) forecasts for each time period.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_four_day_outlook",
        "description": "Get NEA's 4-day weather outlook for Singapore: daily forecast, temperature, humidity and wind.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_haze_conditions",
        "description": "Get current haze / air quality across Singapore: 24-hr PSI with NEA descriptor, 1-hr PM2.5 "
        "with NEA band per region, and NEA's health advisory.",
        "inputSchema": {"type": "object", "properties": {
            "region": {"type": "string", "description": "Optional: north, south, east, west or central. Empty = all."}}},
    },
]
