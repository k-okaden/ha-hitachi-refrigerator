"""The Hitachi refrigerator integration."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HitachiClient, HitachiSession
from .const import CONF_SESSION, KEYS_CONFIG_FILE, KEYS_FILE
from .coordinator import HitachiConfigEntry, HitachiCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CAMERA, Platform.SENSOR]


def load_keys(config_dir: str) -> dict[str, str]:
    """Read the app's built-in AES keys (made by tools/extract_keys.py).

    /config/hitachi_refrigerator_keys.json is checked first because HACS
    updates replace the integration folder.
    """
    candidates = (Path(config_dir) / KEYS_CONFIG_FILE, Path(__file__).parent / KEYS_FILE)
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text())
    raise FileNotFoundError(" or ".join(str(p) for p in candidates))


async def async_create_client(
    hass: HomeAssistant, email: str, password: str, saved: dict | None = None
) -> HitachiClient:
    try:
        keys = await hass.async_add_executor_job(load_keys, hass.config.config_dir)
    except (OSError, ValueError) as err:
        raise ConfigEntryError(f"AES keys not found: {err}") from err
    return HitachiClient(
        async_get_clientsession(hass),
        keys,
        email,
        password,
        HitachiSession(**saved) if saved else None,
    )


async def async_setup_entry(hass: HomeAssistant, entry: HitachiConfigEntry) -> bool:
    client = await async_create_client(
        hass, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD], entry.data.get(CONF_SESSION)
    )
    coordinator = HitachiCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HitachiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
