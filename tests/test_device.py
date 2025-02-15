"""Tests for Device models."""

from datetime import datetime
import pytest

from pycalista_ista.models.device import Device
from pycalista_ista.models.reading import Reading


def test_device_initialization():
    """Test device initialization with valid data."""
    device = Device("12345", "Kitchen")
    assert device.serial_number == "12345"
    assert device.location == "Kitchen"
    assert device.history == []

def test_device_initialization_no_location():
    """Test device initialization without location."""
    device = Device("12345")
    assert device.serial_number == "12345"
    assert device.location == ""
    assert device.history == []

def test_device_initialization_empty_serial():
    """Test device initialization with empty serial number."""
    with pytest.raises(ValueError, match="Serial number cannot be empty"):
        Device("")

def test_add_reading_value():
    """Test adding reading using raw values."""
    device = Device("12345")
    date = datetime(2025, 1, 1)
    device.add_reading_value(100.5, date)
    
    assert len(device.history) == 1
    assert device.history[0].reading == 100.5
    assert device.history[0].date == date

def test_add_reading_negative_value():
    """Test adding negative reading value."""
    device = Device("12345")
    date = datetime(2025, 1, 1)
    
    with pytest.raises(ValueError, match="Reading cannot be negative"):
        device.add_reading_value(-1, date)

def test_add_reading_chronological_order():
    """Test readings are stored in chronological order."""
    device = Device("12345")
    
    date1 = datetime(2025, 1, 1)
    date2 = datetime(2025, 1, 2)
    date3 = datetime(2025, 1, 3)
    
    # Add readings in non-chronological order
    device.add_reading_value(100, date2)
    device.add_reading_value(50, date1)
    device.add_reading_value(150, date3)
    
    # Verify they're stored in chronological order
    assert len(device.history) == 3
    assert device.history[0].date == date1
    assert device.history[1].date == date2
    assert device.history[2].date == date3

def test_last_consumption_insufficient_data():
    """Test last consumption with insufficient readings."""
    device = Device("12345")
    assert device.last_consumption is None
    
    device.add_reading_value(100, datetime(2025, 1, 1))
    assert device.last_consumption is None

def test_last_consumption_calculation():
    """Test last consumption calculation."""
    device = Device("12345")
    
    device.add_reading_value(100, datetime(2025, 1, 1))
    device.add_reading_value(150, datetime(2025, 1, 2))
    
    consumption = device.last_consumption
    assert consumption is not None
    assert consumption.reading == 50  # 150 - 100
    assert consumption.date == datetime(2025, 1, 2)

def test_last_reading():
    """Test last reading property."""
    device = Device("12345")
    
    assert device.last_reading is None
    
    date1 = datetime(2025, 1, 1)
    date2 = datetime(2025, 1, 2)
    
    device.add_reading_value(100, date1)
    device.add_reading_value(150, date2)
    
    last_reading = device.last_reading
    assert last_reading is not None
    assert last_reading.reading == 150
    assert last_reading.date == date2

def test_device_representation():
    """Test string representation of device."""
    device1 = Device("12345", "Kitchen")
    device2 = Device("67890")
    
    assert repr(device1) == "<Device at Kitchen (SN: 12345)>"
    assert repr(device2) == "<Device (SN: 67890)>"
