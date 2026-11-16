"""Constants for Heating Queue Manager."""

DOMAIN = "heating_queue_manager"
CONF_MAX_ACTIVE = "max_active"
DEFAULT_MAX_ACTIVE = 3

ATTR_HEATER_ID = "heater_id"
ATTR_RELAY_ENTITY_ID = "relay_entity_id"
SERVICE_REQUEST = "request"
SERVICE_RELEASE = "release"
SERVICE_CANCEL = "cancel"
SERVICE_RESUME = "resume"

SIGNAL_QUEUE_UPDATED = f"{DOMAIN}_queue_updated"
EVENT_SLOT_GRANTED = f"{DOMAIN}_slot_granted"
