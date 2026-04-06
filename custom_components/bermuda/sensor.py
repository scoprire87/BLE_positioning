"""Sensor platform for BLE Radar (Bermuda fork)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import RestoreSensor, SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    STATE_UNAVAILABLE,
    EntityCategory,
    UnitOfLength,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
    _LOGGER,
    ADDR_TYPE_IBEACON,
    ADDR_TYPE_PRIVATE_BLE_DEVICE,
    SIGNAL_DEVICE_NEW,
    SIGNAL_SCANNERS_CHANGED,
)
from .entity import BermudaEntity, BermudaGlobalEntity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import BermudaConfigEntry
    from .coordinator import BermudaDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BermudaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup sensor platform."""
    coordinator: BermudaDataUpdateCoordinator = entry.runtime_data.coordinator

    created_devices: list[str] = []  
    created_scanners: dict[str, list[str]] = {}  

    @callback
    def device_new(address: str) -> None:
        """Create entities for newly-found device."""
        if address not in created_devices:
            entities = []
            entities.append(BermudaSensor(coordinator, entry, address))
            if coordinator.have_floors:
                entities.append(BermudaSensorFloor(coordinator, entry, address))
            entities.append(BermudaSensorRange(coordinator, entry, address))
            entities.append(BermudaSensorScanner(coordinator, entry, address))
            entities.append(BermudaSensorRssi(coordinator, entry, address))
            entities.append(BermudaSensorAreaLastSeen(coordinator, entry, address))
            entities.append(BermudaSensorAreaSwitchReason(coordinator, entry, address))

            async_add_entities(entities, False)
            created_devices.append(address)
        else:
            pass

        create_scanner_entities()
        coordinator.sensor_created(address)

    def create_scanner_entities():
        for scanner in coordinator.get_scanners:
            if (
                scanner.is_remote_scanner is None  
                or (scanner.is_remote_scanner and scanner.address_wifi_mac is None)
            ):
                return

        entities = []
        for scanner in coordinator.scanner_list:
            for address in created_devices:
                if address not in created_scanners.get(scanner, []):
                    entities.append(BermudaSensorScannerRange(coordinator, entry, address, scanner))
                    entities.append(BermudaSensorScannerRangeRaw(coordinator, entry, address, scanner))
                    created_entry = created_scanners.setdefault(scanner, [])
                    created_entry.append(address)
        async_add_entities(entities, False)

    @callback
    def scanners_changed() -> None:
        create_scanner_entities()

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_NEW, device_new))
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_SCANNERS_CHANGED, scanners_changed))

    async_add_entities(
        (
            BermudaTotalProxyCount(coordinator, entry),
            BermudaActiveProxyCount(coordinator, entry),
            BermudaTotalDeviceCount(coordinator, entry),
            BermudaVisibleDeviceCount(coordinator, entry),
        )
    )


class BermudaSensor(BermudaEntity, SensorEntity):
    """BLE Radar Sensor class."""

    @property
    def unique_id(self):
        return self._device.unique_id

    @property
    def has_entity_name(self) -> bool:
        return True

    @property
    def name(self):
        return "Radar Room"

    @property
    def native_value(self):
        """Restituisce la stanza Radar, o l'area fallback se il radar fallisce."""
        if self._device.radar_room and self._device.radar_room not in ["Sconosciuta", "Nessuna Mappa"]:
            return self._device.radar_room
        return self._device.area_name

    @property
    def icon(self):
        if self.name == "Radar Room":
            return self._device.area_icon
        if self.name == "Area Last Seen":
            return self._device.area_last_seen_icon
        if self.name == "Floor":
            return self._device.floor_icon
        return super().icon

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self.name in ["Radar Room", "Distance", "Floor"]

    @property
    def device_class(self):
        return "bermuda__custom_device_class"

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        current_mac = self._device.address
        if self._device.address_type in [
            ADDR_TYPE_IBEACON,
            ADDR_TYPE_PRIVATE_BLE_DEVICE,
        ]:
            current_mac: str = STATE_UNAVAILABLE
            _best_stamp = 0
            for source_ad in self._device.adverts.values():
                if source_ad.stamp > _best_stamp:  
                    current_mac = source_ad.device_address
                    _best_stamp = source_ad.stamp

        attribs = {}
        if self.name in ["Radar Room", "Floor"]:
            # --- INFO RADAR ---
            attribs["radar_active"] = (self._device.radar_room is not None and self._device.radar_room not in ["Sconosciuta", "Nessuna Mappa"])
            if self._device.radar_match_dist is not None:
                attribs["euclidean_distance_score"] = round(self._device.radar_match_dist, 2)
            
            # --- INFO FALLBACK (Bermuda originale) ---
            attribs["fallback_area_id"] = self._device.area_id
            attribs["fallback_area_name"] = self._device.area_name
            attribs["floor_id"] = self._device.floor_id
            attribs["floor_name"] = self._device.floor_name
            attribs["floor_level"] = self._device.floor_level
            
        attribs["current_mac"] = current_mac

        return attribs


class BermudaSensorFloor(BermudaSensor):
    @property
    def unique_id(self):
        return f"{self._device.unique_id}_floor"

    @property
    def name(self):
        return "Floor"

    @property
    def native_value(self):
        return self._device.floor_name


