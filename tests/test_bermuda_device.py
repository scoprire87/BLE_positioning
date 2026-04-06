"""
Tests for BleRadarDevice class in ble_radar_device.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from homeassistant.components.bluetooth import BaseHaScanner, BaseHaRemoteScanner
from custom_components.ble_radar.ble_radar_device import BleRadarDevice
from custom_components.ble_radar.const import ICON_DEFAULT_AREA, ICON_DEFAULT_FLOOR


@pytest.fixture
def mock_coordinator():
    """Fixture for mocking BleRadarDataUpdateCoordinator."""
    coordinator = MagicMock()
    coordinator.options = {}
    coordinator.hass_version_min_2025_4 = True
    return coordinator


@pytest.fixture
def mock_scanner():
    """Fixture for mocking BaseHaScanner."""
    scanner = MagicMock(spec=BaseHaScanner)
    scanner.time_since_last_detection.return_value = 5.0
    scanner.source = "mock_source"
    return scanner


@pytest.fixture
def mock_remote_scanner():
    """Fixture for mocking BaseHaRemoteScanner."""
    scanner = MagicMock(spec=BaseHaRemoteScanner)
    scanner.time_since_last_detection.return_value = 5.0
    scanner.source = "mock_source"
    return scanner


@pytest.fixture
def ble_radar_device(mock_coordinator):
    """Fixture for creating a BleRadarDevice instance."""
    return BleRadarDevice(address="AA:BB:CC:DD:EE:FF", coordinator=mock_coordinator)


@pytest.fixture
def ble_radar_scanner(mock_coordinator):
    """Fixture for creating a BleRadarDevice Scanner instance."""
    return BleRadarDevice(address="11:22:33:44:55:66", coordinator=mock_coordinator)


def test_ble_radar_device_initialization(ble_radar_device):
    """Test BleRadarDevice initialization."""
    assert ble_radar_device.address == "aa:bb:cc:dd:ee:ff"
    assert ble_radar_device.name.startswith("ble_radar_")
    assert ble_radar_device.area_icon == ICON_DEFAULT_AREA
    assert ble_radar_device.floor_icon == ICON_DEFAULT_FLOOR
    assert ble_radar_device.zone == "not_home"


def test_async_as_scanner_init(ble_radar_scanner, mock_scanner):
    """Test async_as_scanner_init method."""
    ble_radar_scanner.async_as_scanner_init(mock_scanner)
    assert ble_radar_scanner._hascanner == mock_scanner
    assert ble_radar_scanner.is_scanner is True
    assert ble_radar_scanner.is_remote_scanner is False


def test_async_as_scanner_update(ble_radar_scanner, mock_scanner):
    """Test async_as_scanner_update method."""
    ble_radar_scanner.async_as_scanner_update(mock_scanner)
    assert ble_radar_scanner.last_seen > 0


def test_async_as_scanner_get_stamp(ble_radar_scanner, mock_scanner, mock_remote_scanner):
    """Test async_as_scanner_get_stamp method."""
    ble_radar_scanner.async_as_scanner_init(mock_scanner)
    ble_radar_scanner.stamps = {"AA:BB:CC:DD:EE:FF": 123.45}

    stamp = ble_radar_scanner.async_as_scanner_get_stamp("AA:bb:CC:DD:EE:FF")
    assert stamp is None

    ble_radar_scanner.async_as_scanner_init(mock_remote_scanner)

    stamp = ble_radar_scanner.async_as_scanner_get_stamp("AA:bb:CC:DD:EE:FF")
    assert stamp == 123.45

    stamp = ble_radar_scanner.async_as_scanner_get_stamp("AA:BB:CC:DD:E1:FF")
    assert stamp is None


def test_make_name(ble_radar_device):
    """Test make_name method."""
    ble_radar_device.name_by_user = "Custom Name"
    name = ble_radar_device.make_name()
    assert name == "Custom Name"
    assert ble_radar_device.name == "Custom Name"


def test_process_advertisement(ble_radar_device, ble_radar_scanner):
    """Test process_advertisement method."""
    advertisement_data = MagicMock()
    ble_radar_device.process_advertisement(ble_radar_scanner, advertisement_data)
    assert len(ble_radar_device.adverts) == 1


def test_to_dict(ble_radar_device):
    """Test to_dict method."""
    device_dict = ble_radar_device.to_dict()
    assert isinstance(device_dict, dict)
    assert device_dict["address"] == "aa:bb:cc:dd:ee:ff"


def test_repr(ble_radar_device):
    """Test __repr__ method."""
    repr_str = repr(ble_radar_device)
    assert repr_str == f"{ble_radar_device.name} [{ble_radar_device.address}]"
