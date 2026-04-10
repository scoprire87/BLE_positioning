"""
Bermuda's internal representation of a bluetooth device.

Each discovered bluetooth device (ie, every found transmitter) will
have one of these entries created for it. These are not HA 'devices' but
our own internal thing. They directly correspond to the entries you will
see when calling the dump_devices service call.

Even devices which are not configured/tracked will get entries created
for them, so we can use them to contribute towards measurements.
"""

from __future__ import annotations

import binascii
import re
from typing import TYPE_CHECKING, Final

from bluetooth_data_tools import monotonic_time_coarse
from homeassistant.components.bluetooth import (
    BaseHaRemoteScanner,
    BaseHaScanner,
    BluetoothChange,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.private_ble_device import coordinator as pble_coordinator
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from homeassistant.util import slugify

from .bermuda_advert import BermudaAdvert
from .const import (
    _LOGGER,
    _LOGGER_SPAM_LESS,
    ADDR_TYPE_IBEACON,
    ADDR_TYPE_PRIVATE_BLE_DEVICE,
    BDADDR_TYPE_NOT_MAC48,
    BDADDR_TYPE_OTHER,
    BDADDR_TYPE_RANDOM_RESOLVABLE,
    BDADDR_TYPE_RANDOM_STATIC,
    BDADDR_TYPE_RANDOM_UNRESOLVABLE,
    BDADDR_TYPE_UNKNOWN,
    CONF_DEVICES,
    CONF_DEVTRACK_TIMEOUT,
    DEFAULT_DEVTRACK_TIMEOUT,
    DOMAIN,
    ICON_DEFAULT_AREA,
    ICON_DEFAULT_FLOOR,
    METADEVICE_IBEACON_DEVICE,
    METADEVICE_PRIVATE_BLE_DEVICE,
    METADEVICE_TYPE_IBEACON_SOURCE,
)
from .util import mac_math_offset, mac_norm

if TYPE_CHECKING:
    from bleak.backends.scanner import AdvertisementData

    from .coordinator import BermudaDataUpdateCoordinator


class BermudaDevice(dict):
    """
    This class is to represent a single bluetooth "device" tracked by Bermuda.

    "device" in this context means a bluetooth receiver like an ESPHome
    running bluetooth_proxy or a bluetooth transmitter such as a beacon,
    a thermometer, watch or phone etc.

    We're not storing this as an Entity because we don't want all devices to
    become entities in homeassistant, since there might be a _lot_ of them.
    """

    def __hash__(self) -> int:
        """A BermudaDevice can be uniquely identified by the address used."""
        return hash(self.address)

    def __init__(self, address: str, coordinator: BermudaDataUpdateCoordinator) -> None:
        """Initial (empty) data."""
        _address = mac_norm(address)
        self.name: str = f"{DOMAIN}_{slugify(_address)}"  # "preferred" name built by Bermuda.
        self.name_bt_serviceinfo: str | None = None  # From serviceinfo.device.name
        self.name_bt_local_name: str | None = None  # From service_info.advertisement.local_name
        self.name_devreg: str | None = None  # From device registry, for other integrations like scanners, pble devices
        self.name_by_user: str | None = None  # Any user-defined (in the HA UI) name discovered for a device.
        self.address: Final[str] = _address
        self.address_ble_mac: str = _address
        self.address_wifi_mac: str | None = None
        # We use a weakref to avoid any possible GC issues (only likely if we add a __del__ method, but *shrug*)
        self._coordinator: BermudaDataUpdateCoordinator = coordinator
        self.ref_power: float = 0  # If non-zero, use in place of global ref_power.
        self.ref_power_changed: float = 0  # Stamp for last change to ref_power, for cache zapping.
        self.options = self._coordinator.options
        self.unique_id: str | None = _address  # mac address formatted.
        self.address_type = BDADDR_TYPE_UNKNOWN

        self.ar = ar.async_get(self._coordinator.hass)
        self.fr = fr.async_get(self._coordinator.hass)

        self.area: ar.AreaEntry | None = None
        self.area_id: str | None = None
        self.area_name: str | None = None
        self.area_icon: str = ICON_DEFAULT_AREA
        self.area_last_seen: str | None = None
        self.area_last_seen_id: str | None = None
        self.area_last_seen_icon: str = ICON_DEFAULT_AREA

        self.area_distance: float | None = None  # how far this dev is from that area
        self.area_rssi: float | None = None  # rssi from closest scanner
        self.area_advert: BermudaAdvert | None = None  # currently closest BermudaScanner

        # --- NUOVO: Variabili per la tracciatura Radar ---
        self.radar_room: str | None = None
        self.radar_match_dist: float | None = None

        self.floor: fr.FloorEntry | None = None
        self.floor_id: str | None = None
        self.floor_name: str | None = None
        self.floor_icon: str = ICON_DEFAULT_FLOOR
        self.floor_level: str | None = None

        self.zone: str = STATE_NOT_HOME  # STATE_HOME or STATE_NOT_HOME
        self.manufacturer: str | None = None
        self._hascanner: BaseHaRemoteScanner | BaseHaScanner | None = None  # HA's scanner
        self._is_scanner: bool = False
        self._is_remote_scanner: bool | None = None
        self.stamps: dict[str, float] = {}
        self.metadevice_type: set = set()
        self.metadevice_sources: list[str] = []  # list of MAC addresses that have/should match this beacon
        self.beacon_unique_id: str | None = None  # combined uuid_major_minor for *really* unique id
        self.beacon_uuid: str | None = None
        self.beacon_major: str | None = None
        self.beacon_minor: str | None = None
        self.beacon_power: float | None = None

        self.entry_id: str | None = None  # used for scanner devices
        self.create_sensor: bool = False  # Create/update a sensor for this device
        self.create_sensor_done: bool = False  # Sensor should now exist
        self.create_tracker_done: bool = False  # device_tracker should now exist
        self.create_number_done: bool = False
        self.create_button_done: bool = False
        self.create_all_done: bool = False  # All platform entities are done and ready.
        self.last_seen: float = 0  # stamp from most recent scanner spotting. monotonic_time_coarse
        self.diag_area_switch: str | None = None  # saves output of AreaTests
        self.adverts: dict[
            tuple[str, str], BermudaAdvert
        ] = {}  # str will be a scanner address OR a deviceaddress__scanneraddress
        self._async_process_address_type()

    def _async_process_address_type(self):
        """
        Identify the address type (MAC, IRK, iBeacon etc) and perform any setup.
        """
        if self.address_type is BDADDR_TYPE_UNKNOWN:
            if self.address.count(":") != 5:
                if re.match("^[A-Fa-f0-9]{32}_[A-Fa-f0-9]*_[A-Fa-f0-9]*$", self.address):
                    self.address_type = ADDR_TYPE_IBEACON
                    self.metadevice_type.add(METADEVICE_IBEACON_DEVICE)
                    self.beacon_unique_id = self.address
                elif re.match("^[A-Fa-f0-9]{32}$", self.address):
                    self.metadevice_type.add(METADEVICE_PRIVATE_BLE_DEVICE)
                    self.address_type = ADDR_TYPE_PRIVATE_BLE_DEVICE
                    self.beacon_unique_id = self.address
                    _irk_bytes = binascii.unhexlify(self.address)
                    _pble_coord = pble_coordinator.async_get_coordinator(self._coordinator.hass)
                    self._coordinator.config_entry.async_on_unload(
                        _pble_coord.async_track_service_info(self.async_handle_pble_callback, _irk_bytes)
                    )
                    _LOGGER.debug("Private BLE Callback registered for %s, %s", self.name, self.address)
                    
                    self._coordinator.config_entry.async_on_unload(
                        self._coordinator.irk_manager.register_irk_callback(self.async_handle_pble_callback, _irk_bytes)
                    )
                    self._coordinator.irk_manager.add_irk(_irk_bytes)
                else:
                    self.address_type = BDADDR_TYPE_NOT_MAC48
            elif len(self.address) == 17:
                top_bits = int(self.address[0:1], 16) >> 2
                if top_bits & 0b00:
                    self.address_type = BDADDR_TYPE_RANDOM_UNRESOLVABLE
                elif top_bits & 0b01:
                    _LOGGER.debug("Identified Resolvable Private (potential IRK source) Address on %s", self.address)
                    self.address_type = BDADDR_TYPE_RANDOM_RESOLVABLE
                    self._coordinator.irk_manager.check_mac(self.address)
                elif top_bits & 0b10:
                    self.address_type = "reserved"
                    _LOGGER.debug("Hey, got one of those reserved MACs, %s", self.address)
                elif top_bits & 0b11:
                    self.address_type = BDADDR_TYPE_RANDOM_STATIC
            else:
                self.address_type = BDADDR_TYPE_OTHER
                name, generic = self._coordinator.get_manufacturer_from_id(self.address[:8])
                if name and (self.manufacturer is None or not generic):
                    self.manufacturer = name

    @property
    def is_scanner(self):
        return self._is_scanner

    @property
    def is_remote_scanner(self):
        return self._is_remote_scanner

    def async_as_scanner_nolonger(self):
        """Call when this device is unregistered as a BaseHaScanner."""
        self._is_scanner = False
        self._is_remote_scanner = False
        self._coordinator.scanner_list_del(self)

    def async_as_scanner_init(self, ha_scanner: BaseHaScanner):
        """Configure this device as a scanner device."""
        if self._hascanner is ha_scanner:
            return

        _first_init = self._hascanner is None

        self._hascanner = ha_scanner
        self._is_scanner = True
        if isinstance(self._hascanner, BaseHaRemoteScanner):
            self._is_remote_scanner = True
        else:
            self._is_remote_scanner = False
        self._coordinator.scanner_list_add(self)

        self.async_as_scanner_resolve_device_entries()

        if _first_init:
            self.async_as_scanner_update(ha_scanner)

    def async_as_scanner_resolve_device_entries(self):
        """From the known MAC address, resolve any relevant device entries and names etc."""
        if self._hascanner is None:
            _LOGGER.warning("Scanner %s has no ha_scanner, can not resolve devices.", self.__repr__())
            return

        connlist = set()
        maclist = set()

        scanner_devreg_bt = None
        scanner_devreg_mac = None
        scanner_devreg_mac_address = None
        scanner_devreg_bt_address = None

        for offset in range(-3, 3):
            if (altmac := mac_math_offset(self.address, offset)) is not None:
                connlist.add(("bluetooth", altmac.upper()))
                connlist.add(("mac", altmac))
                maclist.add(altmac)

        devreg_devices = self._coordinator.dr.devices.get_entries(None, connections=connlist)
        devreg_count = 0
        devreg_stringlist = ""
        for devreg_device in devreg_devices:
            devreg_count += 1
            devreg_stringlist += f"** {devreg_device.name_by_user or devreg_device.name}\n"
            for conn in devreg_device.connections:
                if conn[0] == "bluetooth":
                    scanner_devreg_bt = devreg_device
                    scanner_devreg_bt_address = conn[1].lower()
                if conn[0] == "mac":
                    scanner_devreg_mac = devreg_device
                    scanner_devreg_mac_address = conn[1]

        if devreg_count not in (1, 2, 3):
            _LOGGER_SPAM_LESS.warning(
                f"multimatch_devreg_{self._hascanner.source}",
                "Unexpectedly got %d device registry matches for %s: %s\n",
                devreg_count,
                self._hascanner.name,
                devreg_stringlist,
            )

        if scanner_devreg_bt is None and scanner_devreg_mac is None:
            _LOGGER_SPAM_LESS.error(
                f"scanner_not_in_devreg_{self.address:s}",
                "Failed to find scanner %s (%s) in Device Registry",
                self._hascanner.name,
                self._hascanner.source,
            )
            return

        _area_id = None
        _bt_name = None
        _mac_name = None
        _bt_name_by_user = None
        _mac_name_by_user = None

        if scanner_devreg_bt is not None:
            _area_id = scanner_devreg_bt.area_id
            self.entry_id = scanner_devreg_bt.id
            _bt_name_by_user = scanner_devreg_bt.name_by_user
            _bt_name = scanner_devreg_bt.name
        if scanner_devreg_mac is not None:
            _area_id = _area_id or scanner_devreg_mac.area_id
            self.entry_id = self.entry_id or scanner_devreg_mac.id
            _mac_name = scanner_devreg_mac.name
            _mac_name_by_user = scanner_devreg_mac.name_by_user

        self.unique_id = scanner_devreg_mac_address or scanner_devreg_bt_address or self._hascanner.source
        self.address_ble_mac = scanner_devreg_bt_address or scanner_devreg_mac_address or self._hascanner.source
        self.address_wifi_mac = scanner_devreg_mac_address

        for mac in (
            self.address_ble_mac,
            mac_math_offset(self.address_wifi_mac, 2),
            mac_math_offset(self.address_wifi_mac, -1),
        ):
            if (
                mac is not None
                and mac not in self.metadevice_sources
                and mac != self.address
            ):
                self.metadevice_sources.append(mac)

        self.name_devreg = _mac_name or _bt_name
        self.name_by_user = _bt_name_by_user or _mac_name_by_user
        self.make_name()
        self._update_area_and_floor(_area_id)

    def _update_area_and_floor(self, area_id: str | None):
        """Given an area_id, update the area and floor properties."""
        if area_id is None:
            self.area = None
            self.area_id = None
            self.area_name = None
            self.area_icon = ICON_DEFAULT_AREA
            self.floor = None
            self.floor_id = None
            self.floor_name = None
            self.floor_icon = ICON_DEFAULT_FLOOR
            self.floor_level = None
            return

        if area := self.ar.async_get_area(area_id):
            self.area = area
            self.area_id = area_id
            self.area_name = area.name
            self.area_icon = area.icon or ICON_DEFAULT_AREA
            self.floor_id = area.floor_id
            if self.floor_id is not None:
                self.floor = self.fr.async_get_floor(self.floor_id)
                if self.floor is not None:
                    self.floor_name = self.floor.name
                    self.floor_icon = self.floor.icon or ICON_DEFAULT_FLOOR
                    self.floor_level = self.floor_level
                else:
                    _LOGGER_SPAM_LESS.warning(
                        f"floor_id invalid for {self.__repr__()}",
                        "Update of area for %s has invalid floor_id of %s",
                        self.__repr__(),
                        self.floor_id,
                    )
                    self.floor_id = None
                    self.floor_name = "Invalid Floor ID"
                    self.floor_icon = ICON_DEFAULT_FLOOR
                    self.floor_level = None
            else:
                self.floor = None
                self.floor_name = None
                self.floor_icon = ICON_DEFAULT_FLOOR
        else:
            _LOGGER_SPAM_LESS.warning(
                f"no_area_on_update{self.name}",
                "Setting area of %s with invalid area id of %s",
                self.__repr__(),
                area_id,
            )
            self.area = None
            self.area_name = f"Invalid Area for {self.name}"
            self.area_icon = ICON_DEFAULT_AREA
            self.floor = None
            self.floor_id = None
            self.floor_name = None
            self.floor_icon = ICON_DEFAULT_FLOOR

    def async_as_scanner_update(self, ha_scanner: BaseHaScanner):
        """Fast update of scanner details per update-cycle."""
        if self._hascanner is not ha_scanner:
            if self._hascanner is not None:
                _LOGGER.info("Received replacement ha_scanner object for %s", self.__repr__)
            self.async_as_scanner_init(ha_scanner)

        scannerstamp = 0 - ha_scanner.time_since_last_detection() + monotonic_time_coarse()
        if scannerstamp > self.last_seen:
            self.last_seen = scannerstamp
        elif self.last_seen - scannerstamp > 0.8:
            _LOGGER.debug(
                "Scanner stamp for %s went backwards %.2fs. new %f < last %f",
                self.name,
                self.last_seen - scannerstamp,
                scannerstamp,
                self.last_seen,
            )

        if self.is_remote_scanner:
            if self._coordinator.hass_version_min_2025_4:
                self.stamps = self._hascanner.discovered_device_timestamps  # type: ignore
            else:
                self.stamps = self._hascanner._discovered_device_timestamps  # type: ignore # noqa: SLF001

    def async_as_scanner_get_stamp(self, address: str) -> float | None:
        """Returns the latest known timestamp for the given address from this scanner."""
        if self.is_remote_scanner:
            if self.stamps is None:
                _LOGGER_SPAM_LESS.debug(
                    f"remote_no_stamps{self.address}", "Remote Scanner %s has no stamps dict", self.__repr__()
                )
                return None
            if len(self.stamps) == 0:
                _LOGGER_SPAM_LESS.debug(
                    f"remote_stamps_empty{self.address}", "Remote scanner %s has an empty stamps dict", self.__repr__()
                )
                return None
            try:
                return self.stamps[address.upper()]
            except (KeyError, AttributeError):
                return None
        return None

    @callback
    def async_handle_pble_callback(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        """If this is an IRK device, this callback will be called on IRK updates."""
        address = mac_norm(service_info.address)
        if address not in self.metadevice_sources:
            self.metadevice_sources.insert(0, address)
            _LOGGER.debug("Got %s callback for new IRK address on %s of %s", change, self.name, address)
            self._coordinator.irk_manager.add_macirk(address, bytes.fromhex(self.address))

    def make_name(self):
        """Refreshes self.name, sets and returns it, based on naming preferences."""
        _newname = (
            self.name_by_user
            or self.name_devreg
            or self.name_bt_local_name
            or self.name_bt_serviceinfo
            or self.beacon_unique_id
        )

        if _newname is not None:
            self.name = _newname
        elif self.address_type != BDADDR_TYPE_NOT_MAC48:
            if self.manufacturer:
                _prefix = f"{slugify(self.manufacturer)}"
            else:
                _prefix = DOMAIN
            self.name = f"{_prefix}_{slugify(self.address)}"

        return self.name

    def set_ref_power(self, new_ref_power: float):
        """Set a new reference power for this device and immediately apply."""
        if new_ref_power != self.ref_power:
            self.ref_power = new_ref_power
            nearest_distance = 9999
            nearest_scanner = None
            for advert in self.adverts.values():
                rawdist = advert.set_ref_power(new_ref_power)
                if rawdist is not None and rawdist < nearest_distance:
                    nearest_distance = rawdist
                    nearest_scanner = advert
            self.apply_scanner_selection(nearest_scanner)
            self.ref_power_changed = monotonic_time_coarse()

    def get_current_fingerprint(self) -> dict[str, float]:
        """
        --- NUOVO METODO RADAR ---
        Estrae l'impronta digitale corrente del dispositivo. 
        Ritorna un dizionario {mac_scanner: rssi_stabilizzato} che verrà usato 
        dal KNN per determinare la stanza.
        """
        fingerprint = {}
        for advert in self.adverts.values():
            if hasattr(advert, 'smoothed_rssi') and advert.smoothed_rssi is not None:
                fingerprint[advert.scanner_address] = advert.smoothed_rssi
            elif advert.rssi is not None:
                # Fallback se il Kalman Filter non è ancora inizializzato
                fingerprint[advert.scanner_address] = float(advert.rssi)
        return fingerprint

    def apply_radar_room(self, room_name: str | None, match_dist: float | None = None):
        """
        --- NUOVO METODO RADAR ---
        Sovrascrive la stanza rilevata in base al calcolo di fingerprinting KNN,
        rendendo la rilevazione immune ai muri e agli ostacoli.
        """
        old_area = self.area_name
        self.radar_room = room_name
        self.radar_match_dist = match_dist

        if room_name and room_name not in ["Sconosciuta", "Nessuna Mappa"]:
            self.area_name = room_name
            self.area_id = slugify(room_name)
            self.area_last_seen = room_name
            
            # Sostituiamo la distanza fisica con la distanza Euclidea come metrica di confidenza
            if match_dist is not None:
                self.area_distance = match_dist

        if (old_area != self.area_name) and self.create_sensor:
            _LOGGER.debug(
                "BLE Radar ha spostato %s da '%s' a '%s' (Distanza Euclidea: %s)",
                self.name,
                old_area,
                self.area_name,
                match_dist
            )

    def apply_scanner_selection(self, bermuda_advert: BermudaAdvert | None):
        """Given a BermudaAdvert entry, apply the distance and area attributes."""
        old_area = self.area_name
        if bermuda_advert is not None and bermuda_advert.rssi_distance is not None:
            self.area_advert = bermuda_advert
            self._update_area_and_floor(bermuda_advert.area_id)
            self.area_distance = bermuda_advert.rssi_distance
            self.area_rssi = bermuda_advert.rssi
            self.area_last_seen = self.area_name
            self.area_last_seen_id = self.area_id
            self.area_last_seen_icon = self.area_icon
        else:
            self.area_advert = None
            self._update_area_and_floor(None)
            self.area_distance = None
            self.area_rssi = None

        if (old_area != self.area_name) and self.create_sensor:
            _LOGGER.debug(
                "Device %s was in '%s', now '%s'",
                self.name,
                old_area,
                self.area_name,
            )

    def get_scanner(self, scanner_address) -> BermudaAdvert | None:
        """Given a scanner address, return the most recent BermudaDeviceScanner that matches."""
        _stamp = 0
        _found_scanner = None
        for advert in self.adverts.values():
            if advert.scanner_address == scanner_address:
                if _stamp == 0 or (advert.stamp is not None and advert.stamp > _stamp):
                    _found_scanner = advert
                    _stamp = _found_scanner.stamp or 0

        return _found_scanner

    def calculate_data(self):
        """Call after doing update_scanner() calls so distances are smoothed."""
        for advert in self.adverts.values():
            if isinstance(advert, BermudaAdvert):
                advert.calculate_data()
            else:
                _LOGGER_SPAM_LESS.error(
                    "scanner_not_instance", "Scanner device is not a BermudaDevice instance, skipping."
                )

        if (
            self.last_seen is not None
            and monotonic_time_coarse() - self.options.get(CONF_DEVTRACK_TIMEOUT, DEFAULT_DEVTRACK_TIMEOUT)
            < self.last_seen
        ):
            self.zone = STATE_HOME
        else:
            self.zone = STATE_NOT_HOME

        if self.address.upper() in self.options.get(CONF_DEVICES, []):
            self.create_sensor = True

    def process_advertisement(self, scanner_device: BermudaDevice, advertisementdata: AdvertisementData):
        """Add/Update a scanner/advert entry pair on this device."""
        scanner_address = mac_norm(scanner_device.address)
        device_address = self.address
        advert_tuple = (device_address, scanner_address)

        if len(self.metadevice_sources) > 0 and not self._is_scanner:
            _LOGGER_SPAM_LESS.debug(
                f"meta_{self.address}_{advert_tuple}",
                "process_advertisement called on a metadevice (%s)",
                self.__repr__(),
                advert_tuple,
            )
            return

        if advert_tuple in self.adverts:
            self.adverts[advert_tuple].update_advertisement(advertisementdata, scanner_device)
            device_advert = self.adverts[advert_tuple]
        else:
            device_advert = self.adverts[advert_tuple] = BermudaAdvert(
                self,
                advertisementdata,
                self.options,
                scanner_device,
            )

        if device_advert.stamp is not None and self.last_seen < device_advert.stamp:
            self.last_seen = device_advert.stamp

    def process_manufacturer_data(self, advert: BermudaAdvert):
        """Parse manufacturer data for maker name and iBeacon etc."""
        _want_name_update = False
        for uuid in advert.service_uuids:
            name, generic = self._coordinator.get_manufacturer_from_id(uuid[4:8])
            if name and (self.manufacturer is None or not generic):
                self.manufacturer = name
                _want_name_update = True
        if _want_name_update:
            self.make_name()

        for manudict in advert.manufacturer_data:
            for company_code, man_data in manudict.items():
                name, generic = self._coordinator.get_manufacturer_from_id(company_code)
                if name and (self.manufacturer is None or not generic):
                    self.manufacturer = name

                if company_code == 0x004C:
                    if man_data[:1] == b"\x02":
                        if len(man_data) >= 22:
                            self.metadevice_type.add(METADEVICE_TYPE_IBEACON_SOURCE)
                            self.beacon_uuid = man_data[2:18].hex().lower()
                            self.beacon_major = str(int.from_bytes(man_data[18:20], byteorder="big"))
                            self.beacon_minor = str(int.from_bytes(man_data[20:22], byteorder="big"))
                        if len(man_data) >= 23:
                            self.beacon_power = int.from_bytes([man_data[22]], signed=True)

                        self.beacon_unique_id = f"{self.beacon_uuid}_{self.beacon_major}_{self.beacon_minor}"
                        self.make_name()
                        self._coordinator.register_ibeacon_source(self)

    def to_dict(self):
        """Convert class to serialisable dict for dump_devices."""
        out = {}
        for var, val in vars(self).items():
            if val is None:
                out[var] = val
                continue
            if val in [self._coordinator, self.floor, self.area, self.ar, self.fr]:
                continue
            if val in [self._hascanner, self.area, self.floor, self.ar, self.fr]:
                if hasattr(val, "__repr__"):
                    out[var] = val.__repr__()
                continue
            if val is self.adverts:
                advertout = {}
                for advert in self.adverts.values():
                    advertout[f"{advert.device_address}____{advert.scanner_address}"] = advert.to_dict()
                out[var] = advertout
                continue
            out[var] = val
        return out

    def __repr__(self) -> str:
        """Help debug devices and figure out what device it is at a glance."""
        return f"{self.name} [{self.address}]"
