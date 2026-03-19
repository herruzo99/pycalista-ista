"""Fixtures for PyCalistaIsta Tests (Async)."""

import re
from pathlib import Path
from typing import AsyncGenerator, Generator
from urllib.parse import quote

import aiohttp
import pytest
import pytest_asyncio  # Use pytest_asyncio for async fixtures
from aioresponses import aioresponses  # For mocking aiohttp requests

from pycalista_ista import PyCalistaIsta
from pycalista_ista.const import (
    DATA_URL,
    KC_AUTH_URL,
    KC_REDIRECT_URI,
)
from pycalista_ista.virtual_api import VirtualApi

# --- Constants ---
TEST_EMAIL = "demouser@example.com"
TEST_WRONG_EMAIL = "wronguser@example.com"
TEST_PASSWORD = "password"
TEST_WRONG_PASSWORD = "wrong_password"

# Base URL for mocking convenience
BASE_URL = "https://oficina.ista.es/GesCon/"

# Stable fake action URL returned by the mocked KC login page
# Mock authentication action URL (used in HTML form and for POST matching)
MOCK_KC_ACTION_URL = "https://login.ista.com/mock-auth-action"

# Regex patterns for aioresponses URL matching (handles any query param ordering/encoding)
_KC_AUTH_URL_PATTERN = re.compile(
    r"https://login\.ista\.com/.*auth.*",
    re.IGNORECASE,
)

# Minimal HTML page that Keycloak serves on the discovery GET
_KC_LOGIN_HTML = (
    "<html><body>"
    f'<form method="post" action="{MOCK_KC_ACTION_URL}">'
    '<input type="text" name="username"/>'
    '<input type="password" name="password"/>'
    '<input type="submit" name="login" value="Sign In"/>'
    "</form></body></html>"
)

# Keycloak error page returned when credentials are wrong (stays on KC host)
_KC_ERROR_HTML = (
    "<html><body>"
    f'<form method="post" action="{MOCK_KC_ACTION_URL}">'
    '<div class="kc-feedback-text">Invalid username or password.</div>'
    "</form></body></html>"
)


# --- Fixtures ---


@pytest_asyncio.fixture  # Use async fixture decorator
async def mock_aiohttp_session() -> AsyncGenerator[aiohttp.ClientSession, None]:
    """Create a mock aiohttp ClientSession."""
    # Using a real session for structure, mocking is done via aioresponses
    async with aiohttp.ClientSession() as session:
        yield session
    # Session is closed automatically by async context manager


@pytest_asyncio.fixture  # Use async fixture decorator
async def ista_api_client(mock_aiohttp_session: aiohttp.ClientSession) -> VirtualApi:
    """Create an instance of the async VirtualApi client."""
    client = VirtualApi(
        username=TEST_EMAIL, password=TEST_PASSWORD, session=mock_aiohttp_session
    )
    return client


@pytest_asyncio.fixture  # Use async fixture decorator
async def ista_main_client(
    mock_aiohttp_session: aiohttp.ClientSession,
) -> PyCalistaIsta:
    """Create an instance of the main PyCalistaIsta client."""
    client = PyCalistaIsta(
        email=TEST_EMAIL, password=TEST_PASSWORD, session=mock_aiohttp_session
    )
    return client


@pytest.fixture
def mock_responses() -> Generator[aioresponses, None, None]:
    """Initialize the aioresponses mock."""
    with aioresponses() as m:
        yield m


@pytest.fixture
def excel_file_content(request):
    """Reads content of an Excel file specified by request param."""
    path = (
        Path(__file__).parent / "data" / request.param
    )  # Assume test data is in tests/data/
    if not path.exists():
        raise FileNotFoundError(f"Test data file not found: {path}")
    with open(path, "rb") as fh:
        content = fh.read()
    return content


# --- Helper Functions for Mocking ---


