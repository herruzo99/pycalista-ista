"""Tests for Reading model."""

from datetime import datetime, timezone
import pytest

from pycalista_ista.models.reading import Reading


def test_reading_initialization():
    """Test reading initialization with valid data."""
    date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    reading = Reading(date=date, reading=100.5)

    assert reading.date == date
    assert reading.reading == 100.5


def test_reading_initialization_no_timezone():
    """Test reading initialization with naive datetime."""
    date = datetime(2025, 1, 1)
    reading = Reading(date=date, reading=100.5)

    assert reading.date.tzinfo == timezone.utc
    assert reading.date == datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_reading_comparison():
    """Test reading comparison operators."""
    date1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    date2 = datetime(2025, 1, 2, tzinfo=timezone.utc)

    reading1 = Reading(date=date1, reading=100)
    reading2 = Reading(date=date2, reading=200)
    reading3 = Reading(date=date1, reading=300)

    # Test equality
    assert reading1 == Reading(date=date1, reading=100)

    # Test less than (based on date)
    assert reading1 < reading2

    # Test greater than (based on date)
    assert reading2 > reading1

    # Test same date different values
    assert reading1 == reading3  # Equality only checks date


def test_reading_subtraction():
    """Test reading subtraction for consumption calculation."""
    date1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    date2 = datetime(2025, 1, 2, tzinfo=timezone.utc)

    reading1 = Reading(date=date1, reading=100)
    reading2 = Reading(date=date2, reading=150)

    # Test forward consumption
    consumption = reading2 - reading1
    assert consumption == 50

    # Test reverse consumption
    consumption = reading1 - reading2
    assert consumption == -50


def test_reading_string_representation():
    """Test reading string representation."""
    date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    reading = Reading(date=date, reading=100.5)

    assert str(reading) == "100.5"
    assert repr(reading) == f"<Reading: 100.5 @ {date}>"
