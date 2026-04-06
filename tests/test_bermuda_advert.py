"""
Tests for BleRadarAdvert class in ble_radar_advert.py.
"""

import pytest
from unittest.mock import MagicMock, patch
from custom_components.ble_radar.ble_radar_advert import BleRadarAdvert
from custom_components.ble_radar.ble_radar_device import BleRadarDevice
from bleak.backends.scanner import AdvertisementData


@pytest.fixture
def mock_parent_device():
    """Fixture for mocking the parent BleRadarDevice."""
    device = MagicMock(spec=BleRadarDevice)
    device.address = "aa:bb:cc:dd:ee:ff"
    device.ref_power = -59
    device.name_bt_local_name = None
    device.name = "mock parent name"
    return device


@pytest.fixture
def mock_scanner_device():
    """Fixture for mocking the scanner BleRadarDevice."""
    scanner = MagicMock(spec=BleRadarDevice)
    scanner.address = "11:22:33:44:55:66"
    scanner.name = "Mock Scanner"
    scanner.area_id = "server_room"
    scanner.area_name = "server room"
    scanner.is_remote_scanner = True
    scanner.last_seen = 0.0
    scanner.stamps = {"AA:BB:CC:DD:EE:FF": 123.45}
    scanner.async_as_scanner_get_stamp.return_value = 123.45
    return scanner


@pytest.fixture
def mock_advertisement_data():
    """Fixture for mocking AdvertisementData."""
    advert = MagicMock(spec=AdvertisementData)
    advert.rssi = -70
    advert.tx_power = -20
    advert.local_name = "Mock advert Local Name"
    advert.name = "Mock advert name"
    advert.manufacturer_data = {76: b"\x02\x15"}
    advert.service_data = {"0000abcd-0000-1000-8000-00805f9b34fb": b"\x01\x02"}
    advert.service_uuids = ["0000abcd-0000-1000-8000-00805f9b34fb"]
    return advert


@pytest.fixture
def ble_radar_advert(mock_parent_device, mock_advertisement_data, mock_scanner_device):
    """Fixture for creating a BleRadarAdvert instance."""
    options = {
        "CONF_RSSI_OFFSETS": {"11:22:33:44:55:66": 5},
        "CONF_REF_POWER": -59,
        "CONF_ATTENUATION": 2.0,
        "CONF_MAX_VELOCITY": 3.0,
        "CONF_SMOOTHING_SAMPLES": 5,
    }
    ba = BleRadarAdvert(
        parent_device=mock_parent_device,
        advertisementdata=mock_advertisement_data,
        options=options,
        scanner_device=mock_scanner_device,
    )
    ba.name = "foo name"
    return ba


def test_ble_radar_advert_initialization(ble_radar_advert):
    """Test BleRadarAdvert initialization."""
    assert ble_radar_advert.device_address == "aa:bb:cc:dd:ee:ff"
    assert ble_radar_advert.scanner_address == "11:22:33:44:55:66"
    assert ble_radar_advert.ref_power == -59
    assert ble_radar_advert.stamp == 123.45
    assert ble_radar_advert.rssi == -70


def test_apply_new_scanner(ble_radar_advert, mock_scanner_device):
    """Test apply_new_scanner method."""
    ble_radar_advert.apply_new_scanner(mock_scanner_device)
    assert ble_radar_advert.scanner_device == mock_scanner_device
    assert ble_radar_advert.scanner_sends_stamps is True


def test_update_advertisement(ble_radar_advert, mock_advertisement_data, mock_scanner_device):
    """Test update_advertisement method."""
    ble_radar_advert.update_advertisement(mock_advertisement_data, mock_scanner_device)
    assert ble_radar_advert.rssi == -70
    assert ble_radar_advert.tx_power == -20
    assert ble_radar_advert.local_name[0][0] == "Mock advert Local Name"
    assert ble_radar_advert.manufacturer_data[0][76] == b"\x02\x15"
    assert ble_radar_advert.service_data[0]["0000abcd-0000-1000-8000-00805f9b34fb"] == b"\x01\x02"


def test_set_ref_power(ble_radar_advert):
    """Test set_ref_power method."""
    new_distance = ble_radar_advert.set_ref_power(-65)
    assert ble_radar_advert.ref_power == -65
    assert new_distance is not None


def test_calculate_data_device_arrived(ble_radar_advert):
    """Test calculate_data method when device arrives."""
    ble_radar_advert.new_stamp = 123.45
    ble_radar_advert.rssi_distance_raw = 5.0
    ble_radar_advert.calculate_data()
    assert ble_radar_advert.rssi_distance == 5.0


def test_calculate_data_device_away(ble_radar_advert):
    """Test calculate_data method when device is away."""
    ble_radar_advert.stamp = 0.0
    ble_radar_advert.new_stamp = None
    ble_radar_advert.calculate_data()
    assert ble_radar_advert.rssi_distance is None


def test_to_dict(ble_radar_advert):
    """Test to_dict method."""
    advert_dict = ble_radar_advert.to_dict()
    assert isinstance(advert_dict, dict)
    assert advert_dict["device_address"] == "aa:bb:cc:dd:ee:ff"
    assert advert_dict["scanner_address"] == "11:22:33:44:55:66"


def test_repr(ble_radar_advert):
    """Test __repr__ method."""
    repr_str = repr(ble_radar_advert)
    assert repr_str == "aa:bb:cc:dd:ee:ff__Mock Scanner"
