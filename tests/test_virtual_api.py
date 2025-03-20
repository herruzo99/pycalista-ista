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
from pycalista_ista.models import ColdWaterDevice, Device, HeatingDevice, HotWaterDevice
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

def test_interpolate_and_trim_device_reading_basic():
    """Test basic interpolation with simple readings."""
    api = VirtualApi("test@example.com", "password")
    
    # Create a device with some missing values
    device = Device("12345", "Kitchen")
    device.add_reading_value(100, datetime(2025, 1, 1))
    device.add_reading_value(None, datetime(2025, 1, 2))
    device.add_reading_value(None, datetime(2025, 1, 3))
    device.add_reading_value(200, datetime(2025, 1, 4))
    
    fixed_device = api._interpolate_and_trim_device_reading(device)
    
    # Check that the interpolated device has the correct values
    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 4
    assert readings[0].reading == 100
    assert readings[1].reading == 133.33  # Interpolated value for Jan 2
    assert readings[2].reading == 166.67  # Interpolated value for Jan 3
    assert readings[3].reading == 200
    assert fixed_device.location == "Kitchen"
    assert fixed_device.serial_number == '12345'


def test_interpolate_and_trim_device_keep_device_data():
    """Test basic interpolation with simple readings."""
    api = VirtualApi("test@example.com", "password")
    
    device_1 = Device("12345", "Kitchen")
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == "Kitchen"
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == Device

    device_1 = Device("12345", None)
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == ""
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == Device

    device_1 = HotWaterDevice("12345", "Kitchen")
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == "Kitchen"
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == HotWaterDevice

    device_1 = HotWaterDevice("12345", None)
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == ""
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == HotWaterDevice

    device_1 = ColdWaterDevice("12345", "Kitchen")
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == "Kitchen"
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == ColdWaterDevice

    device_1 = ColdWaterDevice("12345", None)
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == ""
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == ColdWaterDevice

    device_1 = HeatingDevice("12345", "Kitchen")
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == "Kitchen"
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == HeatingDevice

    device_1 = HeatingDevice("12345", None)
    fixed_device_1 = api._interpolate_and_trim_device_reading(device_1)
    assert fixed_device_1.location == ""
    assert fixed_device_1.serial_number == '12345'
    assert fixed_device_1.__class__ == HeatingDevice


def test_interpolate_and_trim_device_reading_no_change_needed():
    """Test when no interpolation is needed."""
    api = VirtualApi("test@example.com", "password")
    
    # Create a device with only valid readings
    device = Device("12345", "Kitchen")
    device.add_reading_value(100, datetime(2025, 1, 1))
    device.add_reading_value(150, datetime(2025, 1, 2))
    device.add_reading_value(200, datetime(2025, 1, 3))
    
    fixed_device = api._interpolate_and_trim_device_reading(device)
    
    # Verify no changes to readings
    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 3
    assert readings[0].reading == 100
    assert readings[1].reading == 150
    assert readings[2].reading == 200

def test_interpolate_and_trim_device_reading_multiple_missing_sequences():
    """Test interpolation with multiple sequences of missing values."""
    api = VirtualApi("test@example.com", "password")
    
    device = Device("12345", "Kitchen")
    device.add_reading_value(100, datetime(2025, 1, 1))
    device.add_reading_value(None, datetime(2025, 1, 2))
    device.add_reading_value(200, datetime(2025, 1, 3))
    device.add_reading_value(None, datetime(2025, 1, 4))
    device.add_reading_value(None, datetime(2025, 1, 5))
    device.add_reading_value(400, datetime(2025, 1, 6))
    
    fixed_device = api._interpolate_and_trim_device_reading(device)

    # Check that all sequences were interpolated correctly
    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 6
    assert readings[0].reading == 100
    assert readings[1].reading == 150  # Interpolated value
    assert readings[2].reading == 200
    assert readings[3].reading == 266.67  # Interpolated value
    assert readings[4].reading == 333.33  # Interpolated value
    assert readings[5].reading == 400


def test_interpolate_and_trim_device_reading_trim_start_end():
    """Test trimming of missing values at start and end."""
    api = VirtualApi("test@example.com", "password")
    
    # Add readings with NULL values at start and end
    device = Device("12345", "Kitchen")
    device.add_reading_value(None, datetime(2025, 1, 1))  # Should be trimmed
    device.add_reading_value(100, datetime(2025, 1, 2))
    device.add_reading_value(200, datetime(2025, 1, 3))
    device.add_reading_value(None, datetime(2025, 1, 4))  # Should be trimmed
    
    fixed_device = api._interpolate_and_trim_device_reading(device)

    # Check that null values at start and end were trimmed
    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 2
    assert readings[0].reading == 100
    assert readings[1].reading == 200


def test_interpolate_and_trim_device_reading_only_one_valid():
    """Test case with only one valid reading."""
    api = VirtualApi("test@example.com", "password")
    
    device = Device("12345", "Kitchen")
    device.add_reading_value(None, datetime(2025, 1, 1))
    device.add_reading_value(100, datetime(2025, 1, 2))
    device.add_reading_value(None, datetime(2025, 1, 3))
    
    fixed_device = api._interpolate_and_trim_device_reading(device)

    # Should only have the one valid reading
    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 1
    assert readings[0].reading == 100

def test_interpolate_and_trim_device_reading_unsorted_dates():
    """Test interpolation works correctly with unsorted input dates."""
    api = VirtualApi("test@example.com", "password")
    
    # Add readings in unsorted order
    device = Device("12345", "Kitchen")
    device.add_reading_value(200, datetime(2025, 1, 3))
    device.add_reading_value(None, datetime(2025, 1, 2))
    device.add_reading_value(100, datetime(2025, 1, 1))
    
    fixed_device = api._interpolate_and_trim_device_reading(device)

    # Check interpolation worked correctly despite unsorted input
    readings = sorted(fixed_device.history, key=lambda r: r.date)
    assert len(readings) == 3
    assert readings[0].reading == 100
    assert readings[1].reading == 150  # Interpolated value
    assert readings[2].reading == 200
