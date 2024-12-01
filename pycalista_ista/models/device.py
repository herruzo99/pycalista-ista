from bisect import insort
from datetime import datetime
import logging
from typing import Optional

from .reading import Reading

_LOGGER = logging.getLogger(__name__)


class Device:
    """Base class for devices."""

    def __init__(self, serial_number: str, device_id: int, name: str):
        """Initialize a device with a unique identifier, name, and optional location."""

        if not serial_number:
            raise ValueError("Serial number cannot be empty.")
        if not device_id:
            raise ValueError("Device ID cannot be empty.")
        if not name:
            raise ValueError("Device name cannot be empty.")

        self.serial_number: str = serial_number
        self.device_id: str = device_id
        self.name: str = name
        self.history: list[Reading] = []

    def add_reading_value(self, reading_value: float, date: datetime) -> None:
        """Add reading value to date."""

        r = Reading(date=date, reading=reading_value)
        self.add_reading(r)

    def add_reading(self, reading: Reading) -> None:
        """Add a new reading with a date."""

        if reading.reading < 0:
            raise ValueError(f"Reading cannot be negative: {reading}")

        if len(self.history) == 0:
            self.history.append(reading)
        else:
            insort(self.history, reading, key=lambda x: x.date)
        _LOGGER.debug(
            f"Reading {reading} added for device {self.serial_number} on {reading.date}."
        )  # noqa: G004

    @property
    def last_consumption(self) -> Optional[Reading]:
        """
        Calculate the consumption between the last two readings.
        :return: Consumption value or None if not enough data is available.
        """
        if len(self.history) < 2:
            _LOGGER.warning(
                f"Not enough data to calculate consumption for device {self.serial_number}."
            )
            return None

        last_reading = self.history[-1]
        previous_reading = self.history[-2]
        consumption = last_reading - previous_reading

        return Reading(date=last_reading.date, reading=consumption)

    @property
    def last_reading(self) -> Optional[Reading]:
        """
        Get the most recent reading.
        :return: The most recent reading or None if no readings exist.
        """
        return self.history[-1] if self.history else None

    def __repr__(self) -> str:
        """
        String representation of the device.
        """
        return f"<Device {self.device_id}: {self.name} (SN: {self.serial_number})>"
