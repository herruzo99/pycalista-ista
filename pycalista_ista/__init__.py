"""Python client for Ista Calista utility monitoring.

This package provides a client for interacting with the Ista Calista
virtual office, allowing retrieval and analysis of utility consumption
data from various types of meters.

Example:
    ```python
    from pycalista_ista import PyCalistaIsta

    client = PyCalistaIsta("user@example.com", "password")
    client.login()
    devices = client.get_devices()
    ```
"""

from __future__ import annotations

from typing import Final

from .__version import __version__
from .exception_classes import LoginError, ParserError, ServerError
from .models import (
    ColdWaterDevice,
    Device,
    HeatingDevice,
    HotWaterDevice,
    Reading,
    WaterDevice,
)
from .pycalista_ista import PyCalistaIsta

# Version information
VERSION: Final[str] = __version__

__all__ = [
    # Main client
    "PyCalistaIsta",
    "VERSION",
    # Device models
    "Device",
    "WaterDevice",
    "HotWaterDevice",
    "ColdWaterDevice",
    "HeatingDevice",
    "Reading",
    # Exceptions
    "LoginError",
    "ParserError",
    "ServerError",
]
