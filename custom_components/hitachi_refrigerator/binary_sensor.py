"""Binary sensors for the Hitachi refrigerator: settings switches and 運転状況 signs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import FridgeStatus
from .coordinator import HitachiConfigEntry, HitachiCoordinator
from .entity import HitachiEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class HitachiBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[FridgeStatus], bool]


BINARY_SENSORS: tuple[HitachiBinarySensorDescription, ...] = (
    # Settings (冷蔵庫設定 / 冷却モード / 節電モード)
    HitachiBinarySensorDescription(
        key="power_saving_mode",
        translation_key="power_saving_mode",
        value_fn=lambda s: s.power_saving_enabled,
    ),
    HitachiBinarySensorDescription(
        key="quick_cooling_mode",
        translation_key="quick_cooling_mode",
        value_fn=lambda s: s.quick_cooling_enabled,
    ),
    # Other cooling-mode switches; not shown in the app for HXCC-type models.
    HitachiBinarySensorDescription(
        key="spot_cooling_mode",
        translation_key="spot_cooling_mode",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.spot_cooling_enabled,
    ),
    HitachiBinarySensorDescription(
        key="rapid_cooling_mode",
        translation_key="rapid_cooling_mode",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.rapid_cooling_enabled,
    ),
    HitachiBinarySensorDescription(
        key="quick_freezing_mode",
        translation_key="quick_freezing_mode",
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.quick_freezing_enabled,
    ),
    # Signs on the 運転状況 screen
    HitachiBinarySensorDescription(
        key="power_saving_active",
        translation_key="power_saving_active",
        value_fn=lambda s: s.power_saving_active,
    ),
    HitachiBinarySensorDescription(
        key="water_tank_empty",
        translation_key="water_tank_empty",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: s.water_tank_empty,
    ),
    HitachiBinarySensorDescription(
        key="ice_cleaning",
        translation_key="ice_cleaning",
        value_fn=lambda s: s.ice_cleaning,
    ),
    HitachiBinarySensorDescription(
        key="quick_ice",
        translation_key="quick_ice",
        value_fn=lambda s: s.quick_ice,
    ),
    HitachiBinarySensorDescription(
        key="rapid_cooling",
        translation_key="rapid_cooling",
        value_fn=lambda s: s.rapid_cooling,
    ),
    HitachiBinarySensorDescription(
        key="quick_cooling",
        translation_key="quick_cooling",
        value_fn=lambda s: s.quick_cooling,
    ),
    HitachiBinarySensorDescription(
        key="quick_freezing",
        translation_key="quick_freezing",
        value_fn=lambda s: s.quick_freezing,
    ),
    HitachiBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.has_problem,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HitachiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        HitachiBinarySensor(coordinator, dst, description)
        for dst in coordinator.data
        for description in BINARY_SENSORS
    )


class HitachiBinarySensor(HitachiEntity, BinarySensorEntity):
    entity_description: HitachiBinarySensorDescription

    def __init__(
        self,
        coordinator: HitachiCoordinator,
        dst: str,
        description: HitachiBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, dst, description.key, "binary_sensor")
        self.entity_description = description

    @property
    def available(self) -> bool:
        # Unavailable while the fridge does not report (power off, software update).
        return super().available and self.fridge.status is not None

    @property
    def is_on(self) -> bool | None:
        status = self.fridge.status if self.fridge else None
        return self.entity_description.value_fn(status) if status else None
