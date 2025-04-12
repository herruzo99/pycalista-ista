"""Async Python client for Ista Calista utility monitoring.

Provides a client for interacting with the Ista Calista virtual office,
allowing retrieval and analysis of utility consumption data asynchronously.
"""

from __future__ import annotations

from typing import Final

from .__version import __version__
from .exception_classes import (  # Updated exception names
    IstaApiError,
    IstaConnectionError,
    IstaLoginError,
    IstaParserError,
)
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
    # Exceptions (Updated Names)
    "IstaApiError",
    "IstaConnectionError",
    "IstaLoginError",
    "IstaParserError",
]

