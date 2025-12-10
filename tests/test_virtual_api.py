"""Tests for Async VirtualApi."""

from datetime import date, datetime
from io import BytesIO

import pytest
from aiohttp import ClientConnectionError
from aioresponses import aioresponses

from pycalista_ista.const import LOGOUT_URL
from pycalista_ista.exception_classes import (
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
    assert not ista_api_client._close_session  # Session injected by fixture


async def test_login_success(ista_api_client: VirtualApi, mock_responses: aioresponses):
    """Test successful async login."""
    mock_login_success(mock_responses)  # Configure mock responses
    result = await ista_api_client.login()
    assert result is True
    # Check if cookies were set (aiohttp handles this internally in the session)
    # assert 'JSESSIONID' in [c.key for c in ista_api_client.session.cookie_jar]


async def test_login_failure(ista_api_client: VirtualApi, mock_responses: aioresponses):
    """Test async login failure (invalid credentials - 302 Redirect)."""
    # Mock 302 redirect which now indicates failure
    mock_responses.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        status=302,
        headers={"Location": "some_redirect_url"},
    )
    with pytest.raises(
        IstaLoginError, match="Login failed - invalid credentials \(302 Redirect\)"
    ):
        await ista_api_client.login()


async def test_login_connection_error(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """Test login failure due to connection error."""
    # Simulate connection error by mocking a failure
    mock_responses.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        exception=ClientConnectionError("Connection refused"),
    )
    # The error message now reflects that retries were attempted.
    with pytest.raises(
        IstaConnectionError, match="Request failed after retries: Connection refused"
    ):
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


async def test_logout(ista_api_client: VirtualApi, mock_responses: aioresponses):
    """Test logout functionality."""
    mock_responses.get(LOGOUT_URL, status=200)
    await ista_api_client.logout()
    # No assertion needed, just ensure no exception raised and request made
    # We can verify the request was made if we want, but aioresponses mocks it so it must match URL


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
    mock_get_readings(
        mock_responses,
        excel_file_content,
        start_dt.strftime("%d/%m/%Y"),
        end_dt.strftime("%d/%m/%Y"),
    )

    # Assume already logged in for this test
    result_buffer = await ista_api_client._get_readings_chunk(start_dt, end_dt)
    assert isinstance(result_buffer, BytesIO)
    assert result_buffer.read() == excel_file_content


async def test_get_readings_chunk_value_error(ista_api_client: VirtualApi):
    """Test getting readings chunk with invalid date range."""
    start_dt = date(2025, 1, 1)
    end_dt = date(2024, 12, 1)  # End before start
    with pytest.raises(ValueError, match="Start date must be before end date"):
        await ista_api_client._get_readings_chunk(start_dt, end_dt)

    start_dt = date(2024, 1, 1)
    end_dt = date(2024, 12, 31)  # Exceeds MAX_DAYS_PER_REQUEST (240)
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
    mock_session_expiry_then_success(
        mock_responses, excel_file_content, start_str, end_str
    )

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

    # Mock logout call which is now in finally block
    mock_responses.get(LOGOUT_URL, status=200)

    # Patch the parser call within the async function context if needed,
    # but better to test parser separately. Assume parser works for this test.
    # We mock the http call, the parser runs in executor.
    devices = await ista_api_client.get_devices_history(start_dt, end_dt)
    assert isinstance(devices, dict)
    assert len(devices) > 0  # Check based on your test excel file
    assert "141740872" in devices  # Example serial from test file
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

    # Mock logout call which is now in finally block
    mock_responses.get(LOGOUT_URL, status=200)

    # The error comes from the parser running in the executor
    with pytest.raises(
        IstaParserError, match="Failed to parse one or more Excel files"
    ):
        await ista_api_client.get_devices_history(start_dt, end_dt)


# --- Interpolation Tests (Copied and adapted from previous version) ---


