"""
Ground truth scraped from NEA's public websites, used to evaluate the agent.

The agent reads NEA data via the data.gov.sg API; the evaluator independently
reads what NEA itself publishes on www.nea.gov.sg and www.haze.gov.sg (the JSON
endpoints those pages render from), so a parsing or reasoning bug in the agent
can't hide behind a shared data path.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

NEA = "https://www.nea.gov.sg"
HAZE = "https://www.haze.gov.sg"
SGT = timezone(timedelta(hours=8))

# NEA weather abbreviations (as used on nea.gov.sg) -> display text.
WEATHER_CODES = {
    "BR": "Mist", "CL": "Cloudy", "CR": "Drizzle", "FA": "Fair (Day)", "FG": "Fog",
    "FN": "Fair (Night)", "FW": "Fair & Warm", "HG": "Heavy Thundery Showers with Gusty Winds",
    "HR": "Heavy Rain", "HS": "Heavy Showers", "HT": "Heavy Thundery Showers", "HZ": "Hazy",
    "LH": "Slightly Hazy", "LR": "Light Rain", "LS": "Light Showers", "OC": "Overcast",
    "PC": "Partly Cloudy (Day)", "PN": "Partly Cloudy (Night)", "PS": "Passing Showers",
    "RA": "Moderate Rain", "SH": "Showers", "SK": "Strong Winds, Showers", "SN": "Snow",
    "SR": "Strong Winds, Rain", "SS": "Snow Showers", "SU": "Sunny", "SW": "Strong Winds",
    "TL": "Thundery Showers", "WC": "Windy, Cloudy", "WD": "Windy", "WF": "Windy, Fair",
    "WR": "Windy, Rain", "WS": "Windy, Showers",
}

DAY_NAMES = {
    "MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday",
    "FRI": "Friday", "SAT": "Saturday", "SUN": "Sunday",
}


def _get(url: str) -> Any:
    last = None
    for attempt in range(3):
        try:
            r = requests.get(
                f"{url}/{int(time.time())}",  # NEA endpoints take a cache-busting suffix
                headers={"User-Agent": "Mozilla/5.0 (sg-weather-agent-eval)"},
                timeout=20,
            )
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Could not fetch NEA ground truth {url}: {last}")


def _num(s: Any) -> int | None:
    m = re.search(r"-?\d+", str(s))
    return int(m.group()) if m else None


def parse_haze_history(haze: dict[str, Any]) -> dict[str, dict[str, dict[str, int]]]:
    """Hourly readings from haze.gov.sg charts, keyed by ISO hour in SGT.

    Note: on haze.gov.sg the chart keyed "ChartPM25" holds the 24-hr PSI series
    (it matches Map24HRPSI); "Chart1HRPM25" holds 1-hr PM2.5 concentrations.
    """
    out: dict[str, dict[str, dict[str, int]]] = {}
    for chart, key in [("ChartPM25", "psi_24h"), ("Chart1HRPM25", "pm25_1h")]:
        for region, series in haze.get(chart, {}).items():
            if not isinstance(series, dict) or "Data" not in series:
                continue
            for pt in series["Data"]:
                if pt.get("isMissing") or pt.get("isInvalid") or pt.get("value") is None:
                    continue
                hour = datetime.strptime(pt["dateTime"], "%d %b %Y %I%p").replace(tzinfo=SGT)
                out.setdefault(hour.isoformat(), {}).setdefault(key, {})[region.lower()] = int(round(pt["value"]))
    return out


def fetch_ground_truth() -> dict[str, Any]:
    fc = _get(f"{NEA}/api/WeatherForecast/forecast24hrnowcast2hrs")
    outlook = _get(f"{NEA}/api/Weather4DayOutlook/GetData")
    haze = _get(f"{HAZE}/api/airquality/jsondata")

    two = fc["Channel2HrForecast"]["Item"]
    main = fc["Channel24HrForecast"]["Main"]
    periods = fc["Channel24HrForecast"]["Forecasts"]

    def code(c: str) -> str:
        return WEATHER_CODES.get(c, c)

    four_day = []
    for d in outlook:
        temps = [int(x) for x in re.findall(r"\d+", d.get("temperature", ""))]
        four_day.append({
            "day": DAY_NAMES.get(d["day"].upper()[:3], d["day"]),
            "forecast": d["forecast"],
            "temp_low": min(temps) if temps else None,
            "temp_high": max(temps) if temps else None,
            "wind": d.get("wind_speed"),
        })

    return {
        "captured_at": datetime.now(SGT).isoformat(timespec="seconds"),
        "source_urls": [f"{NEA}/weather", f"{HAZE}/"],
        "nowcast_2h": {
            "issued": two["ForecastIssue"]["DateTimeStr"],
            "valid": two["ValidTime"],
            "areas": {a["Name"]: code(a["Forecast"]) for a in two["WeatherForecast"]["Area"]},
        },
        "forecast_24h": {
            "issued": main["ForecastIssue"]["DateTimeStr"],
            "valid": main["ValidTime"],
            "temp_low": _num(main["Temperature"]["Low"]),
            "temp_high": _num(main["Temperature"]["High"]),
            "rh_low": _num(main["RelativeHumidity"]["Low"]),
            "rh_high": _num(main["RelativeHumidity"]["High"]),
            "wind": f"{main['Wind']['Direction']} {main['Wind']['Speed']} km/h",
            "overall": code(main["Wxmain"]),
            "narrative": main.get("Forecast"),
            "periods": [
                {
                    "period": p["TimePeriod"],
                    "regions": {r: code(p[f"Wx{r}"]) for r in ["north", "south", "east", "west", "central"]},
                }
                for p in periods
            ],
        },
        "outlook_4day": four_day,
        "haze": {
            "as_of": haze.get("ChartAsOfDate"),
            "psi_24h": {r.lower(): _num(v["Value"]) for r, v in haze["Map24HRPSI"].items()},
            "pm25_1h": {r.lower(): _num(v["Value"]) for r, v in haze["Map1HRPM25"].items()},
        },
        "haze_by_hour": parse_haze_history(haze),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_ground_truth(), indent=2, ensure_ascii=False))
