"""Constants for TiMotion Desk."""

DOMAIN = "timotion_desk"

CONF_KEEP_CONNECTED = "keep_connected"
CONF_PRESETS = "presets"
CONF_PRESET_NAME = "name"
CONF_PRESET_HEIGHT = "height"

DEFAULT_KEEP_CONNECTED = True

# The module allows a single Bluetooth connection. When we do not keep the
# connection open, close it again after this many seconds without activity.
IDLE_DISCONNECT_SECONDS = 30.0
# Minimum time between automatic reconnect attempts.
RECONNECT_MIN_SECONDS = 15.0
# A select preset counts as "current" when the desk is within this many cm.
PRESET_MATCH_TOLERANCE_CM = 1

MANUFACTURER = "TiMotion"
MODEL = "TWD1"
