"""Sensors for the Hitachi refrigerator."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HitachiConfigEntry, HitachiCoordinator
from .entity import HitachiEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HitachiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(LastCapturedSensor(coordinator, dst) for dst in coordinator.data)


class LastCapturedSensor(HitachiEntity, SensorEntity):
    """When the camera last took a photo, i.e. roughly when the door was last opened."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_captured"

    def __init__(self, coordinator: HitachiCoordinator, dst: str) -> None:
        super().__init__(coordinator, dst, "last_captured", "sensor")

    @property
    def native_value(self) -> datetime | None:
        if not self.fridge or not self.fridge.images:
            return None
        return max(image.captured_at for image in self.fridge.images.values())
