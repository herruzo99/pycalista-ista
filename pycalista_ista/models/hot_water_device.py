"""Hot water device model for Ista Calista meters.

This module provides the HotWaterDevice class that represents a hot
water meter in the Ista Calista system. It inherits from WaterDevice
and specializes in tracking hot water consumption.
"""

from __future__ import annotations

from .water_device import WaterDevice


class HotWaterDevice(WaterDevice):
    """Class for hot water consumption meters.

    This class represents a hot water meter, inheriting core water meter
    functionality from WaterDevice and specializing it for hot water
    consumption tracking.

    Example:
        ```python
        meter = HotWaterDevice("12345", "Kitchen Hot Water")
        meter.add_reading_value(100.5, datetime.now())
        latest = meter.last_reading
        ```
    """

    def __init__(self, serial_number: str, location: str | None = None) -> None:
        """Initialize a hot water meter.

        Args:
            serial_number: Unique identifier for the meter
            location: Optional location description

        Raises:
            ValueError: If serial_number is empty
        """
        super().__init__(serial_number, location)

    def __repr__(self) -> str:
        """Get string representation of the hot water meter.

        Returns:
            String representation including type, location and serial number
        """
        location = f" at {self.location}" if self.location else ""
        return f"<Hot Water Device{location} (SN: {self.serial_number})>"
