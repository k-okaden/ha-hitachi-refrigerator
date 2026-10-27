"""Sensors for the Hitachi refrigerator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import FREEZER_SETTINGS, FRIDGE_SETTINGS, ICE_MODES, LEVELS, FridgeStatus
from .coordinator import FridgeData, HitachiConfigEntry, HitachiCoordinator
from .entity import HitachiEntity

PARALLEL_UPDATES = 0


def _last_captured(fridge: FridgeData) -> datetime | None:
    if not fridge.images:
        return None
    return max(image.captured_at for image in fridge.images.values())


@dataclass(frozen=True, kw_only=True)
class HitachiSensorDescription(SensorEntityDescription):
    value_fn: Callable[[FridgeData], str | int | datetime | None]


def _status(fn: Callable[[FridgeStatus], str | int | datetime | None]):
    return lambda fridge: fn(fridge.status) if fridge.status else None


SENSORS: tuple[HitachiSensorDescription, ...] = (
    HitachiSensorDescription(
        key="last_captured",
        translation_key="last_captured",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_captured,
    ),
    HitachiSensorDescription(
        key="door_open_count_today",
        translation_key="door_open_count_today",
        native_unit_of_measurement="回",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_status(lambda s: s.door_open_count_today),
    ),
    HitachiSensorDescription(
        key="door_open_count_yesterday",
        translation_key="door_open_count_yesterday",
        native_unit_of_measurement="回",
        value_fn=_status(lambda s: s.door_open_count_yesterday),
    ),
    HitachiSensorDescription(
        key="fridge_door_open_time_today",
        translation_key="fridge_door_open_time_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_status(lambda s: s.fridge_door_open_seconds_today),
    ),
    HitachiSensorDescription(
        key="drawer_open_time_today",
        translation_key="drawer_open_time_today",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_status(lambda s: s.drawer_open_seconds_today),
    ),
    HitachiSensorDescription(
        key="fridge_door_open_time_yesterday",
        translation_key="fridge_door_open_time_yesterday",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
        value_fn=_status(lambda s: s.fridge_door_open_seconds_yesterday),
    ),
    HitachiSensorDescription(
        key="drawer_open_time_yesterday",
        translation_key="drawer_open_time_yesterday",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        entity_registry_enabled_default=False,
        value_fn=_status(lambda s: s.drawer_open_seconds_yesterday),
    ),
    HitachiSensorDescription(
        key="fridge_setting",
        translation_key="fridge_setting",
        device_class=SensorDeviceClass.ENUM,
        options=[*FRIDGE_SETTINGS.values(), *LEVELS],
        value_fn=_status(lambda s: s.fridge_setting),
    ),
    HitachiSensorDescription(
        key="freezer_setting",
        translation_key="freezer_setting",
        device_class=SensorDeviceClass.ENUM,
        options=[*FREEZER_SETTINGS.values(), *LEVELS],
        value_fn=_status(lambda s: s.freezer_setting),
    ),
    HitachiSensorDescription(
        key="ice_mode",
        translation_key="ice_mode",
        device_class=SensorDeviceClass.ENUM,
        options=list(ICE_MODES.values()),
        value_fn=_status(lambda s: s.ice_mode),
    ),
    HitachiSensorDescription(
        key="error_code",
        translation_key="error_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status(lambda s: s.error_code),
    ),
    HitachiSensorDescription(
        key="info_code",
        translation_key="info_code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status(lambda s: s.info_code),
    ),
    HitachiSensorDescription(
        key="reported_at",
        translation_key="reported_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_status(lambda s: s.reported_at),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HitachiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        HitachiSensor(coordinator, dst, description)
        for dst in coordinator.data
        for description in SENSORS
    )


class HitachiSensor(HitachiEntity, SensorEntity):
    entity_description: HitachiSensorDescription

    def __init__(
        self, coordinator: HitachiCoordinator, dst: str, description: HitachiSensorDescription
    ) -> None:
        super().__init__(coordinator, dst, description.key, "sensor")
        self.entity_description = description

    @property
    def native_value(self) -> str | int | datetime | None:
        return self.entity_description.value_fn(self.fridge) if self.fridge else None