class BermudaSensorScanner(BermudaSensor):
    @property
    def unique_id(self):
        return f"{self._device.unique_id}_scanner"

    @property
    def name(self):
        return "Nearest Scanner (Fallback)"

    @property
    def native_value(self):
        if self._device.area_advert is not None:
            return self.coordinator.devices[self._device.area_advert.scanner_address].name
        return None


class BermudaSensorRssi(BermudaSensor):
    @property
    def unique_id(self):
        return f"{self._device.unique_id}_rssi"

    @property
    def name(self):
        return "Nearest RSSI"

    @property
    def native_value(self):
        return self._cached_ratelimit(self._device.area_rssi, fast_falling=False, fast_rising=True)

    @property
    def device_class(self):
        return SensorDeviceClass.SIGNAL_STRENGTH

    @property
    def native_unit_of_measurement(self):
        return SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT


class BermudaSensorRange(BermudaSensor):
    @property
    def unique_id(self):
        return f"{self._device.unique_id}_range"

    @property
    def name(self):
        return "Distance (Fallback)"

    @property
    def native_value(self):
        distance = self._device.area_distance
        if distance is not None:
            return self._cached_ratelimit(round(distance, 1))
        return None

    @property
    def device_class(self):
        return SensorDeviceClass.DISTANCE

    @property
    def native_unit_of_measurement(self):
        return UnitOfLength.METERS

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT


class BermudaSensorScannerRange(BermudaSensorRange):
    def __init__(
        self,
        coordinator: BermudaDataUpdateCoordinator,
        config_entry,
        address: str,
        scanner_address: str,
    ) -> None:
        super().__init__(coordinator, config_entry, address)
        self.coordinator = coordinator
        self.config_entry = config_entry
        self._device = coordinator.devices[address]
        self._scanner = coordinator.devices[scanner_address]

    @property
    def unique_id(self):
        return f"{self._device.unique_id}_{self._scanner.address_wifi_mac or self._scanner.address}_range"

    @property
    def name(self):
        return f"Distance to {self._scanner.name}"

    @property
    def native_value(self):
        distance = None
        if (scanner := self._device.get_scanner(self._scanner.address)) is not None:
            distance = scanner.rssi_distance
        if distance is not None:
            return self._cached_ratelimit(round(distance, 3))
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        devscanner = self._device.get_scanner(self._scanner.address)
        if hasattr(devscanner, "source"):
            return {
                "area_id": self._scanner.area_id,
                "area_name": self._scanner.area_name,
                "area_scanner_mac": self._scanner.address,
                "area_scanner_name": self._scanner.name,
            }
        else:
            return None


class BermudaSensorScannerRangeRaw(BermudaSensorScannerRange):
    @property
    def unique_id(self):
        return f"{self._device.unique_id}_{self._scanner.address_wifi_mac or self._scanner.address}_range_raw"

    @property
    def name(self):
        return f"Unfiltered Distance to {self._scanner.name}"

    @property
    def native_value(self):
        devscanner = self._device.get_scanner(self._scanner.address)
        distance = getattr(devscanner, "rssi_distance_raw", None)
        if distance is not None:
            return round(distance, 3)
        return None


class BermudaSensorAreaSwitchReason(BermudaSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def entity_registry_enabled_default(self) -> bool:
        return False

    @property
    def name(self):
        return "Area Switch Diagnostic"

    @property
    def unique_id(self):
        return f"{self._device.unique_id}_area_switch_reason"

    @property
    def native_value(self):
        if self._device.diag_area_switch is not None:
            return self._device.diag_area_switch[:255]
        return None


class BermudaSensorAreaLastSeen(BermudaSensor, RestoreSensor):
    @property
    def unique_id(self):
        return f"{self._device.unique_id}_area_last_seen"

    @property
    def name(self):
        return "Area Last Seen"

    @property
    def native_value(self):
        return self._device.area_last_seen

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (sensor_data := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = str(sensor_data.native_value)
            self._device.area_last_seen = str(sensor_data.native_value)


class BermudaGlobalSensor(BermudaGlobalEntity, SensorEntity):
    _attr_has_entity_name = True

    @property
    def name(self):
        return "Area"

    @property
    def device_class(self):
        return "bermuda__custom_device_class"


class BermudaTotalProxyCount(BermudaGlobalSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self):
        return "BERMUDA_GLOBAL_PROXY_COUNT"

    @property
    def native_value(self) -> int:
        return self._cached_ratelimit(len(self.coordinator.scanner_list)) or 0

    @property
    def name(self):
        return "Total proxy count"


class BermudaActiveProxyCount(BermudaGlobalSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self):
        return "BERMUDA_GLOBAL_ACTIVE_PROXY_COUNT"

    @property
    def native_value(self) -> int:
        return self._cached_ratelimit(self.coordinator.count_active_scanners()) or 0

    @property
    def name(self):
        return "Active proxy count"


class BermudaTotalDeviceCount(BermudaGlobalSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self):
        return "BERMUDA_GLOBAL_DEVICE_COUNT"

    @property
    def native_value(self) -> int:
        return self._cached_ratelimit(len(self.coordinator.devices)) or 0

    @property
    def name(self):
        return "Total device count"


class BermudaVisibleDeviceCount(BermudaGlobalSensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def unique_id(self):
        return "BERMUDA_GLOBAL_VISIBLE_DEVICE_COUNT"

    @property
    def native_value(self) -> int:
        return self._cached_ratelimit(self.coordinator.count_active_devices()) or 0

    @property
    def name(self):
        return "Visible device count"
