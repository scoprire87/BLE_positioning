"""Global fixtures for BLE Radar integration."""

from __future__ import annotations

from unittest.mock import patch
from homeassistant.config_entries import ConfigEntryState

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Aggiornamento dei percorsi dei moduli
from custom_components.ble_radar.const import DOMAIN
from custom_components.ble_radar.const import NAME

from .const import MOCK_CONFIG

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def mock_bluetooth(enable_bluetooth):
    """Auto mock bluetooth."""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations."""
    yield


@pytest.fixture(name="skip_notifications", autouse=True)
def skip_notifications_fixture():
    """Skip notification calls."""
    with (
        patch("homeassistant.components.persistent_notification.async_create"),
        patch("homeassistant.components.persistent_notification.async_dismiss"),
    ):
        yield


@pytest.fixture(name="bypass_get_data")
def bypass_get_data_fixture():
    """Skip calls to get data from API."""
    with patch("custom_components.ble_radar.BleRadarDataUpdateCoordinator.async_refresh"):
        yield


@pytest.fixture(name="skip_yaml_data_load", autouse=True)
def skip_yaml_data_load():
    """Skip loading yaml data files for bluetooth manufacturers"""
    with patch("custom_components.ble_radar.BleRadarDataUpdateCoordinator.async_load_manufacturer_ids"):
        yield


@pytest.fixture(name="error_on_get_data")
def error_get_data_fixture():
    """Simulate error when retrieving data from API."""
    with patch(
        "custom_components.ble_radar.BleRadarDataUpdateCoordinator.async_refresh",
        side_effect=Exception,
    ):
        yield


@pytest.fixture()
async def mock_ble_radar_entry(hass: HomeAssistant):
    """This creates a mock config entry"""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test", title=NAME)
    config_entry.add_to_hass(hass)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture()
async def setup_ble_radar_entry(hass: HomeAssistant):
    """This setups a entry so that it can be used."""
    config_entry = MockConfigEntry(domain=DOMAIN, data=MOCK_CONFIG, entry_id="test", title=NAME)
    config_entry.add_to_hass(hass)
    await async_setup_component(hass, DOMAIN, {})
    assert config_entry.state == ConfigEntryState.LOADED
    return config_entry
