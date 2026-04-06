"""Switch platform for BLE Radar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import SIGNAL_DEVICE_NEW
from .entity import BermudaEntity

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback
    from . import BermudaConfigEntry
    from .coordinator import BermudaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BermudaConfigEntry,
    async_add_devices: AddEntitiesCallback,
) -> None:
    """Load Switch entities for a config entry."""
    coordinator: BermudaDataUpdateCoordinator = entry.runtime_data.coordinator

    created_devices = []

    @callback
    def device_new(address: str) -> None:
        """Create entities for newly-found device."""
        # Se in futuro vorrai abilitare gli switch, decommenta le righe qui sotto
        # e assicurati che Platform.SWITCH sia presente in PLATFORMS (const.py)
        
        # if address not in created_devices:
        #     entities = []
        #     entities.append(BermudaRadarSwitch(coordinator, entry, address))
        #     async_add_devices(entities, False)
        #     created_devices.append(address)
        pass

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_NEW, device_new))


class BermudaRadarSwitch(BermudaEntity, SwitchEntity):
    """Esempio di interruttore per abilitare/disabilitare funzionalità del BLE Radar."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Abilita Tracciamento Radar"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        entry: BermudaConfigEntry,
        address: str,
    ) -> None:
        super().__init__(coordinator, entry, address)
        # Inizializza lo stato dell'interruttore
        self._is_on = True

    @property
    def unique_id(self):
        """Uniquely identify this sensor so that it gets stored in the entity_registry."""
        return f"{self._device.unique_id}_radar_switch"

    @property
    def icon(self):
        """Cambia icona in base allo stato."""
        return "mdi:radar" if self._is_on else "mdi:radar-off"

    @property
    def is_on(self):
        """Ritorna True se l'interruttore è acceso."""
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Accende l'interruttore."""
        self._is_on = True
        # Qui potresti aggiungere la logica per informare il coordinator
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Spegne l'interruttore."""
        self._is_on = False
        # Qui potresti aggiungere la logica per informare il coordinator
        self.async_write_ha_state()
