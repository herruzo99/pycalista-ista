"""Fixtures for PyCalistaIsta Tests (Async)."""

import asyncio
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import aiohttp
import pytest
import pytest_asyncio # Use pytest_asyncio for async fixtures
from aioresponses import aioresponses # For mocking aiohttp requests

from pycalista_ista import PyCalistaIsta
from pycalista_ista.const import DATA_URL, LOGIN_URL
from pycalista_ista.virtual_api import VirtualApi

# --- Constants ---
TEST_EMAIL = "demouser@example.com"
TEST_WRONG_EMAIL = "wronguser@example.com"
TEST_PASSWORD = "password"
TEST_WRONG_PASSWORD = "wrong_password"

# Base URL for mocking convenience
BASE_URL = "https://oficina.ista.es/GesCon/"

# --- Fixtures ---

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    # This overrides the default pytest-asyncio loop fixture if needed,
    # usually not required unless customizing the loop policy.
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture # Use async fixture decorator
async def mock_aiohttp_session() -> aiohttp.ClientSession:
    """Create a mock aiohttp ClientSession."""
    # Using a real session for structure, mocking is done via aioresponses
    async with aiohttp.ClientSession() as session:
        yield session
    # Session is closed automatically by async context manager


@pytest_asyncio.fixture # Use async fixture decorator
async def ista_api_client(mock_aiohttp_session: aiohttp.ClientSession) -> VirtualApi:
    """Create an instance of the async VirtualApi client."""
    client = VirtualApi(
        username=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session
    )
    # No need to yield and close, session managed externally or by client.close()
    return client

@pytest_asyncio.fixture # Use async fixture decorator
async def ista_main_client(mock_aiohttp_session: aiohttp.ClientSession) -> PyCalistaIsta:
    """Create an instance of the main PyCalistaIsta client."""
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session
    )
    # No need to yield and close, session managed externally or by client.close()
    return client


@pytest.fixture
def mock_responses() -> aioresponses:
    """Initialize the aioresponses mock."""
    with aioresponses() as m:
        yield m


@pytest.fixture
def excel_file_content(request):
    """Reads content of an Excel file specified by request param."""
    path = Path(__file__).parent / "data" / request.param # Assume test data is in tests/data/
    if not path.exists():
        raise FileNotFoundError(f"Test data file not found: {path}")
    with open(path, "rb") as fh:
        content = fh.read()
    return content

# --- Helper Functions for Mocking ---

def mock_login_success(mock_resp: aioresponses):
    """Configure mock responses for a successful login."""
    # Mock the POST request to the login endpoint
    mock_resp.post(
        'https://oficina.ista.es/GesCon/GestionOficinaVirtual.do',
        status=200,
        headers={'Set-Cookie': 'JSESSIONID=MOCK_SESSION_ID; Path=/GesCon; HttpOnly, FGTServer=MOCK_FGT_SERVER; Path=/'},
        body=b''
    )
    # Mock the subsequent metadata preload request
    mock_resp.get(
        'https://oficina.ista.es/GesCon/GestionFincas.do?metodo=preCargaLecturasRadio',
        status=200,
        body=b'<html>Metadata preloaded</html>'
    )

def mock_login_failure(mock_resp: aioresponses):
    """Configure mock responses for a failed login (invalid credentials)."""
    mock_resp.post(
        'https://oficina.ista.es/GesCon/GestionOficinaVirtual.do',
        status=200,
        headers={'Content-Length': '100'},
        body='<html>Usuario o contraseña incorrectos</html>'
    )

def mock_get_readings(mock_resp: aioresponses, excel_content: bytes, start_date: str, end_date: str):
    """Configure mock responses for fetching readings."""
    # Create the URL with query parameters
    url = (
        f'https://oficina.ista.es/GesCon/GestionFincas.do?d-4360165-e=2&'
        f'fechaHastaRadio={quote(end_date)}&'
        f'metodo=listadoLecturasRadio&'
        f'fechaDesdeRadio={quote(start_date)}&'
        f'6578706f7274=1'
    )
    
    mock_resp.get(
        url,
        status=200,
        headers={'Content-Type': 'application/vnd.ms-excel;charset=iso-8859-1'},
        body=excel_content
    )

def mock_session_expiry_then_success(mock_resp: aioresponses, excel_content: bytes, start_date: str, end_date: str):
    """Simulate session expiry on first attempt, then success after relogin."""
    # Create the URL with query parameters
    url = (
        f'https://oficina.ista.es/GesCon/GestionFincas.do?d-4360165-e=2&'
        f'fechaHastaRadio={quote(end_date)}&'
        f'metodo=listadoLecturasRadio&'
        f'fechaDesdeRadio={quote(start_date)}&'
        f'6578706f7274=1'
    )

    # 1. First attempt (session expired) - returns HTML login page
    mock_resp.get(
        url,
        status=200,
        headers={'Content-Type': 'text/html'},
        body=b'<html>Redirect to GestionOficinaVirtual.do</html>',
        repeat=1
    )

    # 2. Mock the relogin attempt
    mock_login_success(mock_resp)

    # 3. Second attempt (after relogin) - returns Excel data
    mock_resp.get(
        url,
        status=200,
        headers={'Content-Type': 'application/vnd.ms-excel;charset=iso-8859-1'},
        body=excel_content,
        repeat=1
    )
