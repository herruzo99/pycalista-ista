"""Tests for Device models."""

from datetime import datetime, timezone

import pytest

from pycalista_ista.models.device import Device


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
    assert device.history[0].date == date.replace(tzinfo=timezone.utc)


def test_add_reading_negative_value():
    """Test adding negative reading value."""
    device = Device("12345")
    date = datetime(2025, 1, 1)

    with pytest.raises(ValueError, match="Reading value cannot be negative"):
        device.add_reading_value(-1, date)


def test_add_reading_chronological_order():
    """Test readings are stored in chronological order."""
    device = Device("12345")

    date1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    date2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
    date3 = datetime(2025, 1, 3, tzinfo=timezone.utc)

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

    device.add_reading_value(100, datetime(2025, 1, 1, tzinfo=timezone.utc))
    device.add_reading_value(150, datetime(2025, 1, 2, tzinfo=timezone.utc))

    consumption = device.last_consumption
    assert consumption is not None
    assert consumption.reading == 50  # 150 - 100
    assert consumption.date == datetime(2025, 1, 2, tzinfo=timezone.utc)


def test_last_reading():
    """Test last reading property."""
    device = Device("12345")

    assert device.last_reading is None

    date1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    date2 = datetime(2025, 1, 2, tzinfo=timezone.utc)

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


def test_device_equality_same_serial():
    """Devices with the same serial number are equal regardless of location."""
    assert Device("ABC", "Room A") == Device("ABC", "Room B")
    assert Device("ABC") == Device("ABC")


def test_device_equality_different_serial():
    """Devices with different serial numbers are not equal."""
    assert Device("ABC") != Device("XYZ")


def test_device_eq_non_device_returns_not_implemented():
    """Comparing a Device with a non-Device returns NotImplemented."""
    result = Device("ABC").__eq__("ABC")
    assert result is NotImplemented


def test_device_hash_equal_devices_same_hash():
    """Equal devices produce the same hash."""
    assert hash(Device("ABC", "L1")) == hash(Device("ABC", "L2"))


def test_device_usable_as_dict_key():
    """Devices can be used as dictionary keys (requires __hash__)."""
    d1 = Device("S1", "Kitchen")
    d2 = Device("S2", "Bathroom")
    mapping = {d1: "heating", d2: "water"}
    assert mapping[Device("S1")] == "heating"


def test_device_usable_in_set():
    """Devices with the same serial are deduplicated in a set."""
    s = {Device("X", "A"), Device("X", "B"), Device("Y")}
    assert len(s) == 2


def test_last_consumption_with_none_reading():
    """last_consumption returns None when the last reading value is None."""
    device = Device("12345")
    device.add_reading_value(100.0, datetime(2025, 1, 1, tzinfo=timezone.utc))
    device.add_reading_value(None, datetime(2025, 1, 2, tzinfo=timezone.utc))
    assert device.last_consumption is None


def test_add_reading_none_value_accepted():
    """add_reading_value accepts None (missing reading) without raising."""
    device = Device("12345")
    device.add_reading_value(None, datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert len(device.history) == 1
    assert device.history[0].reading is None
