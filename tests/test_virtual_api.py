"""Tests for VirtualApi and login functionality."""

import re
from datetime import date, datetime, timedelta
from http import HTTPStatus
from io import BytesIO
from unittest.mock import Mock, patch

import pytest
import xlwt
from requests.exceptions import RequestException

from pycalista_ista import ParserError, PyCalistaIsta, ServerError
from pycalista_ista.exception_classes import LoginError
from pycalista_ista.models.heating_device import HeatingDevice
from pycalista_ista.virtual_api import VirtualApi
from tests.conftest import TEST_EMAIL


def test_virtual_api_initialization():
    """Test VirtualApi initialization."""
    api = VirtualApi("test@example.com", "password")
    assert api.username == "test@example.com"
    assert api.password == "password"
    assert api.cookies == {}
    assert api.session is not None


def test_login_success(requests_mock):
    """Test successful login."""
    api = VirtualApi("test@example.com", "password")

    requests_mock.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        cookies={"FGTServer": "testFGTServer"},
    )

    requests_mock.get(
        "https://oficina.ista.es/GesCon/GestionFincas.do?metodo=preCargaLecturasRadio",
        text="success",
    )

    api.login()
    assert "FGTServer" in api.cookies
    assert api.cookies["FGTServer"] == "testFGTServer"


def test_login_failure(requests_mock):
    """Test login failure."""
    api = VirtualApi("test@example.com", "wrong_password")

    requests_mock.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        headers={"Content-Length": "100"},
        text="Login failed",
    )

    with pytest.raises(LoginError, match="Login failed - invalid credentials"):
        api.login()


def test_relogin(requests_mock):
    """Test relogin functionality."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "old_cookie"}

    requests_mock.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        cookies={"FGTServer": "new_cookie"},
    )

    requests_mock.get(
        "https://oficina.ista.es/GesCon/GestionFincas.do?metodo=preCargaLecturasRadio",
        text="success",
    )

    api.relogin()
    assert api.cookies["FGTServer"] == "new_cookie"


def test_get_readings_chunk(requests_mock):
    """Test getting readings for a date range chunk."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "test_cookie"}

    # Create a minimal Excel file
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sheet1")

    # Add headers
    headers = ["Tipo", "N° Serie", "Ubicación", "01/01", "02/01"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header)

    # Add a row
    row_data = [
        "Radio Distribuidor de Costes de Calefacción",
        "12345",
        "Kitchen",
        100,
        150,
    ]
    for col, value in enumerate(row_data):
        sheet.write(1, col, value)

    # Write to BytesIO
    excel_content = BytesIO()
    workbook.save(excel_content)
    excel_content.seek(0)
    requests_mock.get(
        "https://oficina.ista.es/GesCon/GestionFincas.do",
        content=excel_content.getvalue(),
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"},
    )

    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 30)

    result = api._get_readings_chunk(start, end)
    assert result.read() == excel_content.read()


def test_get_readings_chunk_session_expired(requests_mock):
    """Test getting readings with expired session."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "expired_cookie"}

    requests_mock.post(
        "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do",
        cookies={"FGTServer": "new_cookie"},
    )

    requests_mock.get(
        "https://oficina.ista.es/GesCon/GestionFincas.do?metodo=preCargaLecturasRadio",
        text="success",
    )

    # Create Excel file for session expired test
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sheet1")

    # Add headers
    headers = ["Tipo", "N° Serie", "Ubicación", "01/01", "02/01"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header)

    # Add a row
    row_data = [
        "Radio Distribuidor de Costes de Calefacción",
        "12345",
        "Kitchen",
        100,
        150,
    ]
    for col, value in enumerate(row_data):
        sheet.write(1, col, value)

    # Write to BytesIO
    excel_content = BytesIO()
    workbook.save(excel_content)
    excel_content.seek(0)

    matcher = re.compile(r"https://oficina\.ista\.es/GesCon/GestionFincas\.do.*")
    requests_mock.get(
        matcher,
        text="<html>Session expired</html>",
        headers={"Content-Type": "text/html"},
        request_headers={"Cookie": "FGTServer=expired_cookie"},
    )

    requests_mock.get(
        matcher,
        content=excel_content.getvalue(),
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"},
        request_headers={"Cookie": "FGTServer=new_cookie"},
    )

    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 30)

    result = api._get_readings_chunk(start, end)
    assert result.read() == excel_content.getvalue()
    assert api.cookies["FGTServer"] == "new_cookie"


def test_merge_device_histories():
    """Test merging device histories from multiple periods."""
    api = VirtualApi("test@example.com", "password")

    device1 = HeatingDevice("12345", "Kitchen")
    device1.add_reading_value(100, datetime(2025, 1, 1))

    device2 = HeatingDevice("12345", "Kitchen")
    device2.add_reading_value(150, datetime(2025, 2, 1))

    device_lists = [{"12345": device1}, {"12345": device2}]

    merged = api.merge_device_histories(device_lists)
    assert len(merged) == 1
    assert len(merged["12345"].history) == 2
    assert merged["12345"].history[0].reading == 100
    assert merged["12345"].history[1].reading == 150


def test_get_devices_history(requests_mock):
    """Test getting complete device history."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "test_cookie"}

    # Create Excel file for device history test
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sheet1")

    # Add headers
    headers = ["Tipo", "N° Serie", "Ubicación", "01/01", "02/01"]
    for col, header in enumerate(headers):
        sheet.write(0, col, header)

    # Add a row
    row_data = [
        "Radio Distribuidor de Costes de Calefacción",
        "12345",
        "Kitchen",
        100,
        150,
    ]
    for col, value in enumerate(row_data):
        sheet.write(1, col, value)

    # Write to BytesIO
    excel_content = BytesIO()
    workbook.save(excel_content)
    excel_content.seek(0)

    requests_mock.get(
        "https://oficina.ista.es/GesCon/GestionFincas.do",
        content=excel_content.getvalue(),
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"},
    )

    start = date(2025, 1, 1)
    end = date(2025, 1, 30)

    with patch("pycalista_ista.excel_parser.ExcelParser") as MockParser:
        mock_devices = {"12345": HeatingDevice("12345", "Kitchen")}
        MockParser.return_value.get_devices_history.return_value = mock_devices

        history = api.get_devices_history(start, end)
        assert len(history) == 1
        assert "12345" in history


@pytest.mark.parametrize("ista_client", [TEST_EMAIL], indirect=True)
@pytest.mark.usefixtures("mock_requests_login")
@pytest.mark.usefixtures("mock_requests_data")
def test_pycalista_login(ista_client: PyCalistaIsta) -> None:
    """Test PyCalistaIsta login integration."""
    ista_client.login()
    assert ista_client._virtual_api.cookies["FGTServer"] == "testFGTServer"


@pytest.mark.parametrize("ista_client", [TEST_EMAIL], indirect=True)
@pytest.mark.usefixtures("mock_wrong_requests_login")
@pytest.mark.usefixtures("mock_requests_data")
def test_pycalista_wrong_login(ista_client: PyCalistaIsta) -> None:
    """Test PyCalistaIsta login failure."""
    with pytest.raises(LoginError):
        ista_client.login()
