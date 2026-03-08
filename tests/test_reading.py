"""Tests for Reading model."""

from datetime import datetime, timezone

from pycalista_ista.models.reading import Reading


def test_reading_initialization():
    """Test reading initialization with valid data."""
    date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    reading = Reading(date=date, reading=100.5)

    assert reading.date == date
    assert reading.reading == 100.5


def test_reading_initialization_no_timezone():
    """Test reading initialization with naive datetime."""
    naive_date = datetime(2025, 1, 1)
    reading = Reading(date=naive_date, reading=100.5)

    assert reading.date.tzinfo == timezone.utc
    assert reading.date == naive_date.replace(tzinfo=timezone.utc)


def test_reading_comparison():
    """Test reading comparison operators."""
    date1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    date2 = datetime(2025, 1, 2, tzinfo=timezone.utc)

    reading1 = Reading(date=date1, reading=100)
    reading2 = Reading(date=date2, reading=200)
    reading3 = Reading(date=date1, reading=300)

    # Test equality
    assert reading1 == Reading(date=date1, reading=100)
    assert reading1 != reading3  # Different readings should not be equal

    # Test less than (based on date)
    assert reading1 < reading2

    # Test greater than (based on date)
    assert reading2 > reading1


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
    assert repr(reading) == f"<Reading: 100.5 @ {date.isoformat()}>"


def test_reading_none_value_is_valid():
    """Reading accepts None as a value (missing data marker)."""
    r = Reading(date=datetime(2025, 1, 1, tzinfo=timezone.utc), reading=None)
    assert r.reading is None


def test_reading_subtraction_none_self():
    """__sub__ returns None when self.reading is None."""
    r_none = Reading(date=datetime(2025, 1, 2, tzinfo=timezone.utc), reading=None)
    r_val = Reading(date=datetime(2025, 1, 1, tzinfo=timezone.utc), reading=50.0)
    assert (r_none - r_val) is None


def test_reading_subtraction_none_other():
    """__sub__ returns None when other.reading is None."""
    r_val = Reading(date=datetime(2025, 1, 2, tzinfo=timezone.utc), reading=100.0)
    r_none = Reading(date=datetime(2025, 1, 1, tzinfo=timezone.utc), reading=None)
    assert (r_val - r_none) is None


def test_reading_subtraction_both_none():
    """__sub__ returns None when both readings are None."""
    d1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    d2 = datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert (Reading(d2, None) - Reading(d1, None)) is None


def test_reading_subtraction_type_error():
    """__sub__ raises TypeError for non-Reading operands."""
    import pytest

    r = Reading(date=datetime(2025, 1, 1, tzinfo=timezone.utc), reading=100.0)
    with pytest.raises(TypeError):
        r - 42  # type: ignore[operator]


def test_reading_comparison_type_error():
    """__lt__ raises TypeError for non-Reading operands."""
    import pytest

    r = Reading(date=datetime(2025, 1, 1, tzinfo=timezone.utc), reading=100.0)
    with pytest.raises(TypeError):
        r < "not a reading"  # type: ignore[operator]


def test_reading_equality_with_non_reading():
    """__eq__ returns NotImplemented for non-Reading objects."""
    r = Reading(date=datetime(2025, 1, 1, tzinfo=timezone.utc), reading=100.0)
    assert r.__eq__("not a reading") is NotImplemented


def test_reading_negative_value_raises():
    """Reading with a negative value raises ValueError."""
    import pytest

    with pytest.raises(ValueError, match="Reading value cannot be negative"):
        Reading(date=datetime(2025, 1, 1, tzinfo=timezone.utc), reading=-1.0)
