"""Models for the PyCalistaIsta package.

This module provides the data models used throughout the package to represent
different types of utility meters and their readings. The models include:

- Device: Base class for all meter types
- WaterDevice: Base class for water meters
- HotWaterDevice: Hot water meter implementation
- ColdWaterDevice: Cold water meter implementation
- HeatingDevice: Heating meter implementation
- Reading: Individual meter reading with timestamp
"""

from __future__ import annotations

from .cold_water_device import ColdWaterDevice
from .device import Device
from .heating_device import HeatingDevice
from .hot_water_device import HotWaterDevice
from .reading import Reading
from .water_device import WaterDevice

__all__ = [
    "Device",
    "WaterDevice",
    "HotWaterDevice",
    "ColdWaterDevice",
    "HeatingDevice",
    "Reading",
]
