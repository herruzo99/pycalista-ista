"""Tests for Async VirtualApi."""

from datetime import date, datetime
from io import BytesIO

import pytest
from aiohttp import ClientConnectionError
from aioresponses import aioresponses

from pycalista_ista.const import DATA_URL, LOGIN_URL, LOGOUT_URL
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
        IstaLoginError, match=r"Login failed - invalid credentials \(302 Redirect\)"
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


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


async def test_virtual_api_close_own_session():
    """close() shuts down an internally created session."""
    client = VirtualApi(TEST_EMAIL, TEST_PASSWORD)  # no external session
    assert not client.session.closed
    await client.close()
    assert client.session.closed


async def test_virtual_api_close_external_session_not_closed(
    ista_api_client: VirtualApi,
):
    """close() does NOT close a session that was provided externally."""
    session = ista_api_client.session
    await ista_api_client.close()
    assert not session.closed  # caller owns the session


async def test_logout_exception_is_silenced(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """logout() swallows exceptions so they don't block callers."""
    from aiohttp import ClientConnectionError

    mock_responses.get(LOGOUT_URL, exception=ClientConnectionError("no route"))
    # Must not raise despite the connection failure
    await ista_api_client.logout()


async def test_virtual_api_close_idempotent():
    """Calling close() twice on an owned session does not raise."""
    client = VirtualApi(TEST_EMAIL, TEST_PASSWORD)
    await client.close()
    await client.close()  # second call must be safe


async def test_virtual_api_async_context_manager():
    """async with VirtualApi(...) closes the session on exit."""
    async with VirtualApi(TEST_EMAIL, TEST_PASSWORD) as client:
        assert not client.session.closed
    assert client.session.closed


# ---------------------------------------------------------------------------
# _send_request edge cases
# ---------------------------------------------------------------------------


async def test_send_request_closed_session_raises():
    """_send_request raises IstaConnectionError when the session is closed."""
    client = VirtualApi(TEST_EMAIL, TEST_PASSWORD)
    await client.close()

    with pytest.raises(IstaConnectionError, match="Session is closed"):
        await client._send_request("GET", LOGIN_URL)


async def test_send_request_retries_on_503_then_succeeds(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """A 503 on the first attempt triggers a retry that succeeds."""
    from unittest.mock import AsyncMock, patch

    url = DATA_URL
    mock_responses.get(url, status=503)
    mock_responses.get(url, status=200, body=b"ok")

    with patch("pycalista_ista.virtual_api.asyncio.sleep", new_callable=AsyncMock):
        response = await ista_api_client._send_request(
            "GET", url, retry_attempts=1, relogin=False
        )
    assert response.status == 200


async def test_send_request_exhausted_retries_raises(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """IstaConnectionError is raised when all retry attempts are exhausted."""
    from unittest.mock import AsyncMock, patch

    url = DATA_URL
    # Need MAX_RETRIES + 1 failures (initial attempt + 2 retries = 3 total)
    for _ in range(3):
        mock_responses.get(url, status=503)

    with patch("pycalista_ista.virtual_api.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(IstaConnectionError):
            await ista_api_client._send_request("GET", url, relogin=False)


async def test_send_request_binary_response_does_not_trigger_relogin(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """A binary (non-decodable) response does not trigger the session-expiry check."""
    # Return Excel magic bytes – valid binary content
    excel_magic = b"\xd0\xcf\x11\xe0" + b"\x00" * 100
    mock_responses.get(
        DATA_URL,
        status=200,
        headers={"Content-Type": "application/vnd.ms-excel"},
        body=excel_magic,
    )
    # Should succeed without triggering relogin
    response = await ista_api_client._send_request("GET", DATA_URL, relogin=False)
    assert response.status == 200


# ---------------------------------------------------------------------------
# login() – metadata preload failure
# ---------------------------------------------------------------------------


async def test_login_unexpected_exception_propagates(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """An unexpected exception inside login() propagates after logging."""
    from unittest.mock import AsyncMock, patch

    mock_responses.post(LOGIN_URL, status=200, body=b"")

    with patch.object(
        ista_api_client,
        "_preload_reading_metadata",
        new_callable=AsyncMock,
        side_effect=RuntimeError("surprise"),
    ):
        with pytest.raises(RuntimeError, match="surprise"):
            await ista_api_client.login()


async def test_login_preload_metadata_failure(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """If the metadata preload after login fails, IstaConnectionError propagates."""
    from unittest.mock import AsyncMock, patch

    # Login POST succeeds
    mock_responses.post(LOGIN_URL, status=200, body=b"")
    # Metadata preload GET fails
    mock_responses.get(
        f"{DATA_URL}?metodo=preCargaLecturasRadio",
        status=500,
    )

    with patch("pycalista_ista.virtual_api.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(IstaConnectionError):
            await ista_api_client.login()


# ---------------------------------------------------------------------------
# _get_readings – multi-chunk splitting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "excel_file_content", ["consulta_2024-11-30_2025-01-01.xls"], indirect=True
)
async def test_get_readings_multi_chunk(
    ista_api_client: VirtualApi,
    mock_responses: aioresponses,
    excel_file_content: bytes,
):
    """Date ranges >240 days are split into multiple chunk requests."""
    from datetime import timedelta

    # 300-day range → 2 chunks
    start_dt = date(2024, 1, 1)
    end_dt = start_dt + timedelta(days=299)

    # Chunk 1: days 0-239
    chunk1_end = start_dt + timedelta(days=239)
    # Chunk 2: days 240-299
    chunk2_start = chunk1_end + timedelta(days=1)

    mock_get_readings(
        mock_responses,
        excel_file_content,
        start_dt.strftime("%d/%m/%Y"),
        chunk1_end.strftime("%d/%m/%Y"),
    )
    mock_get_readings(
        mock_responses,
        excel_file_content,
        chunk2_start.strftime("%d/%m/%Y"),
        end_dt.strftime("%d/%m/%Y"),
    )

    buffers = await ista_api_client._get_readings(start_dt, end_dt)
    assert len(buffers) == 2


async def test_get_readings_start_after_end_raises(ista_api_client: VirtualApi):
    """_get_readings raises ValueError when start > end."""
    with pytest.raises(ValueError, match="Start date must be before or equal"):
        await ista_api_client._get_readings(date(2025, 2, 1), date(2025, 1, 1))


# ---------------------------------------------------------------------------
# merge_device_histories – edge cases
# ---------------------------------------------------------------------------


async def test_merge_skips_non_device_objects(ista_api_client: VirtualApi):
    """merge_device_histories skips list entries that are not Device instances."""
    from pycalista_ista.models import HeatingDevice

    valid = HeatingDevice("S1", "Room")
    valid.add_reading_value(100.0, datetime(2025, 1, 1))

    # Inject a non-Device value under the same key
    device_list = [{"S1": valid, "BAD": "not-a-device"}]  # type: ignore[list-item]
    merged = ista_api_client.merge_device_histories(device_list)

    assert "S1" in merged
    assert "BAD" not in merged


async def test_merge_device_histories_fallback_on_interpolation_error(
    ista_api_client: VirtualApi,
):
    """When interpolation fails, the raw device is kept rather than dropped."""
    from unittest.mock import patch

    from pycalista_ista.models import HeatingDevice

    device = HeatingDevice("S1", "Room")
    device.add_reading_value(100.0, datetime(2025, 1, 1))

    with patch.object(
        ista_api_client,
        "_interpolate_and_trim_device_reading",
        side_effect=RuntimeError("boom"),
    ):
        result = ista_api_client.merge_device_histories([{"S1": device}])

    # Device must still be present (fallback to raw)
    assert "S1" in result


# ---------------------------------------------------------------------------
# _interpolate_and_trim – additional edge cases
# ---------------------------------------------------------------------------


async def test_interpolate_single_valid_reading(ista_api_client: VirtualApi):
    """Fewer than 2 valid readings skips interpolation and returns as-is."""
    device = HeatingDevice("X", "L")
    device.add_reading_value(50.0, datetime(2025, 1, 1))
    device.add_reading_value(None, datetime(2025, 1, 2))

    fixed = ista_api_client._interpolate_and_trim_device_reading(device)
    # Only the one valid reading should be returned; None is trimmed from edges
    assert len(fixed.history) == 1
    assert fixed.history[0].reading == 50.0


async def test_interpolate_identical_timestamps_skips_gracefully(
    ista_api_client: VirtualApi,
):
    """Two valid readings at the same timestamp do not cause a ZeroDivisionError."""
    device = HeatingDevice("X", "L")
    ts = datetime(2025, 1, 1)
    device.add_reading_value(100.0, ts)
    device.add_reading_value(None, datetime(2025, 1, 2))
    # Same timestamp as first reading – edge case for time_span == 0
    device.add_reading_value(120.0, ts)

    # Should not raise; interpolation for the duplicate-timestamp gap is skipped
    fixed = ista_api_client._interpolate_and_trim_device_reading(device)
    assert fixed is not None


# ---------------------------------------------------------------------------
# _find_export_url
# ---------------------------------------------------------------------------


def test_find_export_url_returns_absolute_xls():
    """Relative export href is made absolute and forced to XLS format (e=2)."""
    html = (
        '<a href="GesCon/GestionLecturas.do?d-999-e=1&6578706f7274=1">Export</a>'
    )
    url = VirtualApi._find_export_url(html)
    assert url is not None
    assert url.startswith("https://oficina.ista.es/")
    assert "d-999-e=2" in url


def test_find_export_url_with_fragment_filters_correctly():
    """url_fragment restricts matches to links containing that substring."""
    html = (
        '<a href="GesCon/GestionFacturacion.do?d-148657-e=1&6578706f7274=1">Facturas</a>'
        '<a href="GesCon/GestionLecturas.do?d-99-e=1&6578706f7274=1">Lecturas</a>'
    )
    inv_url = VirtualApi._find_export_url(html, url_fragment="GestionFacturacion")
    lec_url = VirtualApi._find_export_url(html, url_fragment="GestionLecturas")

    assert inv_url is not None and "GestionFacturacion" in inv_url
    assert lec_url is not None and "GestionLecturas" in lec_url


def test_find_export_url_no_match_returns_none():
    """Returns None when no matching export link is found."""
    assert VirtualApi._find_export_url("<html><body>nothing</body></html>") is None


def test_find_export_url_fragment_no_match_returns_none():
    """Returns None when the fragment filter eliminates all candidates."""
    html = '<a href="GesCon/GestionLecturas.do?d-99-e=1&6578706f7274=1">Export</a>'
    assert VirtualApi._find_export_url(html, url_fragment="GestionFacturacion") is None


# ---------------------------------------------------------------------------
# get_invoice_xls
# ---------------------------------------------------------------------------


def _make_invoice_xls_bytes() -> bytes:
    """Return minimal invoice XLS bytes for mocking."""
    from io import BytesIO
    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("-")
    for col, h in enumerate(["Fecha lectura", "Tipo equipo", "Importe"]):
        ws.write(0, col, h)
    ws.write(1, 0, "31/01/2026")
    ws.write(1, 1, "Calefacción")
    ws.write(1, 2, "80,12")
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_get_invoice_xls_success_with_link_in_html(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """get_invoice_xls() finds the export link in HTML and downloads the XLS."""
    from pycalista_ista.const import INVOICES_URL

    export_path = "GesCon/GestionFacturacion.do?d-148657-e=1&metodo=listadoRecibos&6578706f7274=1"
    listing_html = f'<a href="{export_path}">Excel</a>'

    mock_responses.get(
        f"{INVOICES_URL}?metodo=buscarRecibos",
        status=200,
        body=listing_html.encode(),
    )
    mock_responses.get(
        f"https://oficina.ista.es/{export_path.replace('e=1', 'e=2')}",
        status=200,
        headers={"Content-Type": "application/vnd.ms-excel"},
        body=_make_invoice_xls_bytes(),
    )

    invoices = await ista_api_client.get_invoice_xls()
    assert len(invoices) == 1
    assert invoices[0].invoice_id is None
    assert invoices[0].amount is not None


async def test_get_invoice_xls_fallback_url(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """get_invoice_xls() falls back to the known URL when HTML has no export link."""
    from pycalista_ista.const import INVOICE_XLS_FALLBACK_URL, INVOICES_URL

    mock_responses.get(
        f"{INVOICES_URL}?metodo=buscarRecibos",
        status=200,
        body=b"<html>no export link here</html>",
    )
    mock_responses.get(
        INVOICE_XLS_FALLBACK_URL,
        status=200,
        headers={"Content-Type": "application/vnd.ms-excel"},
        body=_make_invoice_xls_bytes(),
    )

    invoices = await ista_api_client.get_invoice_xls()
    assert len(invoices) == 1
