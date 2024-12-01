"""Subclass for hot water cost distribution devices."""

from .water_device import WaterDevice


class ColdWaterDevice(WaterDevice):
    """Subclass for hot water cost distribution devices."""

    def __init__(self, serial_number: str, device_id: int, name: str):
        super().__init__(serial_number, device_id, name)

    def __repr__(self) -> str:
        """Print string representation of the device."""

        return f"<Cold water Device {self.device_id}: {self.name} (SN: {self.serial_number})>"
