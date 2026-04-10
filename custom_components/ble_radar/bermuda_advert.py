"""
Bermuda's internal representation of a device to scanner relationship.

This can also be thought of as the representation of an advertisement
received by a given scanner, in that it's the advert that links the
device to a scanner. Multiple scanners will receive a given advert, but
each receiver experiences it (well, the rssi) uniquely.

Every bluetooth scanner is a BermudaDevice, but this class
is the nested entry that gets attached to each device's `scanners`
dict. It is a sub-set of a 'device' and will have attributes specific
to the combination of the scanner and the device it is reporting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from bluetooth_data_tools import monotonic_time_coarse

from .const import (
    _LOGGER,
    CONF_ATTENUATION,
    CONF_MAX_VELOCITY,
    CONF_REF_POWER,
    CONF_RSSI_OFFSETS,
    CONF_SMOOTHING_SAMPLES,
    DISTANCE_INFINITE,
    DISTANCE_TIMEOUT,
    HIST_KEEP_COUNT,
)

from .util import clean_charbuf, rssi_to_metres

# --- NUOVO: Importiamo il Filtro di Kalman per stabilizzare il segnale ---
from .helper import KalmanFilter

if TYPE_CHECKING:
    from bleak.backends.scanner import AdvertisementData

    from .bermuda_device import BermudaDevice

# ruff: noqa: PLR1730


class BermudaAdvert(dict):
    """
    Represents details from a scanner relevant to a specific device.
    """

    def __hash__(self) -> int:
        """The device-mac / scanner mac uniquely identifies a received advertisement pair."""
        return hash((self.device_address, self.scanner_address))

    def __init__(
        self,
        parent_device: BermudaDevice,
        advertisementdata: AdvertisementData,
        options,
        scanner_device: BermudaDevice,
    ) -> None:
        self.scanner_address: Final[str] = scanner_device.address
        self.device_address: Final[str] = parent_device.address
        self._device = parent_device
        self.ref_power: float = self._device.ref_power
        self.apply_new_scanner(scanner_device)

        self.options = options

        self.stamp: float = 0
        self.new_stamp: float | None = None
        self.rssi: float | None = None
        
        # --- NUOVO: Variabili per l'RSSI stabilizzato dal filtro ---
        self.kf_rssi = KalmanFilter(q=0.1, r=2.0)
        self.smoothed_rssi: float | None = None

        self.tx_power: float | None = None
        self.rssi_distance: float | None = None
        self.rssi_distance_raw: float
        self.stale_update_count = 0
        self.hist_stamp: list[float] = []
        self.hist_rssi: list[int] = []
        self.hist_distance: list[float] = []
        self.hist_distance_by_interval: list[float] = []
        self.hist_interval = []
        self.hist_velocity: list[float] = []
        self.conf_rssi_offset = self.options.get(CONF_RSSI_OFFSETS, {}).get(self.scanner_address, 0)
        self.conf_ref_power = self.options.get(CONF_REF_POWER)
        self.conf_attenuation = self.options.get(CONF_ATTENUATION)
        self.conf_max_velocity = self.options.get(CONF_MAX_VELOCITY)
        self.conf_smoothing_samples = self.options.get(CONF_SMOOTHING_SAMPLES)
        self.local_name: list[tuple[str, bytes]] = []
        self.manufacturer_data: list[dict[int, bytes]] = []
        self.service_data: list[dict[str, bytes]] = []
        self.service_uuids: list[str] = []

        self.update_advertisement(advertisementdata, self.scanner_device)

    def apply_new_scanner(self, scanner_device: BermudaDevice):
        self.name: str = scanner_device.name
        self.scanner_device = scanner_device
        if self.scanner_address != scanner_device.address:
            _LOGGER.error("Advert %s received new scanner with wrong address %s", self.__repr__(), scanner_device)
        self.area_id: str | None = scanner_device.area_id
        self.area_name: str | None = scanner_device.area_name
        self.scanner_sends_stamps = scanner_device.is_remote_scanner

    def update_advertisement(self, advertisementdata: AdvertisementData, scanner_device: BermudaDevice):
        """Update gets called every time we see a new packet."""
        if scanner_device is not self.scanner_device:
            _LOGGER.debug(
                "Replacing stale scanner device %s with %s", self.scanner_device.__repr__(), scanner_device.__repr__()
            )
            self.apply_new_scanner(scanner_device)

        scanner = self.scanner_device
        new_stamp: float | None = None

        if self.scanner_sends_stamps:
            new_stamp = scanner.async_as_scanner_get_stamp(self.device_address)

            if new_stamp is None:
                self.stale_update_count += 1
                return

            if self.stamp > new_stamp:
                self.stale_update_count += 1
                return

            if self.stamp == new_stamp:
                self.stale_update_count += 1
                return

        elif self.rssi != advertisementdata.rssi:
            new_stamp = monotonic_time_coarse() - 3.0
        else:
            return

        if new_stamp > self.scanner_device.last_seen + 0.01:
            self.scanner_device.last_seen = new_stamp

        if len(self.hist_stamp) == 0 or new_stamp is not None:
            self.rssi = advertisementdata.rssi
            self.hist_rssi.insert(0, self.rssi)

            self._update_raw_distance(reading_is_new=True)

            if new_stamp is not None and self.stamp is not None:
                _interval = new_stamp - self.stamp
            else:
                _interval = None
            self.hist_interval.insert(0, _interval)

            self.stamp = new_stamp or 0
            self.hist_stamp.insert(0, self.stamp)

        self.tx_power = advertisementdata.tx_power

        _want_name_update = False
        if advertisementdata.local_name is not None:
            nametuplet = (clean_charbuf(advertisementdata.local_name), advertisementdata.local_name.encode())
            if len(self.local_name) == 0 or self.local_name[0] != nametuplet:
                self.local_name.insert(0, nametuplet)
                del self.local_name[HIST_KEEP_COUNT:]
                if self._device.name_bt_local_name is None or len(self._device.name_bt_local_name) < len(nametuplet[0]):
                    self._device.name_bt_local_name = nametuplet[0]
                    _want_name_update = True

        if len(self.manufacturer_data) == 0 or self.manufacturer_data[0] != advertisementdata.manufacturer_data:
            self.manufacturer_data.insert(0, advertisementdata.manufacturer_data)
            self._device.process_manufacturer_data(self)
            _want_name_update = True
            del self.manufacturer_data[HIST_KEEP_COUNT:]

        if len(self.service_data) == 0 or self.service_data[0] != advertisementdata.service_data:
            self.service_data.insert(0, advertisementdata.service_data)
            if advertisementdata.service_data not in self.manufacturer_data[1:]:
                _want_name_update = True
            del self.service_data[HIST_KEEP_COUNT:]

        for service_uuid in advertisementdata.service_uuids:
            if service_uuid not in self.service_uuids:
                self.service_uuids.insert(0, service_uuid)
                _want_name_update = True
                del self.service_uuids[HIST_KEEP_COUNT:]

        if _want_name_update:
            self._device.make_name()

        self.new_stamp = new_stamp

    def _update_raw_distance(self, reading_is_new=True) -> float:
        if self.ref_power == 0:
            ref_power = self.conf_ref_power
        else:
            ref_power = self.ref_power

        distance = rssi_to_metres(self.rssi + self.conf_rssi_offset, ref_power, self.conf_attenuation)
        self.rssi_distance_raw = distance
        if reading_is_new:
            self.hist_distance.insert(0, distance)
        elif self.rssi_distance is not None:
            self.rssi_distance = distance
            if len(self.hist_distance) > 0:
                self.hist_distance[0] = distance
            else:
                self.hist_distance.append(distance)
            if len(self.hist_distance_by_interval) > 0:
                self.hist_distance_by_interval[0] = distance
        return distance

    def set_ref_power(self, value: float) -> float | None:
        if value != self.ref_power:
            self.ref_power = value
            return self._update_raw_distance(False)
        return self.rssi_distance_raw

    def calculate_data(self):
        new_stamp = self.new_stamp
        self.new_stamp = None

        if self.rssi_distance is None and new_stamp is not None:
            self.rssi_distance = self.rssi_distance_raw
            # --- NUOVO: Aggiorna l'RSSI stabilizzato ---
            self.smoothed_rssi = self.kf_rssi.update(self.rssi)
            
            if self.rssi_distance_raw is not None:
                self.hist_distance_by_interval.clear()
                self.hist_distance_by_interval.append(self.rssi_distance_raw)

        elif new_stamp is None and (self.stamp is None or self.stamp < monotonic_time_coarse() - DISTANCE_TIMEOUT):
            self.rssi_distance = None
            # --- NUOVO: Resetta il filtro se il dispositivo sparisce ---
            self.smoothed_rssi = None
            self.kf_rssi = KalmanFilter(q=0.1, r=2.0)
            
            if len(self.hist_distance_by_interval) > 0:
                self.hist_distance_by_interval.clear()

        else:
            # --- NUOVO: Aggiorna l'RSSI stabilizzato anche nei cicli normali ---
            if new_stamp is not None and self.rssi is not None:
                self.smoothed_rssi = self.kf_rssi.update(self.rssi)

            if len(self.hist_stamp) > 1:
                velo_newdistance = self.hist_distance[0]
                velo_newstamp = self.hist_stamp[0]
                peak_velocity = 0
                delta_t = velo_newstamp - self.hist_stamp[1]
                delta_d = velo_newdistance - self.hist_distance[1]
                if delta_t > 0:
                    peak_velocity = delta_d / delta_t
                if peak_velocity >= 0:
                    for old_distance, old_stamp in zip(self.hist_distance[2:], self.hist_stamp[2:], strict=False):
                        if old_stamp is None:
                            continue
                        delta_t = velo_newstamp - old_stamp
                        if delta_t <= 0:
                            continue
                        delta_d = velo_newdistance - old_distance
                        velocity = delta_d / delta_t
                        if velocity > peak_velocity:
                            peak_velocity = velocity
                velocity = peak_velocity
            else:
                velocity = 0

            self.hist_velocity.insert(0, velocity)

            if velocity > self.conf_max_velocity:
                if len(self.hist_distance_by_interval) > 0:
                    self.hist_distance_by_interval.insert(0, self.hist_distance_by_interval[0])
                else:
                    self.hist_distance_by_interval.insert(0, self.rssi_distance_raw)
            else:
                self.hist_distance_by_interval.insert(0, self.rssi_distance_raw)

            if len(self.hist_distance_by_interval) > self.conf_smoothing_samples:
                del self.hist_distance_by_interval[self.conf_smoothing_samples :]

            dist_total: float = 0
            local_min: float = self.rssi_distance_raw or DISTANCE_INFINITE
            for distance in self.hist_distance_by_interval:
                if distance is not None and distance <= local_min:
                    local_min = distance
                dist_total += local_min

            if (_hist_dist_len := len(self.hist_distance_by_interval)) > 0:
                movavg = dist_total / _hist_dist_len
            else:
                movavg = local_min

            if self.rssi_distance_raw is None or movavg < self.rssi_distance_raw:
                self.rssi_distance = movavg
            else:
                self.rssi_distance = self.rssi_distance_raw

        del self.hist_distance[HIST_KEEP_COUNT:]
        del self.hist_interval[HIST_KEEP_COUNT:]
        del self.hist_rssi[HIST_KEEP_COUNT:]
        del self.hist_stamp[HIST_KEEP_COUNT:]
        del self.hist_velocity[HIST_KEEP_COUNT:]

    def to_dict(self):
        out = {}
        for var, val in vars(self).items():
            if val in [self.options]:
                continue
            if val in [self.options, self._device, self.scanner_device, self.kf_rssi]:
                out[var] = val.__repr__()
                continue
            if val is self.local_name:
                out[var] = {}
                for namestr, namebytes in self.local_name:
                    out[var][namestr] = namebytes.hex()
                continue
            if val is self.manufacturer_data:
                out[var] = {}
                for manrow in self.manufacturer_data:
                    for manid, manbytes in manrow.items():
                        out[var][manid] = manbytes.hex()
                continue
            if val is self.service_data:
                out[var] = {}
                for svrow in self.service_data:
                    for svid, svbytes in svrow.items():
                        out[var][svid] = svbytes.hex()
                continue
            if isinstance(val, str | int):
                out[var] = val
                continue
            if isinstance(val, float):
                out[var] = round(val, 4)
                continue
            if isinstance(val, list):
                out[var] = []
                for row in val:
                    if isinstance(row, float):
                        out[var].append(round(row, 4))
                    else:
                        out[var].append(row)
                continue
            out[var] = val.__repr__()
        return out

    def __repr__(self) -> str:
        return f"{self.device_address}__{self.scanner_device.name}"
