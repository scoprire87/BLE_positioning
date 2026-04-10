"""Create device_tracker entities for BLE Radar devices."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker.config_entry import BaseTrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.const import STATE_HOME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import SIGNAL_DEVICE_NEW
from .entity import BermudaEntity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import BermudaConfigEntry
    from .coordinator import BermudaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BermudaConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Load Device Tracker entities for a config entry."""
    coordinator: BermudaDataUpdateCoordinator = entry.runtime_data.coordinator

    created_devices = []  # list of devices we've already created entities for

    @callback
    def device_new(address: str) -> None:
        """
        Create entities for newly-found device.
        """
        if address not in created_devices:
            entities = []
            entities.append(BermudaDeviceTracker(coordinator, entry, address))
            async_add_devices(entities, False)
            created_devices.append(address)
        
        # tell the co-ord we've done it.
        coordinator.device_tracker_created(address)

    # Connect device_new to a signal so the coordinator can call it
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_NEW, device_new))


class BermudaDeviceTracker(BermudaEntity, BaseTrackerEntity):
    """A trackable BLE Radar Device."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Radar Tracker"

    @property
    def unique_id(self):
        """Uniquely identify this sensor so that it gets stored in the entity_registry."""
        return f"{self._device.unique_id}_radar_tracker"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return extra state attributes for this device (Radar Mapping Info)."""
        attrs = {
            "area": self._device.area_name,
            "radar_room": self._device.radar_room,
        }
        
        # Aggiungiamo il punteggio di precisione (Distanza Euclidea) se disponibile
        if self._device.radar_match_dist is not None:
            attrs["precision_score"] = round(self._device.radar_match_dist, 2)
            
        # Manteniamo il proxy più vicino come informazione di debug
        _scannername = self._device.area_advert.name if self._device.area_advert is not None else None
        attrs["closest_scanner"] = _scannername
        
        return attrs

    @property
    def state(self) -> str:
        """Return the state of the device."""
        return self._device.zone

    @property
    def source_type(self) -> SourceType:
        """Return the source type, eg gps or router, of the device."""
        return SourceType.BLUETOOTH_LE

    @property
    def icon(self) -> str:
        """Return device icon."""
        return "mdi:bluetooth-connect" if self._device.zone == STATE_HOME else "mdi:bluetooth-off"