async def test_interpolate_and_trim_device_reading_basic(ista_api_client: VirtualApi):
    """Test basic interpolation with simple readings."""
    device = HeatingDevice("12345", "Kitchen")
    device.add_reading_value(
        100, datetime(2025, 1, 1)
    )  # Use loop time for consistency if needed
    device.add_reading_value(None, datetime(2025, 1, 2))
    device.add_reading_value(None, datetime(2025, 1, 3))
    device.add_reading_value(200, datetime(2025, 1, 4))

    fixed_device = ista_api_client._interpolate_and_trim_device_reading(device)

    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 4
    assert readings[0].reading == 100
    # Timestamps might differ slightly, focus on value
    assert readings[1].reading == 133.3333
    assert readings[2].reading == 166.6667
    assert readings[3].reading == 200
    assert fixed_device.location == "Kitchen"
    assert fixed_device.serial_number == "12345"
    assert isinstance(fixed_device, HeatingDevice)


async def test_interpolate_preserves_precision_on_flat_reading(
    ista_api_client: VirtualApi,
):
    """
    Test interpolation when start and end values are identical with high precision.
    This directly tests the user's reported issue where 106.554 was interpolated
    incorrectly as 106.55.
    """
    device = HeatingDevice("DEVICE_FLAT", "Living Room")
    device.add_reading_value(106.554, datetime(2025, 2, 1))
    device.add_reading_value(None, datetime(2025, 2, 2))
    device.add_reading_value(None, datetime(2025, 2, 3))
    device.add_reading_value(None, datetime(2025, 2, 4))
    device.add_reading_value(106.554, datetime(2025, 2, 5))

    fixed_device = ista_api_client._interpolate_and_trim_device_reading(device)
    readings = sorted(fixed_device.history, key=lambda r: r.date)

    assert len(readings) == 5
    assert readings[0].reading == 106.554
    assert readings[1].reading == 106.554
    assert readings[2].reading == 106.554
    assert readings[3].reading == 106.554
    assert readings[4].reading == 106.554


async def test_interpolate_with_meter_reset_sets_gap_to_zero(
    ista_api_client: VirtualApi,
):
    """
    Test the special exception case where a meter reading goes down over a gap.
    This signifies a reset, and all interpolated values should be 0.
    """
    device = HeatingDevice("DEVICE_RESET", "Basement")
    device.add_reading_value(110.0, datetime(2025, 3, 10))
    device.add_reading_value(None, datetime(2025, 3, 11))
    device.add_reading_value(None, datetime(2025, 3, 12))
    device.add_reading_value(None, datetime(2025, 3, 13))
    device.add_reading_value(5.0, datetime(2025, 3, 14))  # Reading decreased

    fixed_device = ista_api_client._interpolate_and_trim_device_reading(device)
    readings = sorted(fixed_device.history, key=lambda r: r.date)

    assert len(readings) == 5
    assert readings[0].reading == 110.0
    assert readings[1].reading == 0
    assert readings[2].reading == 0
    assert readings[3].reading == 0
    assert readings[4].reading == 5.0


async def test_interpolate_clamps_to_boundaries(ista_api_client: VirtualApi):
    """
    Test that interpolated values are always greater than or equal to the previous
    real data point and less than or equal to the next real data point.
    """
    device = HeatingDevice("DEVICE_BOUNDARY", "Office")
    start_val = 250.123
    end_val = 250.128  # A very small increase over a few days

    device.add_reading_value(start_val, datetime(2025, 4, 1))
    device.add_reading_value(None, datetime(2025, 4, 2))
    device.add_reading_value(None, datetime(2025, 4, 3))
    device.add_reading_value(end_val, datetime(2025, 4, 4))

    fixed_device = ista_api_client._interpolate_and_trim_device_reading(device)
    readings = sorted(fixed_device.history, key=lambda r: r.date)

    assert len(readings) == 4

    # Check the known start and end points
    assert readings[0].reading == start_val
    assert readings[3].reading == end_val

    # Check that interpolated values are within the correct bounds
    # (start_val <= interpolated_val <= end_val)
    interpolated_val_1 = readings[1].reading
    interpolated_val_2 = readings[2].reading

    assert start_val <= interpolated_val_1 <= end_val
    assert start_val <= interpolated_val_2 <= end_val

    # Also check that the values are monotonically increasing
    assert (
        readings[0].reading
        <= readings[1].reading
        <= readings[2].reading
        <= readings[3].reading
    )

    # Check the expected calculated values
    assert (
        pytest.approx(interpolated_val_1) == 250.1247
    )  # (250.123 + (250.128-250.123)/3 * 1)
    assert (
        pytest.approx(interpolated_val_2) == 250.1263
    )  # (250.123 + (250.128-250.123)/3 * 2)
