"""Base entity for the Hitachi refrigerator."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import FridgeData, HitachiCoordinator


class HitachiEntity(CoordinatorEntity[HitachiCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: HitachiCoordinator, dst: str, key: str, platform: str) -> None:
        super().__init__(coordinator)
        self._dst = dst
        device = coordinator.data[dst].device
        self._attr_unique_id = f"{dst}_{key}"
        # Japanese nicknames slugify unpredictably, so suggest a stable entity_id.
        self.entity_id = f"{platform}.hitachi_fridge_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dst)},
            connections={(CONNECTION_NETWORK_MAC, device.mac)},
            manufacturer=MANUFACTURER,
            name=device.nickname or f"{MANUFACTURER} Refrigerator",
        )

    @property
    def fridge(self) -> FridgeData | None:
        return self.coordinator.data.get(self._dst)

    @property
    def available(self) -> bool:
        return super().available and self.fridge is not None
