"""Constants for the Hitachi refrigerator integration."""

from datetime import timedelta

DOMAIN = "hitachi_refrigerator"
MANUFACTURER = "Hitachi"

SCAN_INTERVAL = timedelta(minutes=5)

# center = 冷蔵室の棚, left / right = ドアポケット
CAMERA_POSITIONS = ("center", "left", "right")

CONF_SESSION = "session"
KEYS_FILE = "keys.json"
# Kept outside custom_components so HACS updates do not delete it.
KEYS_CONFIG_FILE = "hitachi_refrigerator_keys.json"
