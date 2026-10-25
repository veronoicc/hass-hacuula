"""Constants for the Vacuula integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "vacuula"

# Configuration options
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEFAULT_MODE = "default_mode"
CONF_DEFAULT_NAV_MODE = "default_nav_mode"

DEFAULT_PORT = 80
DEFAULT_PORT_SSL = 443
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_MODE = "turbo"
DEFAULT_NAV_MODE = "normal"

# Cleaning and navigation mode choices
MODE_ECO = "eco"
MODE_TURBO = "turbo"
CLEANING_MODES = [MODE_TURBO, MODE_ECO]

NAV_MODE_NORMAL = "normal"
NAV_MODE_EXTRA_CARE = "extra_care"
NAV_MODE_DEEP = "deep"
NAV_MODE_GENTLE = "gentle"
NAVIGATION_MODES = [
    NAV_MODE_NORMAL,
    NAV_MODE_EXTRA_CARE,
    NAV_MODE_DEEP,
    NAV_MODE_GENTLE,
]

GEN3_NAV_MODES = [NAV_MODE_NORMAL, NAV_MODE_EXTRA_CARE, NAV_MODE_DEEP]
GEN4_NAV_MODES = [NAV_MODE_NORMAL, NAV_MODE_GENTLE]

CLEAN_CATEGORY_MAP = "map"
CLEAN_CATEGORY_HOUSE = "house"
GEN3_CLEAN_CATEGORIES = [CLEAN_CATEGORY_MAP, CLEAN_CATEGORY_HOUSE]

ALL_ZONES_OPTION = "all"

# Supported platforms
PLATFORMS: list[Platform] = [
    Platform.VACUUM,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.IMAGE,
]

# Dispatcher signals
SIGNAL_NEW_ROBOT = f"{DOMAIN}_new_robot_{{}}"

# Services
SERVICE_CLEAN_ZONE = "clean_zone"
SERVICE_CLEAN_ZONES = "clean_zones"
SERVICE_CLEAN_SPOT = "clean_spot"
SERVICE_REFRESH_MAPS = "refresh_maps"
SERVICE_DISMISS_ALERT = "dismiss_alert"
SERVICE_SEND_RAW_COMMAND = "send_raw_command"

ATTR_SERIAL = "serial"
ATTR_MAP_NAME = "map_name"
ATTR_ZONE_NAME = "zone_name"
ATTR_ZONES = "zones"
ATTR_MAP_ID = "map_id"
ATTR_FAN_SPEED = "fan_speed"
ATTR_WIDTH = "width"
ATTR_HEIGHT = "height"
ATTR_MODE = "mode"
ATTR_NAV_MODE = "navigation_mode"
ATTR_COMMAND = "command"
ATTR_PARAMS = "params"
