"""Test BLE Radar switch."""

from __future__ import annotations

# In futuro, se riattiverai i test per gli switch, 
# questi import punteranno al nuovo dominio ble_radar.

# from homeassistant.components.switch import SERVICE_TURN_OFF
# from homeassistant.components.switch import SERVICE_TURN_ON
# from homeassistant.const import ATTR_ENTITY_ID

# from custom_components.ble_radar.const import DEFAULT_NAME
# from custom_components.ble_radar.const import SWITCH

# Al momento non utilizzato - manteniamo la struttura aggiornata per BLE Radar
# async def test_switch_services(hass: HomeAssistant):
#     """Test switch services."""
#     # Crea un'entry finta per saltare il config flow
#     config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test")
#     assert await async_setup_entry(hass, config_entry)
#     await hass.async_block_till_done()

# Esempio di patch aggiornato per il nuovo coordinatore
# with patch(
#     "custom_components.ble_radar.BleRadarDataUpdateCoordinator.async_set_title"
# ) as title_func:
#     await hass.services.async_call(
#         SWITCH,
#         SERVICE_TURN_OFF,
#         service_data={ATTR_ENTITY_ID: f"{SWITCH}.{DEFAULT_NAME}_{SWITCH}"},
#         blocking=True,
#     )
#     assert title_func.called
