"""Polling coordinator for the Hitachi refrigerator cloud."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    CameraImage,
    FridgeStatus,
    HitachiAuthError,
    HitachiClient,
    HitachiDevice,
    HitachiError,
)
from .const import CAMERA_POSITIONS, CONF_SESSION, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type HitachiConfigEntry = ConfigEntry[HitachiCoordinator]


@dataclass
class FridgeData:
    device: HitachiDevice
    # None while the fridge is offline or updating its software.
    status: FridgeStatus | None = None
    # Latest image per camera position (missing when that camera has none).
    images: dict[str, CameraImage] = field(default_factory=dict)


class HitachiCoordinator(DataUpdateCoordinator[dict[str, FridgeData]]):
    """Polls the status and latest camera images of every refrigerator on the account."""

    config_entry: HitachiConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: HitachiConfigEntry, client: HitachiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        # image key (S3 path) -> JPEG bytes, so each image is downloaded only once.
        self._image_cache: dict[str, bytes] = {}

    async def _async_update_data(self) -> dict[str, FridgeData]:
        session_before = self.client.session
        try:
            devices = await self.client.get_devices()
            data: dict[str, FridgeData] = {}
            for device in devices:
                fridge = FridgeData(device, await self.client.get_status(device))
                for position in CAMERA_POSITIONS:
                    if images := await self.client.get_camera_images(device.dst, position):
                        fridge.images[position] = images[-1]
                data[device.dst] = fridge
        except HitachiAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HitachiError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self._save_session_if_changed(session_before)

        wanted = {img.key for f in data.values() for img in f.images.values()}
        self._image_cache = {k: v for k, v in self._image_cache.items() if k in wanted}
        return data

    def _save_session_if_changed(self, before) -> None:
        # Keep the session across restarts so Home Assistant does not log in every time.
        if self.client.session is not None and self.client.session is not before:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_SESSION: self.client.session.as_dict()},
            )

    async def async_get_image(self, image: CameraImage) -> bytes | None:
        if (cached := self._image_cache.get(image.key)) is not None:
            return cached
        try:
            content = await self.client.download(image.url)
        except HitachiError as err:
            # Signed URLs expire; the next refresh brings fresh ones.
            _LOGGER.debug("Could not download %s: %s", image.filename, err)
            await self.async_request_refresh()
            return None
        self._image_cache[image.key] = content
        return content
