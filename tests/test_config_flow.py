"""Test BLE Radar config flow."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant import data_entry_flow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Aggiornamento dei percorsi dei moduli
from custom_components.ble_radar.const import DOMAIN
from custom_components.ble_radar.const import NAME

from .const import MOCK_CONFIG
from .const import MOCK_OPTIONS_GLOBALS


# Simula un flusso di configurazione riuscito dal backend.
# Usiamo la fixture `bypass_get_data` affinché la convalida riesca durante il test.
async def test_successful_config_flow(hass, bypass_get_data):
    """Test a successful config flow."""
    # Inizializza il flusso di configurazione
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    # Verifica che il primo passaggio mostri il modulo utente
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    # Simula l'inserimento dei dati utente
    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=MOCK_CONFIG)

    # Verifica che il flusso sia completo e che venga creata una nuova voce
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {"source": "user"}
    assert result["options"] == {}
    assert result["result"]


# Simula un fallimento durante il flusso di configurazione.
# Usiamo `error_on_get_data` per sollevare un'eccezione durante la convalida.
async def test_failed_config_flow(hass, error_on_get_data):
    """Test a failed config flow due to credential validation failure."""

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], user_input=MOCK_CONFIG)

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result.get("errors") is None


# Poiché l'integrazione ha un flusso di opzioni, testiamo anche quello.
async def test_options_flow(hass: HomeAssistant, setup_ble_radar_entry: MockConfigEntry):
    """Test an options flow."""
    # Avvia il flusso delle opzioni
    result = await hass.config_entries.options.async_init(setup_ble_radar_entry.entry_id)

    # Verifica che il primo passaggio sia un menu (come definito nel tuo config_flow)
    assert result.get("type") == FlowResultType.MENU
    assert result.get("step_id") == "init"

    # Seleziona l'opzione del menu 'globalopts'
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "globalopts"}
    )

    assert result.get("type") == FlowResultType.FORM
    assert result.get("step_id") == "globalopts"

    # Inserisce dati finti nel modulo
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=MOCK_OPTIONS_GLOBALS,
    )

    # Verifica che il flusso finisca correttamente
    assert result.get("type") == FlowResultType.CREATE_ENTRY
    assert result.get("title") == NAME

    # Verifica che le opzioni siano state aggiornate nell'entry
    assert setup_ble_radar_entry.options == MOCK_OPTIONS_GLOBALS
