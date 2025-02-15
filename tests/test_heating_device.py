"""Tests for HeatingDevice model."""

from datetime import datetime
import pytest

from pycalista_ista.models.heating_device import HeatingDevice


def test_heating_device_initialization():
    """Test heating device initialization with valid data."""
    device = HeatingDevice("12345", "Living Room")
    assert device.serial_number == "12345"
    assert device.location == "Living Room"
    assert device.history == []
    assert isinstance(device, HeatingDevice)

def test_heating_device_initialization_no_location():
    """Test heating device initialization without location."""
    device = HeatingDevice("12345")
    assert device.serial_number == "12345"
    assert device.location == ""
    assert device.history == []

def test_heating_device_initialization_empty_serial():
    """Test heating device initialization with empty serial number."""
    with pytest.raises(ValueError, match="Serial number cannot be empty"):
        HeatingDevice("")

def test_heating_device_inheritance():
    """Test that heating device inherits Device functionality."""
    device = HeatingDevice("12345", "Living Room")
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

def test_heating_device_representation():
    """Test string representation of heating device."""
    device1 = HeatingDevice("12345", "Living Room")
    device2 = HeatingDevice("67890")
    
    assert repr(device1) == "<Heating Device at Living Room (SN: 12345)>"
    assert repr(device2) == "<Heating Device (SN: 67890)>"
