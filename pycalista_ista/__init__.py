"""Async Python client for Ista Calista utility monitoring.

Provides a client for interacting with the Ista Calista virtual office,
allowing retrieval and analysis of utility consumption data asynchronously.
"""

from __future__ import annotations

from typing import Final

from .__version import __version__
from .const import INCIDENCE_NAMES
from .exception_classes import (
    IstaApiError,
    IstaConnectionError,
    IstaLoginError,
    IstaParserError,
)
from .models import (
    BilledReading,
    ColdWaterDevice,
    Device,
    HeatingDevice,
    HotWaterDevice,
    Invoice,
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
    # Billing models
    "Invoice",
    "BilledReading",
    # Constants
    "INCIDENCE_NAMES",
    # Exceptions
    "IstaApiError",
    "IstaConnectionError",
    "IstaLoginError",
    "IstaParserError",
]
