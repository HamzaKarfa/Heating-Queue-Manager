"""Constants for Resource Queue Manager."""

DOMAIN = "resource_queue_manager"
CONF_MAX_ACTIVE = "max_active"
CONF_NAME = "name"
CONF_STRATEGY = "strategy"
CONF_STRATEGY_CONFIG = "strategy_config"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
DEFAULT_MAX_ACTIVE = 3
CONF_MONITORED_ENTITIES = "monitored_entities"

ATTR_RESOURCE_ID = "resource_id"
ATTR_ENTITY_ID = "entity_id"
ATTR_STRATEGY_DATA = "strategy_data"
SERVICE_REQUEST = "request"
SERVICE_RELEASE = "release"
SERVICE_CANCEL = "cancel"
SERVICE_RESUME = "resume"

SIGNAL_QUEUE_UPDATED = f"{DOMAIN}_queue_updated"
EVENT_SLOT_GRANTED = f"{DOMAIN}_slot_granted"
