"""Constants for the PyCalistaIsta package.

This module contains all constant values used throughout the package,
including API endpoints, version information, and HTTP headers.

Constants:
    VERSION: Current version of the package
    BASE_URL: Base URL for the Ista Calista virtual office
    LOGIN_URL: URL for authentication endpoint
    DATA_URL: URL for data retrieval endpoint
    USER_AGENT: User agent string for HTTP requests
    LOG_LEVEL_MAP: Mapping from string log levels to Python logging constants.
"""

from __future__ import annotations

import logging
from typing import Final

from .__version import __version__

# Version information
VERSION: Final[str] = __version__

# API Endpoints
BASE_URL: Final[str] = "https://oficina.ista.es/GesCon/"
LOGIN_URL: Final[str] = BASE_URL + "GestionOficinaVirtual.do"
DATA_URL: Final[str] = BASE_URL + "GestionFincas.do"
LOGOUT_URL: Final[str] = BASE_URL + "GestionOficinaVirtual.do?metodo=logOutAbonado"

# HTTP Headers
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/101.0.4951.67 Safari/537.36"
)

# Logging
LOG_LEVEL_MAP: Final[dict[str, int]] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
