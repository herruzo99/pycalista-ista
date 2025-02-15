"""Tests for WaterDevice model."""

from datetime import datetime
import pytest

from pycalista_ista.models.water_device import WaterDevice


def test_water_device_initialization():
    """Test water device initialization with valid data."""
    device = WaterDevice("12345", "Kitchen Sink")
    assert device.serial_number == "12345"
    assert device.location == "Kitchen Sink"
    assert device.history == []
    assert isinstance(device, WaterDevice)


def test_water_device_initialization_no_location():
    """Test water device initialization without location."""
    device = WaterDevice("12345")
    assert device.serial_number == "12345"
    assert device.location == ""
    assert device.history == []


def test_water_device_initialization_empty_serial():
    """Test water device initialization with empty serial number."""
    with pytest.raises(ValueError, match="Serial number cannot be empty"):
        WaterDevice("")


def test_water_device_inheritance():
    """Test that water device inherits Device functionality."""
    device = WaterDevice("12345", "Kitchen Sink")
    date = datetime(2025, 1, 1)

    # Test inherited add_reading_value
    device.add_reading_value(100.5, date)
    assert len(device.history) == 1
    assert device.history[0].reading == 100.5
    assert device.history[0].date == date

    # Test inherited last_reading
    assert device.last_reading is not None
    assert device.last_reading.reading == 100.5
    assert device.last_reading.date == date


def test_water_device_representation():
    """Test string representation of water device."""
    device1 = WaterDevice("12345", "Kitchen Sink")
    device2 = WaterDevice("67890")

    assert repr(device1) == "<Water Device at Kitchen Sink (SN: 12345)>"
    assert repr(device2) == "<Water Device (SN: 67890)>"
