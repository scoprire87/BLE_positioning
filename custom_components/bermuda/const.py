"""Constants for BLE Radar (Bermuda fork)."""

# Base component constants
from __future__ import annotations

import logging
from enum import Enum
from typing import Final

from homeassistant.const import Platform

from .log_spam_less import BermudaLogSpamLess

NAME = "BLE Radar"
DOMAIN = "ble_radar"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "1.0.0"

ATTRIBUTION = "Forked and improved for Radio Mapping from Bermuda BLE"
ISSUE_URL = "https://github.com/scoprire87/BLE_positioning/issues"

# Icons
ICON = "mdi:radar"
ICON_DEFAULT_AREA: Final = "mdi:land-plots-marker"
ICON_DEFAULT_FLOOR: Final = "mdi:selection-marker" 

REPAIR_SCANNER_WITHOUT_AREA = "scanner_without_area"

# Device classes
BINARY_SENSOR_DEVICE_CLASS = "connectivity"

# Platforms (Ora includiamo il Binary Sensor!)
PLATFORMS = [
    Platform.SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.NUMBER,
    Platform.BINARY_SENSOR
]

DOMAIN_PRIVATE_BLE_DEVICE = "private_ble_device"

# Signal names we are using:
SIGNAL_DEVICE_NEW = f"{DOMAIN}-device-new"
SIGNAL_SCANNERS_CHANGED = f"{DOMAIN}-scanners-changed"

UPDATE_INTERVAL = 1.05  

LOGSPAM_INTERVAL = 22

DISTANCE_TIMEOUT = 30  
DISTANCE_INFINITE = 999 

AREA_MAX_AD_AGE: Final = max(DISTANCE_TIMEOUT / 3, UPDATE_INTERVAL * 2)

# Beacon-handling constants.
METADEVICE_TYPE_IBEACON_SOURCE: Final = "beacon source" 
METADEVICE_IBEACON_DEVICE: Final = "beacon device"  
METADEVICE_TYPE_PRIVATE_BLE_SOURCE: Final = "private_ble_src" 
METADEVICE_PRIVATE_BLE_DEVICE: Final = "private_ble_device"  

METADEVICE_SOURCETYPES: Final = {METADEVICE_TYPE_IBEACON_SOURCE, METADEVICE_TYPE_PRIVATE_BLE_SOURCE}
METADEVICE_DEVICETYPES: Final = {METADEVICE_IBEACON_DEVICE, METADEVICE_PRIVATE_BLE_DEVICE}

# Bluetooth Device Address Type 
BDADDR_TYPE_UNKNOWN: Final = "bd_addr_type_unknown" 
BDADDR_TYPE_OTHER: Final = "bd_addr_other"  
BDADDR_TYPE_RANDOM_RESOLVABLE: Final = "bd_addr_random_resolvable"
BDADDR_TYPE_RANDOM_UNRESOLVABLE: Final = "bd_addr_random_unresolvable"
BDADDR_TYPE_RANDOM_STATIC: Final = "bd_addr_random_static"
BDADDR_TYPE_NOT_MAC48: Final = "bd_addr_not_mac48"
ADDR_TYPE_IBEACON: Final = "addr_type_ibeacon"
ADDR_TYPE_PRIVATE_BLE_DEVICE: Final = "addr_type_private_ble_device"

class IrkTypes(Enum):
    ADRESS_NOT_EVALUATED = bytes.fromhex("0000")  
    NOT_RESOLVABLE_ADDRESS = bytes.fromhex("0001")  
    NO_KNOWN_IRK_MATCH = bytes.fromhex("0002")  

    @classmethod
    def unresolved(cls) -> list[bytes]:
        return [bytes(k.value) for k in IrkTypes.__members__.values()]


PRUNE_MAX_COUNT = 1000  
PRUNE_TIME_INTERVAL = 180  
PRUNE_TIME_DEFAULT = 86400  
PRUNE_TIME_UNKNOWN_IRK = 240  
PRUNE_TIME_KNOWN_IRK: Final[int] = 16 * 60  
PRUNE_TIME_REDACTIONS: Final[int] = 10 * 60  
SAVEOUT_COOLDOWN = 10  

DOCS = {}
HIST_KEEP_COUNT = 10  

# Configuration and options
CONFDATA_SCANNERS = "scanners"
CONF_DEVICES = "configured_devices"
CONF_SCANNERS = "configured_scanners"

CONF_MAX_RADIUS, DEFAULT_MAX_RADIUS = "max_area_radius", 20
CONF_MAX_VELOCITY, DEFAULT_MAX_VELOCITY = "max_velocity", 3
CONF_DEVTRACK_TIMEOUT, DEFAULT_DEVTRACK_TIMEOUT = "devtracker_nothome_timeout", 30

CONF_ATTENUATION, DEFAULT_ATTENUATION = "attenuation", 3
CONF_REF_POWER, DEFAULT_REF_POWER = "ref_power", -55.0

CONF_SAVE_AND_CLOSE = "save_and_close"
CONF_SCANNER_INFO = "scanner_info"
CONF_RSSI_OFFSETS = "rssi_offsets"

CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL = "update_interval", 10
CONF_SMOOTHING_SAMPLES, DEFAULT_SMOOTHING_SAMPLES = "smoothing_samples", 20

# --- NUOVE COSTANTI PER BLE RADAR ---
# Parametri del filtro di Kalman per stabilizzare gli sbalzi di RSSI
KALMAN_Q = 0.1  # Varianza del processo (velocità di movimento)
KALMAN_R = 2.0  # Varianza della misura (rumore del segnale)

# Nomi dei servizi registrati in __init__.py
SERVICE_CALIBRATE_ANCHOR = "calibrate_anchor"
SERVICE_MAP_ROOM_POINT = "map_room_point"

DEFAULT_NAME = DOMAIN

_LOGGER: logging.Logger = logging.getLogger(__package__)
_LOGGER_SPAM_LESS = BermudaLogSpamLess(_LOGGER, LOGSPAM_INTERVAL)

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
Forked for Radio Mapping and Kalman Filtering.
Issues? {ISSUE_URL}
-------------------------------------------------------------------
"""
