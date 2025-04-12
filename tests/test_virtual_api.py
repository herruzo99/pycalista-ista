"""Tests for Async VirtualApi."""

import asyncio
from datetime import date, datetime, timedelta
from io import BytesIO
from unittest.mock import patch  # Keep patch if needed for sync parts like parser

import pytest
from aiohttp import ClientConnectionError, ClientResponseError
from aioresponses import aioresponses

from pycalista_ista.exception_classes import (
    IstaApiError,
    IstaConnectionError,
    IstaLoginError,
    IstaParserError,
)
from pycalista_ista.models import HeatingDevice
from pycalista_ista.virtual_api import VirtualApi
from tests.conftest import (  # Import async fixtures and helpers
    TEST_EMAIL,
    TEST_PASSWORD,
    mock_get_readings,
    mock_login_failure,
    mock_login_success,
    mock_session_expiry_then_success,
)

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio


async def test_virtual_api_initialization(ista_api_client: VirtualApi):
    """Test VirtualApi initialization."""
    assert ista_api_client.username == TEST_EMAIL
    assert ista_api_client.password == TEST_PASSWORD
    assert ista_api_client.session is not None
    assert not ista_api_client._close_session # Session injected by fixture


async def test_login_success(ista_api_client: VirtualApi, mock_responses: aioresponses):
    """Test successful async login."""
    mock_login_success(mock_responses) # Configure mock responses
    result = await ista_api_client.login()
    assert result is True
    # Check if cookies were set (aiohttp handles this internally in the session)
    # assert 'JSESSIONID' in [c.key for c in ista_api_client.session.cookie_jar]


async def test_login_failure(ista_api_client: VirtualApi, mock_responses: aioresponses):
    """Test async login failure (invalid credentials)."""
    mock_login_failure(mock_responses)
    with pytest.raises(IstaLoginError, match="Login failed - invalid credentials"):
        await ista_api_client.login()


async def test_login_connection_error(ista_api_client: VirtualApi, mock_responses: aioresponses):
    """Test login failure due to connection error."""
    # Simulate connection error by mocking a failure
    mock_responses.post(
        'https://oficina.ista.es/GesCon/GestionOficinaVirtual.do',
        exception=ClientConnectionError("Connection refused")
    )
    with pytest.raises(IstaConnectionError, match="Request failed: Connection refused"):
         await ista_api_client.login()


async def test_relogin(ista_api_client: VirtualApi, mock_responses: aioresponses):
    """Test async relogin functionality."""
    # Simulate initial state (e.g., some cookies exist) - aiohttp session handles this
    # ista_api_client.session.cookie_jar.update_cookies(...) # If needed

    # Mock successful login sequence for the relogin call
    mock_login_success(mock_responses)

    result = await ista_api_client.relogin()
    assert result is True
    # Verify login sequence was called


@pytest.mark.parametrize(
    "excel_file_content", ["consulta_2024-11-30_2025-01-01.xls"], indirect=True
)
async def test_get_readings_chunk_success(
    ista_api_client: VirtualApi,
    mock_responses: aioresponses,
    excel_file_content: bytes,
):
    """Test getting readings chunk successfully."""
    start_dt = date(2024, 12, 1)
    end_dt = date(2024, 12, 30)
    mock_get_readings(mock_responses, excel_file_content, start_dt.strftime("%d/%m/%Y"), end_dt.strftime("%d/%m/%Y"))

    # Assume already logged in for this test
    result_buffer = await ista_api_client._get_readings_chunk(start_dt, end_dt)
    assert isinstance(result_buffer, BytesIO)
    assert result_buffer.read() == excel_file_content


async def test_get_readings_chunk_value_error(ista_api_client: VirtualApi):
    """Test getting readings chunk with invalid date range."""
    start_dt = date(2025, 1, 1)
    end_dt = date(2024, 12, 1) # End before start
    with pytest.raises(ValueError, match="Start date must be before end date"):
        await ista_api_client._get_readings_chunk(start_dt, end_dt)

    start_dt = date(2024, 1, 1)
    end_dt = date(2024, 12, 31) # Exceeds MAX_DAYS_PER_REQUEST (240)
    with pytest.raises(ValueError, match="Date range exceeds maximum"):
         await ista_api_client._get_readings_chunk(start_dt, end_dt)


