"""The lodge card: who's here (or that nobody is), temperatures and problems.

Reads the Stays sensors, the bdl_modes executor's status and occupancy, and a
few temperatures from Home Assistant in a single request.
"""
import re
from datetime import timedelta

from django.utils import timezone

from bdh_sdk import INFO, ON, WARN, Card, Reading
from bdh_sdk.ha import get_all_states
from bdh_sdk.settings import app_setting

from .homepage import NO_STAY, UNKNOWN, _when, entity

DEFAULTS = {
    "next_entity": "sensor.bdl_stay_next",
    "modes_entity": "sensor.bdl_modes_status",
    "occupancy_entity": "input_select.bdl_occupancy",
    "hot_tub_entity": "sensor.hot_tub_current_temperature",
    # Rooms averaged into the "Inside" reading.
    "room_temperature_pattern": r"^sensor\..+_bdl_temperature$",
    "card_url": "vacation_mode",
}


def _setting(key):
    return app_setting("stays", key, DEFAULTS[key])


def _value(states, entity_id):
    state = states.get(entity_id) or {}
    value = state.get("state")
    return value.strip() if isinstance(value, str) else ""


def _attrs(states, entity_id):
    return (states.get(entity_id) or {}).get("attributes") or {}


def _stay(states, entity_id):
    value = _value(states, entity_id)
    if value.lower() in UNKNOWN or value.lower() == NO_STAY:
        return None
    attrs = _attrs(states, entity_id)
    return {
        "guest": str(attrs.get("guest") or value),
        "owner": bool(attrs.get("owner")),
        "arrival": _when(attrs.get("arrival")),
        "checkout": _when(attrs.get("checkout")),
    }


def _celsius(state):
    try:
        value = float(state.get("state"))
    except (TypeError, ValueError):
        return None
    unit = (state.get("attributes") or {}).get("unit_of_measurement", "")
    return (value - 32) / 1.8 if unit.endswith("F") else value


def _when_text(when):
    if when is None:
        return ""
    local = timezone.localtime(when)
    today = timezone.localdate()
    if local.date() == today:
        day = "today"
    elif local.date() == today + timedelta(days=1):
        day = "tomorrow"
    else:
        day = f"{local:%a %b} {local.day}"
    hour = f"{local:%I}".lstrip("0")
    minutes = f":{local:%M}" if local.minute else ""
    return f"{day}, {hour}{minutes} {local:%p}"


def _readings(states):
    pattern = re.compile(_setting("room_temperature_pattern"))
    rooms = [c for e, s in states.items() if pattern.match(e)
             if (c := _celsius(s)) is not None]
    readings = []
    if rooms:
        readings.append(Reading("Inside", round(sum(rooms) / len(rooms), 1), "C"))
    hot_tub = _celsius(states.get(_setting("hot_tub_entity")) or {})
    if hot_tub is not None:
        readings.append(Reading("Hot tub", round(hot_tub, 1), "C"))
    return tuple(readings)


def _header(states):
    """(title, detail, level) for the lodge's current state."""
    current = _stay(states, entity())
    if current:
        leaving = _when_text(current["checkout"])
        if current["owner"]:
            return "Welcome back", f"Leaving {leaving}" if leaving else "", INFO
        return (f"Welcome, {current['guest']}",
                f"Checkout {leaving}" if leaving else "", INFO)

    upcoming = _stay(states, _setting("next_entity"))
    occupancy = _value(states, _setting("occupancy_entity")).lower()
    if occupancy == "preheat":
        who = "your visit" if upcoming and upcoming["owner"] else \
            upcoming["guest"] if upcoming else "the next arrival"
        ready = _when_text(upcoming["arrival"]) if upcoming else ""
        return f"Preheating for {who}", f"Ready {ready}" if ready else "", ON

    if upcoming:
        who = "Owner visit" if upcoming["owner"] else upcoming["guest"]
        detail = f"Next: {who}, {_when_text(upcoming['arrival'])}"
    else:
        detail = "No upcoming stays"
    title = "Vacation mode" if occupancy == "away" else "Lodge empty"
    return title, detail, INFO


def lodge_card():
    states = {s["entity_id"]: s for s in get_all_states()}
    title, detail, level = _header(states)
    issues = _attrs(states, _setting("modes_entity")).get("issues") or []
    alerts = tuple(f"{issue}: didn't complete" for issue in issues)
    return Card(
        title=title,
        detail=detail,
        readings=_readings(states),
        alerts=alerts,
        url_name=_setting("card_url") or None,
        level=WARN if alerts else level,
    )