def mock_login_success(mock_resp: aioresponses) -> None:
    """Configure mock responses for a successful Keycloak OAuth2 login.

    Chains the three-step flow:
      1. GET KC_AUTH_URL (any params) → 200 HTML with login form
      2. POST MOCK_KC_ACTION_URL → 302 to KC_REDIRECT_URI (auth code callback)
      3. GET KC_REDIRECT_URI callback → 303 to AuthHandler (cookie set)
      4. GET AuthHandler → 302 to GestionOficinaVirtual (JSESSIONID set)
      5. GET GestionOficinaVirtual → 200 (session ready)
      6. GET metadata preload → 200
    """
    # Step 1 – Keycloak discovery: returns an HTML login form
    mock_resp.get(
        _KC_AUTH_URL_PATTERN,
        status=200,
        headers={"Content-Type": "text/html;charset=utf-8"},
        body=_KC_LOGIN_HTML.encode(),
        repeat=True,
    )

    # Step 2 – Credential POST: Keycloak issues auth code redirect
    mock_resp.post(
        re.compile(re.escape(MOCK_KC_ACTION_URL)),
        status=302,
        headers={
            "Location": (
                f"{KC_REDIRECT_URI}"
                "?state=https%3A%2F%2Foficina.ista.es%2FGesCon%2FAuthHandler.do"
                "&code=MOCK_AUTH_CODE"
            ),
            "Set-Cookie": "KEYCLOAK_SESSION=MOCK_KC_SESSION; Path=/realms/GESCON-PORTAL-ES-APP-Abonado/; Secure",
        },
        body=b"",
        repeat=True,
    )

    # Step 3 – acceso.ista.es callback → portal AuthHandler
    mock_resp.get(
        re.compile(re.escape(KC_REDIRECT_URI)),
        status=303,
        headers={
            "Location": f"{BASE_URL}AuthHandler.do?ticket=MOCK_TICKET",
            "Set-Cookie": "KCSESSID=MOCK_KCSESSID; Path=/; Secure; HttpOnly",
        },
        body=b"",
        repeat=True,
    )

    # Step 4 – AuthHandler redirects to GestionOficinaVirtual
    mock_resp.get(
        re.compile(re.escape(f"{BASE_URL}AuthHandler.do")),
        status=302,
        headers={
            "Location": f"{BASE_URL}GestionOficinaVirtual.do?metodo=loginAbonado&ticket=MOCK_TICKET2",
            "Set-Cookie": "JSESSIONID=MOCK_SESSION_ID; Path=/GesCon; HttpOnly",
        },
        body=b"",
        repeat=True,
    )

    # Step 5 – Final portal page: session is ready
    mock_resp.get(
        re.compile(re.escape(f"{BASE_URL}GestionOficinaVirtual.do")),
        status=200,
        headers={"Content-Type": "text/html; charset=UTF-8"},
        body=b"<html><body>Welcome</body></html>",
        repeat=True,
    )

    # Step 6 – Metadata preload
    mock_resp.get(
        re.compile(re.escape(f"{DATA_URL}") + r".*preCargaLecturasRadio.*"),
        status=200,
        body=b"<html>Metadata preloaded</html>",
        repeat=True,
    )


def mock_login_failure(mock_resp: aioresponses) -> None:
    """Configure mock responses for a failed Keycloak login (bad credentials).

    Keycloak returns 200 with an error page that still hosts a login form,
    meaning the final response URL stays on login.ista.com.  The library
    detects this and raises IstaLoginError.
    """
    # Step 1 – KC discovery: normal login form
    mock_resp.get(
        _KC_AUTH_URL_PATTERN,
        status=200,
        headers={"Content-Type": "text/html;charset=utf-8"},
        body=_KC_LOGIN_HTML.encode(),
    )

    # Step 2 – Credential POST: Keycloak rejects credentials,
    #          returns 200 error page (stays on login.ista.com)
    mock_resp.post(
        re.compile(re.escape(MOCK_KC_ACTION_URL)),
        status=200,
        headers={"Content-Type": "text/html;charset=utf-8"},
        body=_KC_ERROR_HTML.encode(),
        repeat=True,
    )


def mock_get_readings(
    mock_resp: aioresponses, excel_content: bytes, start_date: str, end_date: str
) -> None:
    """Configure mock responses for fetching readings."""
    # Create the URL with query parameters
    url = (
        f"https://oficina.ista.es/GesCon/GestionFincas.do?d-4360165-e=2&"
        f"fechaHastaRadio={quote(end_date)}&"
        f"metodo=listadoLecturasRadio&"
        f"fechaDesdeRadio={quote(start_date)}&"
        f"6578706f7274=1"
    )

    mock_resp.get(
        url,
        status=200,
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"},
        body=excel_content,
    )


def mock_session_expiry_then_success(
    mock_resp: aioresponses, excel_content: bytes, start_date: str, end_date: str
) -> None:
    """Simulate session expiry on first attempt, then success after relogin."""
    # Create the URL with query parameters
    url = (
        f"https://oficina.ista.es/GesCon/GestionFincas.do?d-4360165-e=2&"
        f"fechaHastaRadio={quote(end_date)}&"
        f"metodo=listadoLecturasRadio&"
        f"fechaDesdeRadio={quote(start_date)}&"
        f"6578706f7274=1"
    )

    # 1. First attempt (session expired) - portal redirects to Keycloak
    mock_resp.get(
        url,
        status=302,
        headers={"Location": KC_AUTH_URL},
        repeat=1,
    )

    # 2. Mock the relogin attempt (full Keycloak chain)
    mock_login_success(mock_resp)

    # 3. Second attempt (after relogin) - returns Excel data
    mock_resp.get(
        url,
        status=200,
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"},
        body=excel_content,
        repeat=1,
    )
