"""Reads the stay in progress from the Stays AppDaemon app's HA sensor."""
from datetime import datetime

from bdh_sdk import Stay
from bdh_sdk.ha import get_entity_state
from bdh_sdk.settings import app_setting

DEFAULT_ENTITY = "sensor.bdl_stay_current"
NO_STAY = "none"
# HA reports these when AppDaemon hasn't (re)published the sensor. Treat them
# as a failed lookup so the hub keeps the last known stay instead of
# dropping a guest back to the dashboard.
UNKNOWN = {"unknown", "unavailable", ""}


def entity():
    return app_setting("stays", "entity", DEFAULT_ENTITY)


def _when(value):
    if not value:
        return None
    try:
        when = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return when if when.tzinfo else None


def current_stay():
    entity_id = entity()
    state = get_entity_state(entity_id)
    if not isinstance(state, dict):
        raise RuntimeError(f"couldn't read {entity_id} from Home Assistant")
    value = state.get("state")
    value = value.strip() if isinstance(value, str) else ""
    if value.lower() in UNKNOWN:
        raise RuntimeError(f"{entity_id} is {value or 'empty'}")
    if value.lower() == NO_STAY:
        return None
    attrs = state.get("attributes") or {}
    return Stay(
        guest=str(attrs.get("guest") or value),
        arrival=_when(attrs.get("arrival")),
        checkout=_when(attrs.get("checkout")),
    )
