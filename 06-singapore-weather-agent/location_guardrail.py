"""
Location-consent guardrail for the Singapore Weather Agent.

The agent may use the user's current location, but only after the user confirms each
request. Bedrock Guardrails filter text and can't pause a turn to ask the user, so this
guardrail is enforced in code:

1. The agent calls `get_current_location`. With no approval, the tool returns
   `consent_required` and the request becomes *pending*. The agent then asks the user
   to confirm, and the web UI shows an Allow / Don't allow prompt.
2. Coordinates are accepted only while a request is pending, and only from the UI's
   Allow action (`LocationConsent.grant`). Unsolicited coordinates are rejected.
3. One approval covers one lookup. The coordinates are used once, then discarded, so the
   next lookup asks again.
4. Data minimisation: the model only receives the nearest NEA town and PSI region, never
   the raw coordinates. Positions outside Singapore are not resolved.
"""

from __future__ import annotations

import json
import math
import threading
from typing import Any

from strands import tool

import nea_data

# Generous bounding box around Singapore (main island, Jurong Island, Pulau Ubin, Sentosa).
SG_LAT = (1.15, 1.48)
SG_LON = (103.59, 104.10)

LOCATION_INSTRUCTIONS = """Current location (consent required):
- When the user asks about weather or haze "here", "near me", "where I am" or at their current location, call get_current_location straight away. Don't ask for permission yourself first: calling the tool is what shows the user the confirmation prompt, and it returns nothing until they approve. Never call it for any other reason.
- If it returns status "consent_required", ask the user, in one or two sentences, to confirm using the location prompt shown in the app. Then stop. Don't guess their location and don't call other tools for a guessed place. If the user says yes in chat, call get_current_location again.
- If it returns status "denied" or "unavailable", respect that. Don't ask for their location again unless they ask you to use it, and offer to use a town name instead.
- If it returns status "ok", answer for the returned town and region using the normal tools. Refer to their location only by that town name, and never state or estimate coordinates or a street address."""


class LocationConsent:
    """Per-conversation consent gate: idle -> pending -> granted/denied -> (used) -> idle."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "idle"
        self._coords: tuple[float, float] | None = None

    @property
    def pending(self) -> bool:
        return self.state == "pending"

    def grant(self, lat: float, lon: float) -> bool:
        """Record the user's approval with their coordinates. Only valid for a pending request."""
        lat, lon = float(lat), float(lon)
        if not (math.isfinite(lat) and math.isfinite(lon)):
            raise ValueError("invalid coordinates")
        with self._lock:
            if self.state != "pending":
                return False
            self.state, self._coords = "granted", (lat, lon)
            return True

    def deny(self) -> bool:
        with self._lock:
            if self.state != "pending":
                return False
            self.state, self._coords = "denied", None
            return True

    def reset(self) -> None:
        with self._lock:
            self.state, self._coords = "idle", None

    def lookup(self) -> dict[str, Any]:
        """What the agent's tool returns. Consumes an approval, so each lookup needs a fresh one."""
        with self._lock:
            state, coords = self.state, self._coords
            if state in ("granted", "denied"):
                self.state, self._coords = "idle", None  # one approval = one lookup
            else:
                self.state = "pending"
        if state == "denied":
            return {"status": "denied", "message": "The user declined to share their current location."}
        if state != "granted" or coords is None:
            return {
                "status": "consent_required",
                "message": "The user hasn't approved location access for this request. The app is showing "
                "them a confirmation prompt. Ask them to confirm, then stop.",
            }
        return resolve_location(*coords)


def resolve_location(lat: float, lon: float) -> dict[str, Any]:
    """Map coordinates to the nearest NEA 2-hour-forecast town and PSI region (coordinates not returned)."""
    if not (SG_LAT[0] <= lat <= SG_LAT[1] and SG_LON[0] <= lon <= SG_LON[1]):
        return {"status": "unavailable", "message": "The user's location is outside Singapore, so NEA data doesn't cover it."}
    try:
        areas = [(a["name"], a["label_location"]) for a in nea_data.fetch("two-hr-forecast")["area_metadata"]]
        regions = [(r["name"], r["labelLocation"]) for r in nea_data.fetch("psi")["regionMetadata"]]
    except Exception as e:
        return {"status": "unavailable", "message": f"Couldn't match the location to an NEA area: {e}"}

    def nearest(points):
        coslat = math.cos(math.radians(lat))
        return min(points, key=lambda p: (p[1]["latitude"] - lat) ** 2 + ((p[1]["longitude"] - lon) * coslat) ** 2)[0]

    return {
        "status": "ok",
        "nearest_town": nearest(areas),
        "region": nearest(regions),
        "note": "Approximate location: the nearest NEA forecast town to the user. Use these names with the forecast and haze tools.",
    }


def make_location_tool(consent: LocationConsent):
    @tool
    def get_current_location() -> str:
        """Get the user's approximate current location in Singapore (nearest NEA town and region).

        Requires the user's confirmation every time. Call it only when the user asks about
        weather or haze "here", "near me" or at their current location.
        """
        return json.dumps(consent.lookup(), ensure_ascii=False)

    return get_current_location
