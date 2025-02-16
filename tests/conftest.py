"""Fixtures for Tests."""

import os
from http import HTTPStatus
from io import BytesIO
from pathlib import Path

import pytest
from requests_mock.mocker import Mocker as RequestsMock

from pycalista_ista import PyCalistaIsta
from pycalista_ista.const import DATA_URL, LOGIN_URL

TEST_EMAIL = "demouser@example.com"
TEST_WRONG_EMAIL = "wronguser@example.com"
TEST_PASSWORD = "password"


@pytest.fixture
def excel_file(request):
    path = Path(__file__).parent / request.param

    with open(path, "rb") as fh:
        buf = BytesIO(fh.read())
    return buf


@pytest.fixture
def ista_client(request) -> PyCalistaIsta:
    """Create Bring instance."""
    ista = PyCalistaIsta(
        email=getattr(request, "param", TEST_EMAIL),
        password=TEST_PASSWORD,
    )
    return ista


@pytest.fixture
def mock_requests_data(requests_mock: RequestsMock) -> RequestsMock:
    """Mock requests to Login Endpoints."""
    requests_mock.get(
        DATA_URL + "?metodo=preCargaLecturasRadio",
        text="""<html lang="es"></html>""",
    )

    return requests_mock


@pytest.fixture
def mock_wrong_requests_login(requests_mock: RequestsMock) -> RequestsMock:
    """Mock requests to Login Endpoints."""
    requests_mock.post(
        LOGIN_URL,
        text="""<html lang="es"></html>""",
        headers={"Content-Length": "100"},  # This triggers the login error check
    )

    return requests_mock


@pytest.fixture
def mock_requests_login(requests_mock: RequestsMock) -> RequestsMock:
    """Mock requests to Login Endpoints."""

    def response_callback(request, context):
        # Set cookies directly
        context.cookies["FGTServer"] = "testFGTServer"
        context.cookies["JSESSIONID"] = "testJSESSIONID"
        context.cookies["rol"] = "7"
        context.cookies["delegacion"] = "3"
        return """<html lang="es"></html>"""

    requests_mock.post(LOGIN_URL, text=response_callback)
    return requests_mock
