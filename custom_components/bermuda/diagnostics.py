"""Diagnostics support for BLE Radar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN

if TYPE_CHECKING:
    from . import BermudaConfigEntry
    from .coordinator import BermudaDataUpdateCoordinator


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: BermudaConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: BermudaDataUpdateCoordinator = entry.runtime_data.coordinator

    # We can call this with our own config_entry because the diags step doesn't
    # actually use it.

    bt_diags = await coordinator._manager.async_diagnostics()  # noqa

    # Param structure for service call
    call = ServiceCall(hass, DOMAIN, "dump_devices", {"redact": True})
    
    # --- NUOVO: Raccogliamo le statistiche della mappa radar ---
    # Includiamo solo i conteggi per non esporre i MAC Address grezzi nel file di diagnostica
    radar_rooms = coordinator.storage.data.get("rooms", {})
    map_stats = {
        "total_rooms_mapped": len(radar_rooms),
        "fingerprints_per_room": {
            room: len(fingerprints) for room, fingerprints in radar_rooms.items()
        }
    }

    data: dict[str, Any] = {
        "active_devices": f"{coordinator.count_active_devices()}/{len(coordinator.devices)}",
        "active_scanners": f"{coordinator.count_active_scanners()}/{len(coordinator.scanner_list)}",
        "irk_manager": coordinator.redact_data(coordinator.irk_manager.async_diagnostics_no_redactions()),
        "radar_map_stats": map_stats,  # <-- Aggiunto al report
        "devices": await coordinator.service_dump_devices(call),
        "bt_manager": coordinator.redact_data(bt_diags),
    }
    return data
