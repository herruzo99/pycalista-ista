"""Tests that DEBUG logs never carry credentials, cookies or property data."""

import logging
import re

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from yarl import URL

from pycalista_ista import PyCalistaIsta
from pycalista_ista.const import DATA_URL
from pycalista_ista.virtual_api import (
    MASKED_VALUE,
    _cookie_names,
    _redact_mapping,
    _redact_response_snippet,
    _redact_url,
)
from tests.conftest import TEST_EMAIL, mock_login_success

pytestmark = pytest.mark.asyncio

# A password with a distinctive value, so a substring match is meaningful.
SECRET_PASSWORD = "Zq7-very-unique-passphrase"
# A cookie value the library must never log (defect F2 of the audit).
SECRET_COOKIE_VALUE = "Zq7-co0kie-value-never-logged"
COOKIE_NAME = "JSESSIONID"
PORTAL_COOKIE_VALUES = ("MOCK_KC_SESSION", "MOCK_KCSESSID", "MOCK_SESSION_ID")

PROPERTY_ID = "9f3c1a77b2e4d001"
PROPERTY_LABEL = "Calle Mayor 1, 2ºA"

PRELOAD_PATTERN = re.compile(re.escape(DATA_URL) + r".*preCargaLecturasRadio.*")
SWITCH_PATTERN = re.compile(
    r"https://oficina\.ista\.es/GesCon/GestionOficinaVirtual\.do.*"
)


def account_page(selected: str | None = None) -> str:
    """Return a synthetic portal page with the linked-property selector."""
    chosen = " selected" if selected else ""
    return (
        "<html><body><form name='seleccionAbonado'>"
        '<select name="idAbonado" id="idAbonado">'
        f'<option value="{PROPERTY_ID}"{chosen}>{PROPERTY_LABEL}</option>'
        "</select></form></body></html>"
    )


def assert_no_secret(text: str) -> None:
    """Fail with a safe message if a secret appears in the log text."""
    assert SECRET_PASSWORD not in text, "the password appears in the logs"
    for cookie_value in PORTAL_COOKIE_VALUES:
        assert cookie_value not in text, "a cookie value appears in the logs"


async def test_login_debug_logs_hide_password_and_cookies(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """A full login logs no password and no cookie value."""
    caplog.set_level(logging.DEBUG)
    # An existing portal session cookie, as on a long-lived client.
    mock_aiohttp_session.cookie_jar.update_cookies(
        {COOKIE_NAME: SECRET_COOKIE_VALUE},
        response_url=URL("https://oficina.ista.es/"),
    )
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=SECRET_PASSWORD,
        session=mock_aiohttp_session,
    )

    assert await client.login() is True

    assert caplog.text, "expected DEBUG records"
    assert_no_secret(caplog.text)
    assert SECRET_COOKIE_VALUE not in caplog.text, "a cookie value appears in the logs"
    # The credential POST is logged with the password value replaced.
    assert MASKED_VALUE in caplog.text
    # Cookie names stay visible for support; their values do not.
    assert COOKIE_NAME in caplog.text


async def test_property_id_and_label_are_not_logged(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """Discovery and selection never log the property ID or its label."""
    caplog.set_level(logging.DEBUG)

    def preload_callback(url, **kwargs):
        return CallbackResult(
            status=200,
            body=account_page(selected=PROPERTY_ID),
            content_type="text/html; charset=UTF-8",
        )

    def switch_callback(url, **kwargs):
        return CallbackResult(
            status=200, body="<html>OK</html>", content_type="text/html"
        )

    mock_responses.get(PRELOAD_PATTERN, callback=preload_callback, repeat=True)
    mock_responses.post(SWITCH_PATTERN, callback=switch_callback, repeat=True)
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=SECRET_PASSWORD,
        session=mock_aiohttp_session,
        account_id=PROPERTY_ID,
    )

    assert await client.login() is True
    accounts = await client.list_accounts()

    assert [account.account_id for account in accounts] == [PROPERTY_ID]
    assert_no_secret(caplog.text)
    assert PROPERTY_ID not in caplog.text, "the property ID appears in the logs"
    assert PROPERTY_LABEL not in caplog.text, "the property label appears in the logs"


async def test_invoice_request_logs_keep_the_url(caplog):
    """Non-sensitive request data stays readable at DEBUG level."""
    from pycalista_ista.const import INVOICES_URL
    from pycalista_ista.virtual_api import VirtualApi

    caplog.set_level(logging.DEBUG)
    async with aiohttp.ClientSession() as session:
        client = VirtualApi(
            username=TEST_EMAIL, password=SECRET_PASSWORD, session=session
        )
        with aioresponses() as mock_responses:
            mock_responses.get(
                re.compile(re.escape(INVOICES_URL) + r".*metodo=buscarRecibos.*"),
                status=200,
                body="<html><body>sin recibos</body></html>",
            )
            await client.get_invoices()

    assert "buscarRecibos" in caplog.text


async def test_redact_helpers_mask_sensitive_values():
    """The module helpers mask only the sensitive keys."""
    assert _redact_mapping(
        {"password": "p", "username": "u", "idAbonado": "123", "param": "123"}
    ) == {
        "password": MASKED_VALUE,
        "username": "u",
        "idAbonado": MASKED_VALUE,
        "param": MASKED_VALUE,
    }
    assert _redact_url("https://h/x.do?metodo=a&param=123") == (
        f"https://h/x.do?metodo=a&param={MASKED_VALUE}"
    )
    assert _redact_url("https://h/x.do?metodo=a") == "https://h/x.do?metodo=a"
    assert _redact_url("mailto:x@example.com").startswith("mailto:")
    assert _redact_mapping([("password", "p"), ("metodo", "a")]) == [
        ("password", MASKED_VALUE),
        ("metodo", "a"),
    ]
    assert _redact_mapping("raw string body") == MASKED_VALUE
    assert _redact_mapping(None) is None
    assert _redact_response_snippet("<html>hola</html>") == "<html>hola</html>"
    assert (
        _redact_response_snippet('<select name="idAbonado">x</select>')
        == "<page with linked-property selector omitted>"
    )
    async with aiohttp.ClientSession() as session:
        assert _cookie_names(session, "https://oficina.ista.es/") == []
