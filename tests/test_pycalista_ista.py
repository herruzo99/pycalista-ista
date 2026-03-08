"""Tests for the PyCalistaIsta main client."""

import logging
from datetime import date

import aiohttp
import pytest
from aioresponses import aioresponses

from pycalista_ista import PyCalistaIsta
from pycalista_ista.__version import __version__
from pycalista_ista.exception_classes import IstaConnectionError, IstaLoginError
from tests.conftest import (
    TEST_EMAIL,
    TEST_PASSWORD,
    mock_get_readings,
    mock_login_success,
)


# ---------------------------------------------------------------------------
# Synchronous validation – these don't touch the network / event loop
# ---------------------------------------------------------------------------


def test_pycalista_init_empty_email():
    """Empty email raises ValueError before any session is created."""
    with pytest.raises(ValueError, match="Email and password are required"):
        PyCalistaIsta("", TEST_PASSWORD)


def test_pycalista_init_empty_password():
    """Empty password raises ValueError before any session is created."""
    with pytest.raises(ValueError, match="Email and password are required"):
        PyCalistaIsta(TEST_EMAIL, "")


# ---------------------------------------------------------------------------
# Async tests – use the fixture that owns the session lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pycalista_init_valid(mock_aiohttp_session: aiohttp.ClientSession):
    """PyCalistaIsta stores the account email and creates a VirtualApi."""
    client = PyCalistaIsta(TEST_EMAIL, TEST_PASSWORD, session=mock_aiohttp_session)
    assert client.account == TEST_EMAIL
    assert client._virtual_api is not None


@pytest.mark.asyncio
async def test_pycalista_init_strips_whitespace(
    mock_aiohttp_session: aiohttp.ClientSession,
):
    """Leading/trailing whitespace is stripped from the email address."""
    client = PyCalistaIsta(
        "  user@example.com  ", TEST_PASSWORD, session=mock_aiohttp_session
    )
    assert client.account == "user@example.com"


@pytest.mark.asyncio
async def test_get_version(mock_aiohttp_session: aiohttp.ClientSession):
    """get_version() returns the package version string."""
    client = PyCalistaIsta(TEST_EMAIL, TEST_PASSWORD, session=mock_aiohttp_session)
    assert client.get_version() == __version__


@pytest.mark.asyncio
async def test_set_log_level_valid(mock_aiohttp_session: aiohttp.ClientSession):
    """Valid log level names are accepted and applied."""
    client = PyCalistaIsta(TEST_EMAIL, TEST_PASSWORD, session=mock_aiohttp_session)
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        client.set_log_level(level)
        assert logging.getLogger("pycalista_ista").level == getattr(logging, level)


@pytest.mark.asyncio
async def test_set_log_level_case_insensitive(
    mock_aiohttp_session: aiohttp.ClientSession,
):
    """set_log_level() is case-insensitive."""
    client = PyCalistaIsta(TEST_EMAIL, TEST_PASSWORD, session=mock_aiohttp_session)
    client.set_log_level("debug")
    assert logging.getLogger("pycalista_ista").level == logging.DEBUG


@pytest.mark.asyncio
async def test_set_log_level_invalid(mock_aiohttp_session: aiohttp.ClientSession):
    """Unknown log level raises ValueError."""
    client = PyCalistaIsta(TEST_EMAIL, TEST_PASSWORD, session=mock_aiohttp_session)
    with pytest.raises(ValueError, match="Invalid log level"):
        client.set_log_level("VERBOSE")


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pycalista_close():
    """close() shuts down an internally created session without raising."""
    async with aiohttp.ClientSession() as session:
        client = PyCalistaIsta(TEST_EMAIL, TEST_PASSWORD, session=session)
        await client.close()  # external session – should not close it
        assert not session.closed


@pytest.mark.asyncio
async def test_pycalista_async_context_manager():
    """async with PyCalistaIsta(...) calls close() on exit."""
    async with aiohttp.ClientSession() as session:
        async with PyCalistaIsta(TEST_EMAIL, TEST_PASSWORD, session=session) as client:
            assert client.account == TEST_EMAIL


# ---------------------------------------------------------------------------
# login()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pycalista_login_success(
    ista_main_client: PyCalistaIsta, mock_responses: aioresponses
):
    """login() returns True on HTTP 200."""
    mock_login_success(mock_responses)
    result = await ista_main_client.login()
    assert result is True


@pytest.mark.asyncio
async def test_pycalista_login_failure(
    ista_main_client: PyCalistaIsta, mock_responses: aioresponses
):
    """login() raises IstaLoginError on HTTP 302."""
    mock_responses.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        status=302,
        headers={"Location": "https://oficina.ista.es/login"},
    )
    with pytest.raises(IstaLoginError):
        await ista_main_client.login()


@pytest.mark.asyncio
async def test_pycalista_login_connection_error(
    ista_main_client: PyCalistaIsta, mock_responses: aioresponses
):
    """login() raises IstaConnectionError on network failure."""
    from aiohttp import ClientConnectionError

    mock_responses.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        exception=ClientConnectionError("refused"),
    )
    with pytest.raises(IstaConnectionError):
        await ista_main_client.login()


# ---------------------------------------------------------------------------
# get_devices_history()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_devices_history_invalid_dates(
    ista_main_client: PyCalistaIsta,
):
    """start > end raises ValueError."""
    with pytest.raises(ValueError, match="Start date must be before or equal"):
        await ista_main_client.get_devices_history(
            start=date(2025, 2, 1), end=date(2025, 1, 1)
        )


@pytest.mark.asyncio
async def test_pycalista_login_unexpected_exception_wrapped(
    ista_main_client: PyCalistaIsta,
):
    """Unexpected exceptions from VirtualApi.login are wrapped in IstaApiError."""
    from unittest.mock import AsyncMock, patch
    from pycalista_ista.exception_classes import IstaApiError

    with patch.object(
        ista_main_client._virtual_api, "login", new_callable=AsyncMock,
        side_effect=RuntimeError("something went very wrong"),
    ):
        with pytest.raises(IstaApiError, match="unexpected error occurred during login"):
            await ista_main_client.login()


@pytest.mark.asyncio
async def test_get_devices_history_unexpected_exception_wrapped(
    ista_main_client: PyCalistaIsta,
):
    """Unexpected exceptions from VirtualApi.get_devices_history are wrapped in IstaApiError."""
    from unittest.mock import AsyncMock, patch
    from pycalista_ista.exception_classes import IstaApiError

    with patch.object(
        ista_main_client._virtual_api,
        "get_devices_history",
        new_callable=AsyncMock,
        side_effect=RuntimeError("unexpected boom"),
    ):
        with pytest.raises(IstaApiError, match="unexpected error occurred while fetching"):
            await ista_main_client.get_devices_history(
                start=date(2025, 1, 1), end=date(2025, 1, 31)
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "excel_file_content", ["consulta_2024-11-30_2025-01-01.xls"], indirect=True
)
async def test_get_devices_history_success(
    ista_main_client: PyCalistaIsta,
    mock_responses: aioresponses,
    excel_file_content: bytes,
):
    """Full flow: login then get_devices_history returns devices."""
    start_dt = date(2024, 12, 1)
    end_dt = date(2024, 12, 30)

    mock_get_readings(
        mock_responses,
        excel_file_content,
        start_dt.strftime("%d/%m/%Y"),
        end_dt.strftime("%d/%m/%Y"),
    )

    devices = await ista_main_client.get_devices_history(start_dt, end_dt)
    assert isinstance(devices, dict)
    assert len(devices) > 0
