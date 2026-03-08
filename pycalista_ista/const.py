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
INVOICES_URL: Final[str] = BASE_URL + "GestionFacturacionBuscar.do"
INVOICE_PDF_URL: Final[str] = BASE_URL + "GestionFacturacion.do"
CONSUMPTION_URL: Final[str] = BASE_URL + "GestionLecturasBusqueda.do"
# Fallback URL used when the export link cannot be found in the invoice listing HTML
INVOICE_XLS_FALLBACK_URL: Final[str] = (
    BASE_URL
    + "GestionFacturacion.do"
    + "?d-148657-e=2&metodo=listadoRecibos&metodo=buscarRecibos&6578706f7274=1"
)

# HTTP Headers
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/101.0.4951.67 Safari/537.36"
)

# Date formatting
DATE_FORMAT: Final[str] = "%d/%m/%Y"  # Full date used in API requests and Excel data
DATE_HEADER_FORMAT: Final[str] = "%d/%m/%y"  # Date format used in Excel column headers

# Incidence codes returned in billed-consumption readings
INCIDENCE_NAMES: Final[dict[str, str]] = {
    "4700": "Sin incidencia",
    "47A4": "Estimado",
    "47AA": "Arranque automático",
    "4741": "Contador nuevo",
}

# Logging
LOG_LEVEL_MAP: Final[dict[str, int]] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
