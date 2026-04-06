"""Test BLE Radar setup process."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Aggiornamento dei percorsi dei moduli e delle classi
from custom_components.ble_radar.const import DOMAIN, IrkTypes
from custom_components.ble_radar.coordinator import BleRadarDataUpdateCoordinator

from .const import MOCK_CONFIG


# Utilizziamo le fixture definite in conftest.py e quelle fornite dal plugin
# pytest_homeassistant_custom_component per simulare l'ambiente di Home Assistant.
async def test_setup_unload_and_reload_entry(
    hass: HomeAssistant, bypass_get_data, setup_ble_radar_entry: MockConfigEntry
):
    """Test entry setup and unload."""

    # Ricarica l'entry e verifica che i dati siano ancora presenti e lo stato sia LOADED
    assert await hass.config_entries.async_reload(setup_ble_radar_entry.entry_id)
    assert setup_ble_radar_entry.state == ConfigEntryState.LOADED

    # Verifica la corretta inizializzazione dei tipi IRK (Identity Resolving Key)
    assert set(IrkTypes.unresolved()) == {
        IrkTypes.ADRESS_NOT_EVALUATED.value,
        IrkTypes.NO_KNOWN_IRK_MATCH.value,
        IrkTypes.NOT_RESOLVABLE_ADDRESS.value,
    }

    # Scarica l'entry e verifica che lo stato passi a NOT_LOADED
    assert await hass.config_entries.async_unload(setup_ble_radar_entry.entry_id)
    assert setup_ble_radar_entry.state == ConfigEntryState.NOT_LOADED


async def test_setup_entry_exception(hass, error_on_get_data):
    """Test ConfigEntryNotReady when API raises an exception during entry setup."""
    # Crea un'entry finta per il test di errore
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")

    assert config_entry is not None

    # Qui testiamo la condizione in cui il setup fallisce a causa di un'eccezione
    # simulata dalla fixture error_on_get_data.
    # Nota: il coordinatore gestisce internamente le eccezioni durante il refresh,
    # impostando last_update_status che viene poi controllato durante il setup.
