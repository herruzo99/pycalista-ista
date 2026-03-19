"""Constants for the PyCalistaIsta package.

This module contains all constant values used throughout the package,
including API endpoints, version information, and HTTP headers.

Constants:
    VERSION: Current version of the package
    BASE_URL: Base URL for the Ista Calista virtual office
    DATA_URL: URL for the data retrieval endpoint
    KC_AUTH_URL: Keycloak OIDC authorization endpoint (login.ista.com)
    KC_CLIENT_ID: OAuth2 client identifier
    KC_REDIRECT_URI: OAuth2 redirect URI (acceso.ista.es callback)
    KC_STATE: OAuth2 state value matching the portal's AuthHandler URL
    USER_AGENT: User agent string for HTTP requests
    LOG_LEVEL_MAP: Mapping from string log levels to Python logging constants.
"""

from __future__ import annotations

import logging
from typing import Final

from .__version import __version__

# Version information
VERSION: Final[str] = __version__

# API Endpoints – virtual office (oficina.ista.es)
BASE_URL: Final[str] = "https://oficina.ista.es/GesCon/"
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

# Keycloak / OAuth2 – login.ista.com
KC_REALM_URL: Final[str] = "https://login.ista.com/realms/GESCON-PORTAL-ES-APP-Abonado"
KC_AUTH_URL: Final[str] = KC_REALM_URL + "/protocol/openid-connect/auth"
KC_CLIENT_ID: Final[str] = "abonado-service"
KC_REDIRECT_URI: Final[str] = "https://acceso.ista.es/auth/callback/abonado"
# The state value must match the AuthHandler URL that the portal expects
KC_STATE: Final[str] = BASE_URL + "AuthHandler.do"

# HTTP Headers
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
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
