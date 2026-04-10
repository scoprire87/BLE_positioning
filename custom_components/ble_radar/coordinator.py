"""DataUpdateCoordinator for BLE Radar (Bermuda fork)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, cast

import aiofiles
import voluptuous as vol
import yaml
from bluetooth_data_tools import monotonic_time_coarse
from habluetooth import BaseHaScanner
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.api import _get_manager
from homeassistant.const import MAJOR_VERSION as HA_VERSION_MAJ
from homeassistant.const import MINOR_VERSION as HA_VERSION_MIN
from homeassistant.const import Platform
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    config_validation as cv,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    floor_registry as fr,
)
from homeassistant.helpers import (
    issue_registry as ir,
)
from homeassistant.helpers.device_registry import (
    EVENT_DEVICE_REGISTRY_UPDATED,
    EventDeviceRegistryUpdatedData,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import get_age, now

from .bermuda_device import BermudaDevice
from .bermuda_irk import BermudaIrkManager
from .const import (
    _LOGGER,
    _LOGGER_SPAM_LESS,
    ADDR_TYPE_PRIVATE_BLE_DEVICE,
    AREA_MAX_AD_AGE,
    BDADDR_TYPE_NOT_MAC48,
    BDADDR_TYPE_RANDOM_RESOLVABLE,
    CONF_ATTENUATION,
    CONF_DEVICES,
    CONF_DEVTRACK_TIMEOUT,
    CONF_MAX_RADIUS,
    CONF_MAX_VELOCITY,
    CONF_REF_POWER,
    CONF_RSSI_OFFSETS,
    CONF_SMOOTHING_SAMPLES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ATTENUATION,
    DEFAULT_DEVTRACK_TIMEOUT,
    DEFAULT_MAX_RADIUS,
    DEFAULT_MAX_VELOCITY,
    DEFAULT_REF_POWER,
    DEFAULT_SMOOTHING_SAMPLES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    DOMAIN_PRIVATE_BLE_DEVICE,
    METADEVICE_IBEACON_DEVICE,
    METADEVICE_TYPE_IBEACON_SOURCE,
    METADEVICE_TYPE_PRIVATE_BLE_SOURCE,
    PRUNE_MAX_COUNT,
    PRUNE_TIME_DEFAULT,
    PRUNE_TIME_INTERVAL,
    PRUNE_TIME_KNOWN_IRK,
    PRUNE_TIME_REDACTIONS,
    PRUNE_TIME_UNKNOWN_IRK,
    REPAIR_SCANNER_WITHOUT_AREA,
    SAVEOUT_COOLDOWN,
    SIGNAL_DEVICE_NEW,
    SIGNAL_SCANNERS_CHANGED,
    UPDATE_INTERVAL,
)
from .util import mac_explode_formats, mac_norm

# --- NUOVO: Importiamo l'algoritmo di calcolo KNN ---
from .trilateration import find_best_room_match

if TYPE_CHECKING:
    from habluetooth import BluetoothServiceInfoBleak
    from homeassistant.components.bluetooth import (
        BluetoothChange,
    )
    from homeassistant.components.bluetooth.manager import HomeAssistantBluetoothManager

    from . import BermudaConfigEntry
    from .bermuda_advert import BermudaAdvert

Cancellable = Callable[[], None]

class BermudaDataUpdateCoordinator(DataUpdateCoordinator):
    """
    Class to manage fetching data from the Bluetooth component.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BermudaConfigEntry,
    ) -> None:
        """Initialize."""
        self.platforms = []
        self.config_entry = entry

        self.sensor_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self.hass_version_min_2025_2 = HA_VERSION_MAJ > 2025 or (HA_VERSION_MAJ == 2025 and HA_VERSION_MIN >= 2)
        self.hass_version_min_2025_4 = HA_VERSION_MAJ > 2025 or (HA_VERSION_MAJ == 2025 and HA_VERSION_MIN >= 4)

        self.redactions: dict[str, str] = {}
        self._redact_generic_re = re.compile(
            r"(?P<start>[0-9A-Fa-f]{2})[:_-]([0-9A-Fa-f]{2}[:_-]){4}(?P<end>[0-9A-Fa-f]{2})"
        )
        self._redact_generic_sub = r"\g<start>:xx:xx:xx:xx:\g<end>"

        self.stamp_redactions_expiry: float | None = None
        self.update_in_progress: bool = False  
        self.stamp_last_update: float = 0  
        self.stamp_last_update_started: float = 0
        self.stamp_last_prune: float = 0  

        self.member_uuids = {}
        self.company_uuids = {}

        # --- NUOVO: Riferimento allo Storage per leggere le mappe ---
        self.storage = entry.runtime_data.storage

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

        self._waitingfor_load_manufacturer_ids = True
        entry.async_create_background_task(
            hass, self.async_load_manufacturer_ids(), "Load Bluetooth IDs", eager_start=True
        )

        self._manager: HomeAssistantBluetoothManager = _get_manager(hass)  
        self._hascanners: set[BaseHaScanner] = set()  
        self._hascanner_timestamps: dict[str, dict[str, float]] = {}  
        self._scanner_list: set[str] = set()
        self._scanners: set[BermudaDevice] = set()  
        self.irk_manager = BermudaIrkManager()

        self.ar = ar.async_get(self.hass)
        self.er = er.async_get(self.hass)
        self.dr = dr.async_get(self.hass)
        self.fr = fr.async_get(self.hass)
        self.have_floors: bool = self.init_floors()

        self._scanners_without_areas: list[str] | None = None  
        self.pb_state_sources: dict[str, str | None] = {}
        self.metadevices: dict[str, BermudaDevice] = {}
        self._ad_listener_cancel: Cancellable | None = None

        self.last_config_entry_update: float = 0  
        self.last_config_entry_update_request = (
            monotonic_time_coarse() + SAVEOUT_COOLDOWN
        ) 

        self._scanner_init_pending = True
        self._seed_configured_devices_done = False
        self._do_private_device_init = True

        self.config_entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_DEVICE_REGISTRY_UPDATED, self.handle_devreg_changes)
        )

        self.options = {}
        self.options[CONF_ATTENUATION] = DEFAULT_ATTENUATION
        self.options[CONF_DEVTRACK_TIMEOUT] = DEFAULT_DEVTRACK_TIMEOUT
        self.options[CONF_MAX_RADIUS] = DEFAULT_MAX_RADIUS
        self.options[CONF_MAX_VELOCITY] = DEFAULT_MAX_VELOCITY
        self.options[CONF_REF_POWER] = DEFAULT_REF_POWER
        self.options[CONF_SMOOTHING_SAMPLES] = DEFAULT_SMOOTHING_SAMPLES
        self.options[CONF_UPDATE_INTERVAL] = DEFAULT_UPDATE_INTERVAL
        self.options[CONF_RSSI_OFFSETS] = {}

        if hasattr(entry, "options"):
            for key, val in entry.options.items():
                if key in (
                    CONF_ATTENUATION,
                    CONF_DEVICES,
                    CONF_DEVTRACK_TIMEOUT,
                    CONF_MAX_RADIUS,
                    CONF_MAX_VELOCITY,
                    CONF_REF_POWER,
                    CONF_SMOOTHING_SAMPLES,
                    CONF_RSSI_OFFSETS,
                ):
                    self.options[key] = val

        self.devices: dict[str, BermudaDevice] = {}

        hass.services.async_register(
            DOMAIN,
            "dump_devices",
            self.service_dump_devices,
            vol.Schema(
                {
                    vol.Optional("addresses"): cv.string,
                    vol.Optional("configured_devices"): cv.boolean,
                    vol.Optional("redact"): cv.boolean,
                }
            ),
            SupportsResponse.ONLY,
        )

        if self.config_entry is not None:
            self.config_entry.async_on_unload(
                bluetooth.async_register_callback(
                    self.hass,
                    self.async_handle_advert,
                    bluetooth.BluetoothCallbackMatcher(connectable=False),
                    bluetooth.BluetoothScanningMode.ACTIVE,
                )
            )

    @property
    def scanner_list(self):
        return self._scanner_list

    @property
    def get_scanners(self) -> set[BermudaDevice]:
        return self._scanners

    def init_floors(self) -> bool:
        _have_floors: bool = False
        for area in self.ar.async_list_areas():
            if area.floor_id is not None:
                _have_floors = True
                break
        return _have_floors

    def scanner_list_add(self, scanner_device: BermudaDevice):
        self._scanner_list.add(scanner_device.address)
        self._scanners.add(scanner_device)
        async_dispatcher_send(self.hass, SIGNAL_SCANNERS_CHANGED)

    def scanner_list_del(self, scanner_device: BermudaDevice):
        self._scanner_list.remove(scanner_device.address)
        self._scanners.remove(scanner_device)
        async_dispatcher_send(self.hass, SIGNAL_SCANNERS_CHANGED)

    def get_manufacturer_from_id(self, uuid: int | str) -> tuple[str, bool] | tuple[None, None]:
        if isinstance(uuid, str):
            uuid = int(uuid.replace(":", ""), 16)

        _generic = False
        if uuid == 0x0BA9:
            _name = "Shelly Devices"
        elif uuid == 0x004C:
            _name = "Apple Inc."
            _generic = True
        elif uuid == 0x181C:
            _name = "BTHome v1 cleartext"
            _generic = True
        elif uuid == 0x181E:
            _name = "BTHome v1 encrypted"
            _generic = True
        elif uuid == 0xFCD2:
            _name = "BTHome V2" 
            _generic = True
        elif uuid in self.member_uuids:
            _name = self.member_uuids[uuid]
            if any(x in _name for x in ["Google", "Realtek"]):
                _generic = True
        elif uuid in self.company_uuids:
            _name = self.company_uuids[uuid]
            _generic = False
        else:
            return (None, None)
        return (_name, _generic)

    async def async_load_manufacturer_ids(self):
        try:
            file_path = self.hass.config.path(
                f"custom_components/{DOMAIN}/manufacturer_identification/member_uuids.yaml"
            )
            async with aiofiles.open(file_path) as f:
                mi_yaml = yaml.safe_load(await f.read())["uuids"]
            self.member_uuids: dict[int, str] = {member["uuid"]: member["name"] for member in mi_yaml}

            file_path = self.hass.config.path(
                f"custom_components/{DOMAIN}/manufacturer_identification/company_identifiers.yaml"
            )
            async with aiofiles.open(file_path) as f:
                ci_yaml = yaml.safe_load(await f.read())["company_identifiers"]
            self.company_uuids: dict[int, str] = {member["value"]: member["name"] for member in ci_yaml}
        finally:
            self._waitingfor_load_manufacturer_ids = False

    @callback
    def handle_devreg_changes(self, ev: Event[EventDeviceRegistryUpdatedData]):
        device_id = ev.data.get("device_id")

        if ev.data["action"] in {"create", "update"}:
            if device_id is None:
                return

            for device in self.devices.values():
                if device.entry_id == device_id:
                    if device.is_scanner:
                        self._refresh_scanners(force=True)
                        return

            if device_entry := self.dr.async_get(ev.data["device_id"]):
                for conn_type, _conn_id in device_entry.connections:
                    if conn_type == "private_ble_device":
                        self._do_private_device_init = True
                    elif conn_type == "ibeacon":
                        pass
                    else:
                        for ident_type, ident_id in device_entry.identifiers:
                            if ident_type == DOMAIN:
                                try:
                                    if _device := self.devices[ident_id.lower()]:
                                        _device.name_by_user = device_entry.name_by_user
                                        _device.make_name()
                                except KeyError:
                                    pass
                        self._scanner_init_pending = True

        elif ev.data["action"] == "remove":
            device_found = False
            for scanner in self.get_scanners:
                if scanner.entry_id == device_id:
                    self._scanner_init_pending = True
                    device_found = True
            if not device_found:
                self._do_private_device_init = True

    @callback
    def async_handle_advert(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        if self.stamp_last_update < monotonic_time_coarse() - (UPDATE_INTERVAL * 2):
            self._async_update_data_internal()

    def _check_all_platforms_created(self, address):
        dev = self._get_device(address)
        if dev is not None:
            if all(
                [
                    dev.create_sensor_done,
                    dev.create_tracker_done,
                    dev.create_number_done,
                ]
            ):
                dev.create_all_done = True

    def sensor_created(self, address):
        dev = self._get_device(address)
        if dev is not None:
            dev.create_sensor_done = True
        self._check_all_platforms_created(address)

    def device_tracker_created(self, address):
        dev = self._get_device(address)
        if dev is not None:
            dev.create_tracker_done = True
        self._check_all_platforms_created(address)

    def number_created(self, address):
        dev = self._get_device(address)
        if dev is not None:
            dev.create_number_done = True
        self._check_all_platforms_created(address)

    def count_active_devices(self) -> int:
        stamp = monotonic_time_coarse() - 10 
        fresh_count = 0
        for device in self.devices.values():
            if device.last_seen > stamp:
                fresh_count += 1
        return fresh_count

    def count_active_scanners(self, max_age=10) -> int:
        stamp = monotonic_time_coarse() - max_age 
        fresh_count = 0
        for scanner in self.get_active_scanner_summary():
            if scanner.get("last_stamp", 0) > stamp:
                fresh_count += 1
        return fresh_count

    def get_active_scanner_summary(self) -> list[dict]:
        stamp = monotonic_time_coarse()
        return [
            {
                "name": scannerdev.name,
                "address": scannerdev.address,
                "last_stamp": scannerdev.last_seen,
                "last_stamp_age": stamp - scannerdev.last_seen,
            }
            for scannerdev in self.get_scanners
        ]

    def _get_device(self, address: str) -> BermudaDevice | None:
        try:
            return self.devices[mac_norm(address)]
        except KeyError:
            return None

    def _get_or_create_device(self, address: str) -> BermudaDevice:
        mac = mac_norm(address)
        try:
            return self.devices[mac]
        except KeyError:
            self.devices[mac] = device = BermudaDevice(mac, self)
            return device

    async def _async_update_data(self):
        self._async_update_data_internal()

    def _async_update_data_internal(self):
        if self._waitingfor_load_manufacturer_ids:
            return True
        if self.update_in_progress:
            return False
        self.update_in_progress = True

        try:  
            nowstamp = monotonic_time_coarse()
            result_gather_adverts = self._async_gather_advert_data()
            self.update_metadevices()

            for device in self.devices.values():
                device.calculate_data()

            self._refresh_areas_by_min_distance()

            for _source_address in self.options.get(CONF_DEVICES, []):
                self._get_or_create_device(_source_address)
            self._seed_configured_devices_done = True

            for address, device in self.devices.items():
                if device.create_sensor:
                    if not device.create_all_done:
                        async_dispatcher_send(self.hass, SIGNAL_DEVICE_NEW, address)

            self.prune_devices()

        finally:
            self.update_in_progress = False

        self.stamp_last_update_started = nowstamp
        self.stamp_last_update = monotonic_time_coarse()
        self.last_update_success = True
        return result_gather_adverts

    def _async_gather_advert_data(self):
        nowstamp = monotonic_time_coarse()

        if self._scanner_init_pending:
            self._refresh_scanners(force=True)

        for ha_scanner in self._hascanners:
            scanner_device = self._get_device(ha_scanner.source)

            if scanner_device is None:
                self._refresh_scanners(force=True)
                scanner_device = self._get_device(ha_scanner.source)

            if scanner_device is None:
                continue

            scanner_device.async_as_scanner_update(ha_scanner)

            for bledevice, advertisementdata in ha_scanner.discovered_devices_and_advertisement_data.values():
                if adstamp := scanner_device.async_as_scanner_get_stamp(bledevice.address):
                    if adstamp < self.stamp_last_update_started - 3:
                        continue
                if advertisementdata.rssi == -127:
                    continue

                device = self._get_or_create_device(bledevice.address)
                device.process_advertisement(scanner_device, advertisementdata)

        return True

    def prune_devices(self, force_pruning=False):
        if self.stamp_last_prune > monotonic_time_coarse() - PRUNE_TIME_INTERVAL and not force_pruning:
            return
        nowstamp = self.stamp_last_prune = monotonic_time_coarse()
        stamp_known_irk = nowstamp - PRUNE_TIME_KNOWN_IRK
        stamp_unknown_irk = nowstamp - PRUNE_TIME_UNKNOWN_IRK

        if self.stamp_redactions_expiry is not None and self.stamp_redactions_expiry < nowstamp:
            self.redactions.clear()
            self.stamp_redactions_expiry = None

        self.irk_manager.async_prune()

        prune_list: list[str] = []  
        prunable_stamps: dict[str, float] = {}  

        metadevice_source_keepers = set()
        for metadevice in self.metadevices.values():
            if len(metadevice.metadevice_sources) > 0:
                _first = True
                for address in metadevice.metadevice_sources:
                    if _device := self._get_device(address):
                        if _first or _device.last_seen > stamp_known_irk:
                            metadevice_source_keepers.add(address)
                            _first = False
                        else:
                            prune_list.append(address)

        for device_address, device in self.devices.items():
            if (
                device_address not in metadevice_source_keepers
                and device not in self.metadevices
                and device_address not in self.scanner_list
                and (not device.create_sensor)  
                and (not device.is_scanner)  
                and device.address_type != BDADDR_TYPE_NOT_MAC48
            ):
                if device.address_type == BDADDR_TYPE_RANDOM_RESOLVABLE:
                    if device.last_seen < stamp_unknown_irk:
                        prune_list.append(device_address)
                    elif device.last_seen < nowstamp - 200:  
                        prunable_stamps[device_address] = device.last_seen
                elif device.last_seen < nowstamp - PRUNE_TIME_DEFAULT:
                    prune_list.append(device_address)
                else:
                    prunable_stamps[device_address] = device.last_seen

        prune_quota_shortfall = len(self.devices) - len(prune_list) - PRUNE_MAX_COUNT
        if prune_quota_shortfall > 0:
            if len(prunable_stamps) > 0:
                sorted_addresses = sorted([(v, k) for k, v in prunable_stamps.items()])
                cutoff_index = min(len(sorted_addresses), prune_quota_shortfall)
                for _stamp, address in sorted_addresses[: prune_quota_shortfall - 1]:
                    prune_list.append(address)

        for device_address in prune_list:
            del self.devices[device_address]

        for device in self.devices.values():
            for address in prune_list:
                if address in device.metadevice_sources:
                    device.metadevice_sources.remove(address)

            for advert_tuple in list(device.adverts.keys()):
                if device.adverts[advert_tuple].device_address in prune_list:
                    del device.adverts[advert_tuple]

    def discover_private_ble_metadevices(self):
        if self._do_private_device_init:
            self._do_private_device_init = False
            pb_entries = self.hass.config_entries.async_entries(DOMAIN_PRIVATE_BLE_DEVICE, include_disabled=False)
            for pb_entry in pb_entries:
                pb_entities = self.er.entities.get_entries_for_config_entry_id(pb_entry.entry_id)
                for pb_entity in pb_entities:
                    if pb_entity.domain == Platform.DEVICE_TRACKER:
                        if pb_entity.device_id is not None:
                            pb_device = self.dr.async_get(pb_entity.device_id)
                        else:
                            pb_device = None

                        pb_state = self.hass.states.get(pb_entity.entity_id)

                        if pb_state:  
                            pb_source_address = pb_state.attributes.get("current_address", None)
                        else:
                            pb_source_address = None

                        _irk = pb_entity.unique_id.split("_")[0]

                        metadevice = self._get_or_create_device(_irk)
                        metadevice.create_sensor = True

                        if pb_device:
                            metadevice.name_by_user = pb_device.name_by_user
                            metadevice.name_devreg = pb_device.name
                            metadevice.make_name()

                        if pb_entity.entity_id not in self.pb_state_sources:
                            self.pb_state_sources[pb_entity.entity_id] = None  

                        if metadevice.address not in self.metadevices:
                            self.metadevices[metadevice.address] = metadevice

                        if pb_source_address is not None:
                            pb_source_address = mac_norm(pb_source_address)
                            source_device = self._get_or_create_device(pb_source_address)
                            source_device.metadevice_type.add(METADEVICE_TYPE_PRIVATE_BLE_SOURCE)

                            if pb_source_address not in metadevice.metadevice_sources:
                                metadevice.metadevice_sources.insert(0, pb_source_address)

                            self.pb_state_sources[pb_entity.entity_id] = pb_source_address

    def register_ibeacon_source(self, source_device: BermudaDevice):
        if METADEVICE_TYPE_IBEACON_SOURCE not in source_device.metadevice_type:
            pass
        if source_device.beacon_unique_id is not None:
            metadevice = self._get_or_create_device(source_device.beacon_unique_id)
            if len(metadevice.metadevice_sources) == 0:
                if metadevice.address not in self.metadevices:
                    self.metadevices[metadevice.address] = metadevice

                metadevice.name_bt_serviceinfo = source_device.name_bt_serviceinfo
                metadevice.name_bt_local_name = source_device.name_bt_local_name
                metadevice.beacon_unique_id = source_device.beacon_unique_id
                metadevice.beacon_major = source_device.beacon_major
                metadevice.beacon_minor = source_device.beacon_minor
                metadevice.beacon_power = source_device.beacon_power
                metadevice.beacon_uuid = source_device.beacon_uuid

                if metadevice.address.upper() in self.options.get(CONF_DEVICES, []):
                    metadevice.create_sensor = True

            if source_device.address not in metadevice.metadevice_sources:
                metadevice.metadevice_sources.insert(0, source_device.address)
                metadevice.name_bt_serviceinfo = metadevice.name_bt_serviceinfo or source_device.name_bt_serviceinfo
                metadevice.name_bt_local_name = metadevice.name_bt_local_name or source_device.name_bt_local_name

    def update_metadevices(self):
        self.discover_private_ble_metadevices()

        for metadevice in self.metadevices.values():
            _want_name_update = False
            _sources_to_remove = []

            for source_address in metadevice.metadevice_sources:
                source_device = self._get_device(source_address)
                if source_device is None:
                    continue

                if (
                    METADEVICE_IBEACON_DEVICE in metadevice.metadevice_type
                    and metadevice.beacon_unique_id != source_device.beacon_unique_id
                ):
                    for key_address, key_scanner in list(metadevice.adverts):
                        if key_address == source_device.address:
                            del metadevice.adverts[(key_address, key_scanner)]
                    if source_device.address in metadevice.metadevice_sources:
                        _sources_to_remove.append(source_device.address)
                    continue  

                for advert_tuple in source_device.adverts:
                    metadevice.adverts[advert_tuple] = source_device.adverts[advert_tuple]

                if metadevice.last_seen < source_device.last_seen:
                    metadevice.last_seen = source_device.last_seen

                if source_device.ref_power != metadevice.ref_power:
                    source_device.set_ref_power(metadevice.ref_power)

                for key, val in source_device.items():
                    if val is any(
                        [
                            source_device.name_bt_local_name,
                            source_device.name_bt_serviceinfo,
                            source_device.manufacturer,
                        ]
                    ) and metadevice[key] in [None, False]:
                        metadevice[key] = val
                        _want_name_update = True

                if _want_name_update:
                    metadevice.make_name()

                for key, val in source_device.items():
                    if val is any(
                        [
                            source_device.beacon_major,
                            source_device.beacon_minor,
                            source_device.beacon_power,
                            source_device.beacon_unique_id,
                            source_device.beacon_uuid,
                        ]
                    ):
                        metadevice[key] = val

            for source in _sources_to_remove:
                metadevice.metadevice_sources.remove(source)
            if _want_name_update:
                metadevice.make_name()

    def dt_mono_to_datetime(self, stamp) -> datetime:
        age = monotonic_time_coarse() - stamp
        return now() - timedelta(seconds=age)

    def dt_mono_to_age(self, stamp) -> str:
        return get_age(self.dt_mono_to_datetime(stamp))

    def resolve_area_name(self, area_id) -> str | None:
        areas = self.ar.async_get_area(area_id)
        if hasattr(areas, "name"):
            return getattr(areas, "name", "invalid_area")
        return None

    def _refresh_areas_by_min_distance(self):
        """
        --- LOGICA BLE RADAR ---
        Calcola la stanza in base all'algoritmo KNN di Fingerprinting, 
        non più in base al singolo proxy più vicino.
        """
        saved_map = self.storage.data.get("rooms", {})

        for device in self.devices.values():
            if device.create_sensor:
                
                # 1. Recuperiamo l'impronta attuale (i segnali stabilizzati di questo istante)
                current_fingerprint = device.get_current_fingerprint()

                # Se non ha abbastanza segnali (es. nessun proxy lo vede), fallback su Bermuda standard
                if not current_fingerprint:
                    self._refresh_area_by_min_distance_legacy(device)
                    continue

                # 2. Chiediamo al KNN quale stanza corrisponde
                Ematch_result = find_best_room_match(current_fingerprint, saved_map).
                best_room = match_result[0]
                match_distance = match_result[1]


                if best_room != "Sconosciuta":
                    # Il radar ha agganciato la stanza!
                    device.apply_radar_room(best_room, match_distance)
                else:
                    # Se non c'è tracciamento o la mappa non è completa, usa il vecchio metodo come backup
                    self._refresh_area_by_min_distance_legacy(device)

    def _refresh_area_by_min_distance_legacy(self, device: BermudaDevice):
        """Il vecchio metodo di Bermuda come fallback se la mappa radar fallisce."""
        incumbent: BermudaAdvert | None = device.area_advert
        _max_radius = self.options.get(CONF_MAX_RADIUS, DEFAULT_MAX_RADIUS)
        nowstamp = monotonic_time_coarse()

        for challenger in device.adverts.values():
            if incumbent is challenger:
                continue

            if challenger.stamp < nowstamp - AREA_MAX_AD_AGE:
                continue

            if challenger.rssi_distance is None or challenger.rssi_distance > _max_radius or challenger.area_id is None:
                continue

            if incumbent is None or incumbent.rssi_distance is None or incumbent.area_id is None:
                incumbent = challenger
                continue

            if incumbent.rssi_distance < challenger.rssi_distance:
                continue

            _pda = challenger.rssi_distance
            _pdb = incumbent.rssi_distance
            pcnt_diff = abs(_pda - _pdb) / ((_pda + _pdb) / 2)

            if (incumbent.area_id == challenger.area_id and 
                nowstamp - incumbent.stamp > nowstamp - challenger.stamp + 1 and 
                incumbent.rssi_distance >= challenger.rssi_distance):
                incumbent = challenger
                continue

            if len(challenger.hist_distance_by_interval) > 3:  
                hist_min_incumbent = min(incumbent.hist_distance_by_interval[:5])  
                hist_max_challenger = max(challenger.hist_distance_by_interval[:5]) 
                
                if hist_max_challenger < hist_min_incumbent and pcnt_diff > 0.15:
                    incumbent = challenger
                    continue

            if pcnt_diff < 0.30:
                continue

            incumbent = challenger

        device.apply_scanner_selection(incumbent)

    def _refresh_scanners(self, force=False):
        self._rebuild_scanner_list(force=force)

    def _rebuild_scanner_list(self, force=False):
        _new_ha_scanners = set(self._manager.async_current_scanners())

        if _new_ha_scanners is self._hascanners or _new_ha_scanners == self._hascanners:
            return

        self._hascanners = _new_ha_scanners
        self._async_purge_removed_scanners()

        _scanners_without_areas: list[str] = []

        for hascanner in self._hascanners:
            scanner_address = mac_norm(hascanner.source)
            bermuda_scanner = self._get_or_create_device(scanner_address)
            bermuda_scanner.async_as_scanner_init(hascanner)

            if bermuda_scanner.area_id is None:
                _scanners_without_areas.append(f"{bermuda_scanner.name} [{bermuda_scanner.address}]")
        self._async_manage_repair_scanners_without_areas(_scanners_without_areas)

    def _async_purge_removed_scanners(self):
        _scanners = [device.address for device in self.devices.values() if device.is_scanner]
        for ha_scanner in self._hascanners:
            scanner_address = mac_norm(ha_scanner.source)
            if scanner_address in _scanners:
                _scanners.remove(scanner_address)
        for address in _scanners:
            self.devices[address].async_as_scanner_nolonger()

    def _async_manage_repair_scanners_without_areas(self, scannerlist: list[str]):
        if self._scanners_without_areas != scannerlist:
            self._scanners_without_areas = scannerlist
            ir.async_delete_issue(self.hass, DOMAIN, REPAIR_SCANNER_WITHOUT_AREA)

            if self._scanners_without_areas and len(self._scanners_without_areas) != 0:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    REPAIR_SCANNER_WITHOUT_AREA,
                    translation_key=REPAIR_SCANNER_WITHOUT_AREA,
                    translation_placeholders={
                        "scannerlist": "".join(f"- {name}\n" for name in self._scanners_without_areas),
                    },
                    severity=ir.IssueSeverity.ERROR,
                    is_fixable=False,
                )

    async def service_dump_devices(self, call: ServiceCall) -> ServiceResponse:  
        out = {}
        addresses_input = call.data.get("addresses", "")
        redact = call.data.get("redact", False)
        configured_devices = call.data.get("configured_devices", False)

        addresses = []
        if addresses_input != "":
            addresses += addresses_input.upper().split()
        if configured_devices:
            addresses += self.scanner_list
            addresses += self.options.get(CONF_DEVICES, [])
            addresses += self.pb_state_sources

        addresses = list(map(str.lower, addresses))

        for address, device in self.devices.items():
            if len(addresses) == 0 or address.lower() in addresses:
                out[address] = device.to_dict()

        if redact:
            out = cast("ServiceResponse", self.redact_data(out))
        return out

    def redaction_list_update(self):
        i = len(self.redactions)
        for non_lower_address in self.scanner_list:
            address = non_lower_address.lower()
            if address not in self.redactions:
                i += 1
                for altmac in mac_explode_formats(address):
                    self.redactions[altmac] = f"{address[:2]}::SCANNER_{i}::{address[-2:]}"
        for non_lower_address in self.options.get(CONF_DEVICES, []):
            address = non_lower_address.lower()
            if address not in self.redactions:
                i += 1
                if address.count("_") == 2:
                    self.redactions[address] = f"{address[:4]}::CFG_iBea_{i}::{address[32:]}"
                    self.redactions[address.split("_")[0]] = f"{address[:4]}::CFG_iBea_{i}_{address[32:]}::"
                elif len(address) == 17:
                    for altmac in mac_explode_formats(address):
                        self.redactions[altmac] = f"{address[:2]}::CFG_MAC_{i}::{address[-2:]}"
                else:
                    self.redactions[address] = f"CFG_OTHER_{1}_{address}"
        for non_lower_address, device in self.devices.items():
            address = non_lower_address.lower()
            if address not in self.redactions:
                i += 1
                if device.address_type == ADDR_TYPE_PRIVATE_BLE_DEVICE:
                    self.redactions[address] = f"{address[:4]}::IRK_DEV_{i}"
                elif address.count("_") == 2:
                    self.redactions[address] = f"{address[:4]}::OTHER_iBea_{i}::{address[32:]}"
                    self.redactions[address.split("_")[0]] = f"{address[:4]}::OTHER_iBea_{i}_{address[32:]}::"
                elif len(address) == 17: 
                    for altmac in mac_explode_formats(address):
                        self.redactions[altmac] = f"{address[:2]}::OTHER_MAC_{i}::{address[-2:]}"
                else:
                    self.redactions[address] = f"OTHER_{i}_{address}"
        self.stamp_redactions_expiry = monotonic_time_coarse() + PRUNE_TIME_REDACTIONS

    def redact_data(self, data, first_recursion=True):
        if first_recursion:
            self.redaction_list_update()
            first_recursion = False

        if isinstance(data, str): 
            datalower = data.lower()
            if datalower in self.redactions:
                data = self.redactions[datalower]
            else:
                for find, fix in list(self.redactions.items()):
                    if find in datalower:
                        data = datalower.replace(find, fix)
            return self._redact_generic_re.sub(self._redact_generic_sub, data)
        elif isinstance(data, dict):
            return {self.redact_data(k, False): self.redact_data(v, False) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.redact_data(v, False) for v in data]
        else: 
            return data
