#!/usr/bin/env python3
"""Build the synthetic haze-episode replay scenario (tests/replay/haze_episode/).

SYNTHETIC: values are modelled on the scale of Singapore's Sept 2019 haze episode
but are NOT real NEA readings. The expected values are written literally below
and are used both to write the replayed API payloads and the evaluator's ground truth,
so the agent's parsing, banding and advice are tested against hand-specified values.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
FIX = HERE / "tests" / "fixtures"
OUT = HERE / "tests" / "replay" / "haze_episode"
TS = "2019-09-21T13:00:00+08:00"

PSI_24H = {"north": 168, "south": 182, "east": 151, "west": 214, "central": 196}
PM25_1H = {"north": 96, "south": 132, "east": 71, "west": 188, "central": 143}
TEMP = {"low": 25, "high": 33}
RH = {"low": 55, "high": 90}
HAZY_AREAS = {"City", "Jurong West", "Jurong East", "Boon Lay", "Tuas", "Clementi", "Bukit Merah", "Queenstown"}

def load(name):
    return json.loads((FIX / f"{name}.json").read_text())

OUT.mkdir(parents=True, exist_ok=True)

psi = load("psi")
item = psi["data"]["items"][0]
item.update(timestamp=TS, updatedTimestamp=TS, date=TS[:10])
item["readings"]["psi_twenty_four_hourly"] = PSI_24H
(OUT / "psi.json").write_text(json.dumps(psi, indent=1))

pm = load("pm25")
item = pm["data"]["items"][0]
item.update(timestamp=TS, updatedTimestamp=TS, date=TS[:10])
item["readings"]["pm25_one_hourly"] = PM25_1H
(OUT / "pm25.json").write_text(json.dumps(pm, indent=1))

two = load("two-hr-forecast")
it = two["data"]["items"][0]
it.update(timestamp=TS, update_timestamp=TS)
it["valid_period"] = {"start": TS, "end": "2019-09-21T15:00:00+08:00", "text": "1 to 3 pm"}
nowcast = {}
for f in it["forecasts"]:
    f["forecast"] = "Hazy" if f["area"] in HAZY_AREAS else "Slightly Hazy"
    nowcast[f["area"]] = f["forecast"]
(OUT / "two-hr-forecast.json").write_text(json.dumps(two, indent=1))

d24 = load("twenty-four-hr-forecast")
rec = d24["data"]["records"][0]
rec.update(updatedTimestamp="2019-09-21T11:30:00+08:00", timestamp="2019-09-21T11:30:00+08:00")
g = rec["general"]
g["forecast"] = {"code": "HZ", "text": "Hazy"}
g["temperature"] = {**TEMP, "unit": "Degrees Celsius"}
g["relativeHumidity"] = {**RH, "unit": "Percentage"}
g["validPeriod"]["text"] = "12 PM 21 Sep to 12 PM 22 Sep"
for p in rec["periods"]:
    p["regions"] = {r: {"code": "HZ", "text": "Hazy"} for r in PSI_24H}
(OUT / "twenty-four-hr-forecast.json").write_text(json.dumps(d24, indent=1))

d4 = load("four-day-outlook")
(OUT / "four-day-outlook.json").write_text(json.dumps(d4, indent=1))

gt = {
    "captured_at": "SYNTHETIC replay scenario (not real NEA readings)",
    "source_urls": ["synthetic: tests/replay/haze_episode"],
    "nowcast_2h": {"issued": "1.00pm 21 Sep", "valid": "1 to 3 pm", "areas": nowcast},
    "forecast_24h": {"issued": "11.30am 21 Sep", "valid": "12 PM 21 Sep - 12 PM 22 Sep",
                     "temp_low": TEMP["low"], "temp_high": TEMP["high"], "rh_low": RH["low"], "rh_high": RH["high"],
                     "wind": "SSW 5 - 15 km/h", "overall": "Hazy", "narrative": "Hazy conditions island-wide.",
                     "periods": [{"period": p["timePeriod"]["text"], "regions": {r: "Hazy" for r in PSI_24H}} for p in rec["periods"]]},
    "outlook_4day": [],
    "haze": {"as_of": "1pm on 21 Sep 2019 (synthetic)", "psi_24h": PSI_24H, "pm25_1h": PM25_1H},
    "haze_by_hour": {TS: {"psi_24h": PSI_24H, "pm25_1h": PM25_1H}},
}
(OUT / "ground_truth.json").write_text(json.dumps(gt, indent=1))
(OUT / "README.md").write_text("SYNTHETIC haze-episode scenario for replay evaluation. Values are modelled on the scale of "
                               "the Sept 2019 haze but are NOT real NEA readings. Regenerate with scripts/build_haze_scenario.py.\n")
print("wrote", sorted(p.name for p in OUT.iterdir()))
