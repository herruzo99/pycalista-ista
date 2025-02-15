"""Water device model for Ista Calista water meters.

This module provides the WaterDevice class that represents a generic
water meter in the Ista Calista system. It serves as a base class for
specific water meter types (hot and cold water).
"""

from __future__ import annotations

from .device import Device


class WaterDevice(Device):
    """Base class for water distribution meters.

    This class represents a generic water meter and serves as a base
    for more specific water meter types. It inherits core functionality
    from the Device class.

    Example:
        ```python
        meter = WaterDevice("12345", "Kitchen Sink")
        meter.add_reading_value(100.5, datetime.now())
        latest = meter.last_reading
        ```
    """

    def __init__(self, serial_number: str, location: str | None = None) -> None:
        """Initialize a water meter.

        Args:
            serial_number: Unique identifier for the meter
            location: Optional location description

        Raises:
            ValueError: If serial_number is empty
        """
        super().__init__(serial_number, location)

    def __repr__(self) -> str:
        """Get string representation of the water meter.

        Returns:
            String representation including type, location and serial number
        """
        location = f" at {self.location}" if self.location else ""
        return f"<Water Device{location} (SN: {self.serial_number})>"
