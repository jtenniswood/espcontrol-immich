"""Home Assistant platform declarations and shared product settings."""
from homeassistant.const import Platform
from .core.settings import *  # noqa: F403

PLATFORMS = [Platform.IMAGE, Platform.SENSOR, Platform.SWITCH, Platform.BUTTON, Platform.NUMBER, Platform.SELECT]
