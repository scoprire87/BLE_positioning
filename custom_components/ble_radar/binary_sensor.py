"""Binary sensor platform for BLE Radar (Bermuda fork)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import BermudaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Configura la piattaforma binary_sensor per BLE Radar."""
    coordinator = entry.runtime_data.coordinator
    
    entities = []
    for mac, device in coordinator.devices.items():
        if device.create_sensor:
            entities.append(BermudaRadarLockSensor(coordinator, entry, mac))
            
    async_add_entities(entities)


class BermudaRadarLockSensor(BermudaEntity, BinarySensorEntity):
    """Sensore binario che indica se il dispositivo è attualmente tracciato dalla mappa Radar."""

    def __init__(self, coordinator, config_entry, mac_address):
        super().__init__(coordinator, config_entry, mac_address)
        self._attr_device_class = BinarySensorDeviceClass.PRESENCE
        self._attr_name = f"{self._device.name} Radar Lock"
        self._attr_unique_id = f"{self._device.unique_id}_radar_lock"

    @property
    def is_on(self) -> bool:
        """Ritorna True se l'algoritmo KNN ha trovato una stanza corrispondente."""
        # Se radar_room è valorizzato e non è sconosciuto, abbiamo l'aggancio!
        return (
            self._device.radar_room is not None 
            and self._device.radar_room not in ["Sconosciuta", "Nessuna Mappa"]
        )

    @property
    def icon(self):
        """Cambia l'icona dinamicamente in base allo stato."""
        return "mdi:radar" if self.is_on else "mdi:radar-off"

    @property
    def extra_state_attributes(self):
        """Mostra quanto è precisa la misurazione attuale (Distanza Euclidea)."""
        attrs = {}
        if self._device.radar_match_dist is not None:
            attrs["precision_score"] = round(self._device.radar_match_dist, 2)
        return attrs
