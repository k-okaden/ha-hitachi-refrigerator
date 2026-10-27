"""Refrigerator camera images (latest photo taken when the door was opened)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import CameraImage
from .const import CAMERA_POSITIONS
from .coordinator import HitachiConfigEntry, HitachiCoordinator
from .entity import HitachiEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HitachiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        HitachiCamera(coordinator, dst, position)
        for dst in coordinator.data
        for position in CAMERA_POSITIONS
    )


class HitachiCamera(HitachiEntity, Camera):
    _attr_content_type = "image/jpeg"

    def __init__(self, coordinator: HitachiCoordinator, dst: str, position: str) -> None:
        Camera.__init__(self)
        super().__init__(coordinator, dst, position, "camera")
        self._position = position
        self._attr_translation_key = position

    @property
    def _image(self) -> CameraImage | None:
        return self.fridge.images.get(self._position) if self.fridge else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        image = self._image
        return {
            "captured_at": image.captured_at.isoformat() if image else None,
            "filename": image.filename if image else None,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        # A new photo needs a new access token so dashboards fetch it again.
        self.async_update_token()
        super()._handle_coordinator_update()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        if (image := self._image) is None:
            return None
        return await self.coordinator.async_get_image(image)
