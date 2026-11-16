"""Constants for Resource Queue Manager (FIFO)."""

DOMAIN = "resource_queue_manager"
CONF_MAX_ACTIVE = "max_active"
DEFAULT_MAX_ACTIVE = 3
CONF_MONITORED_ENTITIES = "monitored_entities"

ATTR_RESOURCE_ID = "resource_id"
ATTR_ENTITY_ID = "entity_id"
SERVICE_REQUEST = "request"
SERVICE_RELEASE = "release"
SERVICE_CANCEL = "cancel"
SERVICE_RESUME = "resume"

SIGNAL_QUEUE_UPDATED = f"{DOMAIN}_queue_updated"
EVENT_SLOT_GRANTED = f"{DOMAIN}_slot_granted"
