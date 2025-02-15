"""Tests for VirtualApi and login functionality."""

from datetime import datetime, date, timedelta
from http import HTTPStatus
from io import BytesIO
import pytest
from unittest.mock import Mock, patch

from requests.exceptions import RequestException

from pycalista_ista.virtual_api import VirtualApi
from pycalista_ista.exception_classes import LoginError
from pycalista_ista.models.heating_device import HeatingDevice
from pycalista_ista import ParserError, PyCalistaIsta, ServerError
from tests.conftest import TEST_EMAIL


# VirtualApi Tests

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
    
    # Mock successful login response
    requests_mock.post(
        "https://www.ista.es/IstaWebApp/loginAbonado.do",
        headers={"Content-Length": None},
        cookies={"FGTServer": "testFGTServer"}
    )
    
    # Mock preload request
    requests_mock.get(
        "https://www.ista.es/IstaWebApp/listadoLecturasRadio.do",
        text="success"
    )
    
    api.login()
    assert "FGTServer" in api.cookies
    assert api.cookies["FGTServer"] == "testFGTServer"

def test_login_failure(requests_mock):
    """Test login failure."""
    api = VirtualApi("test@example.com", "wrong_password")
    
    # Mock failed login response
    requests_mock.post(
        "https://www.ista.es/IstaWebApp/loginAbonado.do",
        headers={"Content-Length": "100"},
        text="Login failed"
    )
    
    with pytest.raises(LoginError, match="Login failed - invalid credentials"):
        api.login()

def test_relogin(requests_mock):
    """Test relogin functionality."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "old_cookie"}
    
    # Mock successful login response
    requests_mock.post(
        "https://www.ista.es/IstaWebApp/loginAbonado.do",
        headers={"Content-Length": None},
        cookies={"FGTServer": "new_cookie"}
    )
    
    # Mock preload request
    requests_mock.get(
        "https://www.ista.es/IstaWebApp/listadoLecturasRadio.do",
        text="success"
    )
    
    api.relogin()
    assert api.cookies["FGTServer"] == "new_cookie"

def test_get_readings_chunk(requests_mock):
    """Test getting readings for a date range chunk."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "test_cookie"}
    
    # Mock Excel response
    excel_content = b"test excel content"
    requests_mock.get(
        "https://www.ista.es/IstaWebApp/listadoLecturasRadio.do",
        content=excel_content,
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"}
    )
    
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 30)
    
    result = api._get_readings_chunk(start, end)
    assert result.read() == excel_content

def test_get_readings_chunk_session_expired(requests_mock):
    """Test getting readings with expired session."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "expired_cookie"}
    
    # Mock HTML response (session expired)
    requests_mock.get(
        "https://www.ista.es/IstaWebApp/listadoLecturasRadio.do",
        text="<html>Session expired</html>",
        headers={"Content-Type": "text/html"}
    )
    
    # Mock relogin
    requests_mock.post(
        "https://www.ista.es/IstaWebApp/loginAbonado.do",
        headers={"Content-Length": None},
        cookies={"FGTServer": "new_cookie"}
    )
    
    # Mock preload request
    requests_mock.get(
        "https://www.ista.es/IstaWebApp/listadoLecturasRadio.do",
        text="success"
    )
    
    # Mock successful Excel response after relogin
    excel_content = b"test excel content"
    requests_mock.get(
        "https://www.ista.es/IstaWebApp/listadoLecturasRadio.do",
        content=excel_content,
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"}
    )
    
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 30)
    
    result = api._get_readings_chunk(start, end)
    assert result.read() == excel_content
    assert api.cookies["FGTServer"] == "new_cookie"

def test_merge_device_histories():
    """Test merging device histories from multiple periods."""
    api = VirtualApi("test@example.com", "password")
    
    # Create test devices with different readings
    device1 = HeatingDevice("12345", "Kitchen")
    device1.add_reading_value(100, datetime(2025, 1, 1))
    
    device2 = HeatingDevice("12345", "Kitchen")
    device2.add_reading_value(150, datetime(2025, 2, 1))
    
    device_lists = [
        {"12345": device1},
        {"12345": device2}
    ]
    
    merged = api.merge_device_histories(device_lists)
    assert len(merged) == 1
    assert len(merged["12345"].history) == 2
    assert merged["12345"].history[0].reading == 100
    assert merged["12345"].history[1].reading == 150

def test_get_devices_history(requests_mock):
    """Test getting complete device history."""
    api = VirtualApi("test@example.com", "password")
    api.cookies = {"FGTServer": "test_cookie"}
    
    # Mock Excel response
    excel_content = b"test excel content"
    requests_mock.get(
        "https://www.ista.es/IstaWebApp/listadoLecturasRadio.do",
        content=excel_content,
        headers={"Content-Type": "application/vnd.ms-excel;charset=iso-8859-1"}
    )
    
    start = date(2025, 1, 1)
    end = date(2025, 1, 30)
    
    with patch('pycalista_ista.excel_parser.ExcelParser') as MockParser:
        mock_devices = {
            "12345": HeatingDevice("12345", "Kitchen")
        }
        MockParser.return_value.get_devices_history.return_value = mock_devices
        
        history = api.get_devices_history(start, end)
        assert len(history) == 1
        assert "12345" in history

# PyCalistaIsta Integration Tests

@pytest.mark.parametrize("ista_client", [TEST_EMAIL], indirect=True)
@pytest.mark.usefixtures("mock_requests_login")
@pytest.mark.usefixtures("mock_requests_data")
def test_pycalista_login(ista_client: PyCalistaIsta) -> None:
    """Test PyCalistaIsta login integration."""
    ista_client.login()
    assert ista_client._virtual_api.cookies['FGTServer'] == "testFGTServer"

@pytest.mark.parametrize("ista_client", [TEST_EMAIL], indirect=True)
@pytest.mark.usefixtures("mock_wrong_requests_login")
@pytest.mark.usefixtures("mock_requests_data")
def test_pycalista_wrong_login(ista_client: PyCalistaIsta) -> None:
    """Test PyCalistaIsta login failure."""
    with pytest.raises(LoginError):
        ista_client.login()