@pytest.mark.parametrize(
    "excel_file_content", ["consulta_2024-11-30_2025-01-01.xls"], indirect=True
)
async def test_get_readings_chunk_session_expired(
    ista_api_client: VirtualApi,
    mock_responses: aioresponses,
    excel_file_content: bytes,
):
    """Test getting readings chunk with session expiry and successful relogin."""
    start_dt = date(2024, 12, 1)
    end_dt = date(2024, 12, 30)
    start_str = start_dt.strftime("%d/%m/%Y")
    end_str = end_dt.strftime("%d/%m/%Y")

    # Configure mocks for expiry -> relogin -> success
    mock_session_expiry_then_success(mock_responses, excel_file_content, start_str, end_str)

    result_buffer = await ista_api_client._get_readings_chunk(start_dt, end_dt)
    assert isinstance(result_buffer, BytesIO)
    assert result_buffer.read() == excel_file_content


@pytest.mark.parametrize(
    "excel_file_content", ["consulta_2024-11-30_2025-01-01.xls"], indirect=True
)
async def test_get_devices_history_success(
    ista_api_client: VirtualApi,
    mock_responses: aioresponses,
    excel_file_content: bytes,
):
    """Test getting full device history successfully (single chunk)."""
    start_dt = date(2024, 12, 1)
    end_dt = date(2024, 12, 30)
    start_str = start_dt.strftime("%d/%m/%Y")
    end_str = end_dt.strftime("%d/%m/%Y")

    mock_get_readings(mock_responses, excel_file_content, start_str, end_str)

    # Patch the parser call within the async function context if needed,
    # but better to test parser separately. Assume parser works for this test.
    # We mock the http call, the parser runs in executor.
    devices = await ista_api_client.get_devices_history(start_dt, end_dt)
    assert isinstance(devices, dict)
    assert len(devices) > 0 # Check based on your test excel file
    assert "141740872" in devices # Example serial from test file
    assert isinstance(devices["141740872"], HeatingDevice)


async def test_get_devices_history_parser_error(
    ista_api_client: VirtualApi,
    mock_responses: aioresponses,
):
    """Test getting device history when parser fails."""
    start_dt = date(2024, 12, 1)
    end_dt = date(2024, 12, 30)
    start_str = start_dt.strftime("%d/%m/%Y")
    end_str = end_dt.strftime("%d/%m/%Y")

    # Provide invalid excel content
    invalid_excel_content = b"this is not excel"
    mock_get_readings(mock_responses, invalid_excel_content, start_str, end_str)

    # The error comes from the parser running in the executor
    with pytest.raises(IstaParserError, match="Failed to parse one or more Excel files"):
         await ista_api_client.get_devices_history(start_dt, end_dt)


# --- Interpolation Tests (Copied and adapted from previous version) ---

async def test_interpolate_and_trim_device_reading_basic(ista_api_client: VirtualApi):
    """Test basic interpolation with simple readings."""
    device = HeatingDevice("12345", "Kitchen")
    device.add_reading_value(100, datetime(2025, 1, 1)) # Use loop time for consistency if needed
    device.add_reading_value(None, datetime(2025, 1, 2))
    device.add_reading_value(None, datetime(2025, 1, 3))
    device.add_reading_value(200, datetime(2025, 1, 4))

    fixed_device = ista_api_client._interpolate_and_trim_device_reading(device)

    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 4
    assert readings[0].reading == 100
    # Timestamps might differ slightly, focus on value
    assert pytest.approx(readings[1].reading) == 133.33
    assert pytest.approx(readings[2].reading) == 166.67
    assert readings[3].reading == 200
    assert fixed_device.location == "Kitchen"
    assert fixed_device.serial_number == '12345'
    assert isinstance(fixed_device, HeatingDevice)
