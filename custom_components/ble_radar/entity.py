"""BermudaEntity class for BLE Radar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bluetooth_data_tools import monotonic_time_coarse
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ADDR_TYPE_IBEACON,
    ADDR_TYPE_PRIVATE_BLE_DEVICE,
    ATTRIBUTION,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    DOMAIN_PRIVATE_BLE_DEVICE,
)

if TYPE_CHECKING:
    from . import BermudaConfigEntry
    from .coordinator import BermudaDataUpdateCoordinator


class BermudaEntity(CoordinatorEntity):
    """
    Co-ordinator for BLE Radar data.
    """

    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        config_entry: BermudaConfigEntry,
        address: str,
    ) -> None:
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.config_entry = config_entry
        self.address = address
        self._device = coordinator.devices[address]
        self._lastname = self._device.name  
        self.ar = ar.async_get(coordinator.hass)
        self.dr = dr.async_get(coordinator.hass)
        self.devreg_init_done = False

        self.bermuda_update_interval = config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self.bermuda_last_state: Any = 0
        self.bermuda_last_stamp: float = 0
        
        # --- NUOVO: Tracciamo l'ultima stanza radar per aggiornamenti istantanei ---
        self._last_radar_room: str | None = None

    def _cached_ratelimit(self, statevalue: Any, fast_falling=True, fast_rising=False, interval=None):
        """
        Rate-limit updates per non intasare il database, ma con un'eccezione 
        se l'area radar è cambiata.
        """
        if interval is not None:
            self.bermuda_update_interval = interval

        nowstamp = monotonic_time_coarse()
        
        # --- NUOVO: Se la stanza radar è cambiata, forza l'aggiornamento istantaneo! ---
        force_update = False
        if getattr(self._device, 'radar_room', None) != self._last_radar_room:
            self._last_radar_room = getattr(self._device, 'radar_room', None)
            force_update = True

        if (
            force_update
            or (self.bermuda_last_stamp < nowstamp - self.bermuda_update_interval) 
            or (self._device.ref_power_changed > nowstamp + 2)  
            or (self.bermuda_last_state is None)  
            or (statevalue is None)  
            or (fast_falling and statevalue < self.bermuda_last_state)  
            or (fast_rising and statevalue > self.bermuda_last_state)  
        ):
            self.bermuda_last_stamp = nowstamp
            self.bermuda_last_state = statevalue
            return statevalue
        else:
            return self.bermuda_last_state

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the co-ordinator."""
        if not self.devreg_init_done and self.device_entry:
            self._device.name_by_user = self.device_entry.name_by_user
            self.devreg_init_done = True
        if self._device.name != self._lastname:
            self._lastname = self._device.name
            if self.device_entry:
                self.dr.async_update_device(self.device_entry.id, name=self._device.name)
        self.async_write_ha_state()

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return self._device.unique_id

    @property
    def device_info(self):
        """Implementing this creates an entry in the device registry."""
        domain_name = DOMAIN
        model = None

        if self._device.is_scanner:
            connections = {
                (dr.CONNECTION_NETWORK_MAC, (self._device.address_wifi_mac or self._device.address).lower()),
                (dr.CONNECTION_BLUETOOTH, (self._device.address_ble_mac or self._device.address).upper()),
            }
        elif self._device.address_type == ADDR_TYPE_IBEACON:
            connections = {("ibeacon", self._device.address.lower())}
            model = f"iBeacon: {self._device.address.lower()}"
        elif self._device.address_type == ADDR_TYPE_PRIVATE_BLE_DEVICE:
            connections = {("private_ble_device", self._device.address.lower())}
            domain_name = DOMAIN_PRIVATE_BLE_DEVICE
        else:
            connections = {(dr.CONNECTION_BLUETOOTH, self._device.address.upper())}

        device_info = {
            "identifiers": {(domain_name, self._device.unique_id)},
            "connections": connections,
            "name": self._device.name,
        }
        if model is not None:
            device_info["model"] = model

        return device_info

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {
            "attribution": ATTRIBUTION,
            "id": str(self.coordinator.data.get("id")),
            "integration": DOMAIN,
        }


class BermudaGlobalEntity(CoordinatorEntity):
    """Holds all Bermuda global data under one entity type/device."""

    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        config_entry: BermudaConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.config_entry = config_entry
        self._cache_ratelimit_value = None
        self._cache_ratelimit_stamp: float = 0
        self._cache_ratelimit_interval = 60

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    def _cached_ratelimit(self, statevalue: Any, interval: int | None = None):
        if interval is not None:
            self._cache_ratelimit_interval = interval
        nowstamp = monotonic_time_coarse()

        if nowstamp > self._cache_ratelimit_stamp + self._cache_ratelimit_interval:
            self._cache_ratelimit_stamp = nowstamp
            self._cache_ratelimit_value = statevalue
            return statevalue
        else:
            return self._cache_ratelimit_value

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "BERMUDA_GLOBAL")},
            "name": "BLE Radar Global",
        }
