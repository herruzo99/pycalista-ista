"""Heating device model for Ista Calista meters.

This module provides the HeatingDevice class that represents a heating
meter in the Ista Calista system. It inherits from Device and
specializes in tracking heating consumption.
"""

from __future__ import annotations

from .device import Device


class HeatingDevice(Device):
    """Class for heating consumption meters.

    This class represents a heating meter, inheriting core meter
    functionality from Device and specializing it for heating
    consumption tracking.

    Example:
        ```python
        meter = HeatingDevice("12345", "Living Room Radiator")
        meter.add_reading_value(100.5, datetime.now())
        latest = meter.last_reading
        ```
    """

    def __init__(self, serial_number: str, location: str | None = None) -> None:
        """Initialize a heating meter.

        Args:
            serial_number: Unique identifier for the meter
            location: Optional location description

        Raises:
            ValueError: If serial_number is empty
        """
        super().__init__(serial_number, location)

    def __repr__(self) -> str:
        """Get string representation of the heating meter.

        Returns:
            String representation including type, location and serial number
        """
        location = f" at {self.location}" if self.location else ""
        return f"<Heating Device{location} (SN: {self.serial_number})>"
