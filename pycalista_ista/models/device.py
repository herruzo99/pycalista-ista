"""Base device model for Ista Calista meters.

This module provides the base Device class that represents any type of
utility meter in the Ista Calista system. It handles basic functionality
like storing readings and calculating consumption.
"""

from __future__ import annotations

import logging
from bisect import insort
from datetime import datetime
from typing import Final, Optional

from .reading import Reading

_LOGGER: Final = logging.getLogger(__name__)


class Device:
    """Base class for Ista Calista utility meters.

    This class provides core functionality for all meter types,
    including reading storage, consumption calculation, and history tracking.

    Attributes:
        serial_number: Unique identifier for the device
        location: Optional location description
        history: List of readings ordered by date

    Example:
        ```python
        device = Device("12345", "Kitchen")
        device.add_reading_value(100.5, datetime.now())
        latest = device.last_reading
        ```
    """

    def __init__(self, serial_number: str, location: str | None = None) -> None:
        """Initialize a device.

        Args:
            serial_number: Unique identifier for the device
            location: Optional location description

        Raises:
            ValueError: If serial_number is empty
        """
        if not serial_number:
            raise ValueError("Serial number cannot be empty")

        self.serial_number: str = serial_number
        self.location: str = location or ""
        self.history: list[Reading] = []

    def add_reading_value(self, reading_value: float, date: datetime) -> None:
        """Add a new reading using raw values.

        This is a convenience method that creates a Reading object
        and adds it to the device history.

        Args:
            reading_value: The meter reading value
            date: Timestamp of the reading

        Raises:
            ValueError: If reading_value is negative
        """
        reading = Reading(date=date, reading=reading_value)
        self.add_reading(reading)

    def add_reading(self, reading: Reading) -> None:
        """Add a new reading to the device history.

        The reading is inserted in chronological order.

        Args:
            reading: The Reading object to add

        Raises:
            ValueError: If the reading value is negative
        """
        if reading.reading is not None and reading.reading < 0:
            raise ValueError(f"Reading cannot be negative: {reading}")

        if not self.history:
            self.history.append(reading)
        else:
            insort(self.history, reading, key=lambda x: x.date)

        _LOGGER.debug(
            "Reading %s added for device %s on %s",
            reading,
            self.serial_number,
            reading.date,
        )

    @property
    def last_consumption(self) -> Reading | None:
        """Calculate consumption between the last two readings.

        Returns:
            Reading object with consumption value, or None if insufficient data
        """
        if len(self.history) < 2:
            _LOGGER.debug(
                "Not enough data to calculate consumption for device %s",
                self.serial_number,
            )
            return None

        last_reading = self.history[-1]
        previous_reading = self.history[-2]
        consumption = last_reading - previous_reading

        return Reading(date=last_reading.date, reading=consumption)

    @property
    def last_reading(self) -> Reading | None:
        """Get the most recent reading.

        Returns:
            Most recent Reading object, or None if no readings exist
        """
        return self.history[-1] if self.history else None

    def __repr__(self) -> str:
        """Get string representation of the device.

        Returns:
            String representation including location and serial number
        """
        location = f" at {self.location}" if self.location else ""
        return f"<Device{location} (SN: {self.serial_number})>"
