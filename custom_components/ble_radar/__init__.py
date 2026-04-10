"""
Custom integration to integrate Bermuda BLE Trilateration with Home Assistant.

For more details about this integration, please refer to
https://github.com/agittins/bermuda
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_registry import async_migrate_entries

from .const import _LOGGER, DOMAIN, PLATFORMS, STARTUP_MESSAGE
from .coordinator import BermudaDataUpdateCoordinator
from .util import mac_math_offset, mac_norm
from .storage import RadarStorage

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceEntry

type BermudaConfigEntry = ConfigEntry[BermudaData]


@dataclass
class BermudaData:
    """Holds global data for Bermuda."""

    storage: RadarStorage  # <-- Spostato in alto
    coordinator: BermudaDataUpdateCoordinator | None = None  # <-- Reso opzionale per l'inizializzazione


CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: BermudaConfigEntry) -> bool:
    """Set up this integration using UI."""
    if hass.data.get(DOMAIN) is None:
        _LOGGER.info(STARTUP_MESSAGE)
    
    # 1. Inizializza lo storage della mappa
    radar_storage = RadarStorage(hass)

    # 2. ASSEGNA SUBITO runtime_data in modo che il coordinatore possa trovarlo
    entry.runtime_data = BermudaData(storage=radar_storage)

    # 3. ORA inizializza il coordinatore (che leggerà con successo entry.runtime_data.storage)
    coordinator = BermudaDataUpdateCoordinator(hass, entry)
    
    # 4. Aggiorna l'oggetto inserendo il coordinatore
    entry.runtime_data.coordinator = coordinator

    async def on_failure():
        _LOGGER.debug("Coordinator last update failed, rasing ConfigEntryNotReady")
        raise ConfigEntryNotReady

    try:
        await coordinator.async_refresh()
    except Exception as ex:  # noqa: BLE001
        _LOGGER.exception(ex)
        await on_failure()
    if not coordinator.last_update_success:
        await on_failure()

    # --- INIZIO NUOVO CODICE: Servizi di Calibrazione ---
    
    async def handle_calibrate_anchor(call):
        """Associa un dispositivo a uno scanner (ancora) per tarare il segnale."""
        scanner_id = call.data.get("scanner_id")
        ref_rssi = call.data.get("ref_rssi", -59)
        radar_storage.save_anchor(scanner_id, ref_rssi)
        _LOGGER.info("Calibrata ancora %s con RSSI %s", scanner_id, ref_rssi)

    async def handle_map_room_point(call):
        """Salva l'impronta digitale radio di un punto/stanza."""
        room_name = call.data.get("room_name")
        target_mac = call.data.get("target_mac")

        # Recupera il vettore RSSI attuale per il target_mac dal coordinator
        fingerprint = {}
        if target_mac:
            target_mac_norm = mac_norm(target_mac)
            if target_mac_norm in coordinator.devices:
                device = coordinator.devices[target_mac_norm]
                # Estrae i dati RSSI da tutti gli scanner che vedono il dispositivo in questo momento
                for scanner_mac, scanner_data in device.scanners.items():
                    fingerprint[scanner_mac] = scanner_data.rssi

        if fingerprint:
            radar_storage.save_room_point(room_name, fingerprint)
            _LOGGER.info("Mappato punto in %s con %s scanner", room_name, len(fingerprint))
        else:
            _LOGGER.warning("Impossibile mappare %s: nessun segnale trovato per %s", room_name, target_mac)

    # Registra il servizio per calibrare gli Shelly/Proxy
    hass.services.async_register(
        DOMAIN,
        "calibrate_anchor",
        handle_calibrate_anchor,
        schema=vol.Schema({
            vol.Required("scanner_id"): cv.string,
            vol.Optional("ref_rssi", default=-59): int,
        })
    )

    # Registra il servizio per la Mappatura delle Stanze (girando per casa)
    hass.services.async_register(
        DOMAIN,
        "map_room_point",
        handle_map_room_point,
        schema=vol.Schema({
            vol.Required("room_name"): cv.string,
            vol.Required("target_mac"): cv.string,
        })
    )
    # --- FINE NUOVO CODICE ---

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: BermudaConfigEntry) -> bool:
    """Migrate previous config entries."""
    _LOGGER.debug("Migrating config from version %s.%s", config_entry.version, config_entry.minor_version)
    _oldversion = f"{config_entry.version}.{config_entry.minor_version}"

    if config_entry.version == 3:  # it won't be.
        old_unique_id = config_entry.unique_id
        new_unique_id = mac_math_offset(old_unique_id, 3)

        @callback
        def update_unique_id(entity_entry):
            """Update unique_id of an entity."""
            return {"new_unique_id": entity_entry.unique_id.replace(old_unique_id, new_unique_id)}

        if old_unique_id != new_unique_id:
            await async_migrate_entries(hass, config_entry.entry_id, update_unique_id)
            hass.config_entries.async_update_entry(config_entry, unique_id=new_unique_id)

        return False

    if f"{config_entry.version}.{config_entry.minor_version}" != _oldversion:
        _LOGGER.info("Migrated config entry to version %s.%s", config_entry.version, config_entry.minor_version)

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: BermudaConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Implements user-deletion of devices from device registry."""
    coordinator: BermudaDataUpdateCoordinator = config_entry.runtime_data.coordinator
    if not coordinator:
        return True
        
    address = None
    for domain, ident in device_entry.identifiers:
        try:
            if domain == DOMAIN:
                address = ident.split("_")[0]
        except KeyError:
            pass
    if address is not None:
        try:
            coordinator.devices[mac_norm(address)].create_sensor = False
        except KeyError:
            _LOGGER.warning("Failed to locate device entry for %s", address)
        return True
    _LOGGER.warning(
        "Didn't find address for %s but allowing deletion to proceed.",
        device_entry.name,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BermudaConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unload_result := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        _LOGGER.debug("Unloaded platforms.")
    return unload_result


async def async_reload_entry(hass: HomeAssistant, entry: BermudaConfigEntry) -> None:
    """Reload config entry."""
    hass.config_entries.async_schedule_reload(entry.entry_id)
