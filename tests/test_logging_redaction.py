"""Tests that DEBUG logs never carry credentials, cookies or property data."""

import logging
import re
from datetime import date

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses
from yarl import URL

from pycalista_ista import PyCalistaIsta
from pycalista_ista.const import CONSUMPTION_URL, DATA_URL, INVOICES_URL
from pycalista_ista.exception_classes import (
    IstaApiError,
    IstaConnectionError,
    IstaLoginError,
)
from pycalista_ista.virtual_api import (
    MASKED_VALUE,
    VirtualApi,
    _cookie_names,
    _redact_mapping,
    _redact_response_snippet,
    _redact_sensitive_pairs,
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
READINGS_PATTERN = re.compile(re.escape(DATA_URL) + r".*listadoLecturasRadio.*")
KC_DISCOVERY_PATTERN = re.compile(r"https://login\.ista\.com/.*auth.*")
KC_ACTION_PATTERN = re.compile(
    re.escape("https://login.ista.com/mock-auth-action") + r".*"
)

# One-time Keycloak tokens, as they appear in the login form action URL.
KC_SESSION_CODE = "Zq7-session-code-value"
KC_EXECUTION = "Zq7-execution-value"
KC_TAB_ID = "Zq7-tab-value"
KC_TOKENS = (KC_SESSION_CODE, KC_EXECUTION, KC_TAB_ID)
KC_ACTION_URL = (
    "https://login.ista.com/mock-auth-action"
    f"?session_code={KC_SESSION_CODE}&execution={KC_EXECUTION}"
    f"&client_id=abonado-service&tab_id={KC_TAB_ID}"
)


def kc_login_page(action_url: str = KC_ACTION_URL) -> str:
    """Return a synthetic Keycloak login form page."""
    return (
        "<html><body>"
        f'<form method="post" action="{action_url}">'
        '<input type="text" name="username"/>'
        '<input type="password" name="password"/>'
        "</form></body></html>"
    )


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
    """Discovery and selection never log the property ID or its label.

    The mocked page has one property and no ``selected`` attribute, which is
    the live shape after a switch, so the default-selection path is covered.
    """
    caplog.set_level(logging.DEBUG)

    def preload_callback(url, **kwargs):
        return CallbackResult(
            status=200,
            body=account_page(),
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

    # The portal smuggles the property ID inside another parameter's value,
    # encoded as %C2%B6m%3D<id>. Masking by key name alone leaves it in the log.
    smuggled = "https://h/x.do?d-148657-e=2%C2%B6m%3DZq7-secret&6578706f7274=1"
    assert "Zq7-secret" not in _redact_url(smuggled)
    assert "Zq7-secret" not in str(_redact_mapping({"d-148657-e": "2¶m=Zq7-secret"}))
    assert _redact_response_snippet("<html>hola</html>") == "<html>hola</html>"
    assert (
        _redact_response_snippet('<select name="idAbonado">x</select>')
        == "<page with linked-property selector omitted>"
    )
    async with aiohttp.ClientSession() as session:
        assert _cookie_names(session, "https://oficina.ista.es/") == []


async def test_keycloak_action_url_tokens_are_masked_on_error(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """A failing request logs the action URL without its one-time tokens.

    D1: the unrecoverable-status log line used the raw URL. The discovery
    snippet (D2) must be masked too.
    """
    caplog.set_level(logging.DEBUG)
    mock_responses.get(
        KC_DISCOVERY_PATTERN,
        status=200,
        headers={"Content-Type": "text/html;charset=utf-8"},
        body=kc_login_page().encode(),
        repeat=True,
    )
    mock_responses.post(
        KC_ACTION_PATTERN,
        status=403,
        headers={"Content-Type": "text/html;charset=utf-8"},
        body=b"<html>Forbidden</html>",
        repeat=True,
    )
    client = VirtualApi(
        username=TEST_EMAIL, password=SECRET_PASSWORD, session=mock_aiohttp_session
    )

    with pytest.raises(IstaConnectionError):
        await client.login()

    messages = [record.getMessage() for record in caplog.records]
    status_lines = [
        message
        for message in messages
        if message.startswith("Request failed with unrecoverable status")
    ]
    snippet_lines = [message for message in messages if "Received response" in message]
    assert status_lines, "expected the unrecoverable-status error log"
    assert snippet_lines, "expected the response log"
    for value in KC_TOKENS:
        assert value not in caplog.text, "a Keycloak token appears in the logs"
    assert MASKED_VALUE in status_lines[0]


async def test_credential_failure_page_tokens_are_masked(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """The Keycloak error page is logged without its one-time tokens.

    D2: the credential-failure path logged the raw body snippet.
    """
    caplog.set_level(logging.DEBUG)
    error_page = (
        "<html><body>"
        f'<form method="post" action="{KC_ACTION_URL}">'
        '<div class="kc-feedback-text">Invalid username or password.</div>'
        "</form></body></html>"
    )
    mock_responses.get(
        KC_DISCOVERY_PATTERN,
        status=200,
        headers={"Content-Type": "text/html;charset=utf-8"},
        body=kc_login_page().encode(),
        repeat=True,
    )
    mock_responses.post(
        KC_ACTION_PATTERN,
        status=200,
        headers={"Content-Type": "text/html;charset=utf-8"},
        body=error_page.encode(),
        repeat=True,
    )
    client = VirtualApi(
        username=TEST_EMAIL, password=SECRET_PASSWORD, session=mock_aiohttp_session
    )

    with pytest.raises(IstaLoginError):
        await client.login()

    failure_lines = [
        record.getMessage()
        for record in caplog.records
        if "Login failed" in record.getMessage()
    ]
    assert failure_lines, "expected the credential-failure error log"
    assert "Invalid username or password" in failure_lines[0]
    for value in KC_TOKENS:
        assert value not in caplog.text, "a Keycloak token appears in the logs"


async def test_readings_snippet_redacts_the_selector_page(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """An HTML answer on the readings path logs no property ID or label.

    D3: the readings path logged the first 250 characters raw, and the
    session-expired page is exactly the linked-property selector page.
    """
    caplog.set_level(logging.DEBUG)
    mock_responses.get(
        READINGS_PATTERN,
        status=200,
        headers={"Content-Type": "text/html; charset=UTF-8"},
        body=account_page(selected=PROPERTY_ID).encode(),
        repeat=True,
    )
    client = VirtualApi(
        username=TEST_EMAIL, password=SECRET_PASSWORD, session=mock_aiohttp_session
    )

    with pytest.raises(IstaApiError):
        await client.get_devices_history(date(2026, 2, 1), date(2026, 2, 2))

    mismatch_lines = [
        record.getMessage()
        for record in caplog.records
        if "Expected Excel file" in record.getMessage()
    ]
    assert mismatch_lines, "expected the content-type error log"
    assert PROPERTY_ID not in caplog.text, "the property ID appears in the logs"
    assert PROPERTY_LABEL not in caplog.text, "the property label appears in the logs"


async def test_redact_pairs_masks_html_escaped_query_values():
    """Sensitive pairs are masked in plain text, URLs and HTML attributes."""
    escaped = (
        '<form action="https://login.ista.com/x?session_code=AAA&amp;'
        'execution=BBB&tab_id=CCC">'
    )
    masked = _redact_sensitive_pairs(escaped)

    assert "AAA" not in masked
    assert "BBB" not in masked
    assert "CCC" not in masked
    assert masked.count(MASKED_VALUE) == 3
    assert _redact_sensitive_pairs("metodo=buscarRecibos") == "metodo=buscarRecibos"


async def test_undecodable_readings_body_logs_no_property_data(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """An undecodable readings body logs only its hex signature.

    The session-expired page can arrive in an encoding that the client cannot
    decode. The bytes must not be logged as text, because they can hold the
    property ID and label.
    """
    caplog.set_level(logging.DEBUG)
    body = (
        '<html><body><select name="idAbonado">'
        f'<option value="{PROPERTY_ID}" selected>{PROPERTY_LABEL}</option>'
        "</select>\xf1</body></html>"
    ).encode("latin-1")
    mock_responses.get(
        READINGS_PATTERN,
        status=200,
        headers={"Content-Type": "text/html; charset=x-unknown-encoding"},
        body=body,
        repeat=True,
    )
    client = VirtualApi(
        username=TEST_EMAIL, password=SECRET_PASSWORD, session=mock_aiohttp_session
    )

    with pytest.raises(IstaApiError):
        await client.get_devices_history(date(2026, 2, 1), date(2026, 2, 2))

    assert PROPERTY_ID.encode() not in caplog.text.encode()
    assert PROPERTY_LABEL.encode() not in caplog.text.encode()
    assert "Response signature (first 16 bytes, hex)" in caplog.text


SECRET_PROPERTY_PARAM = "Zq7-secret-property-param"

EXPORT_ANCHOR = (
    '<a href="GestionFacturacion.do?d-148657-e=1'
    f'&param={SECRET_PROPERTY_PARAM}&6578706f7274=1">Excel</a>'
)
EXPORT_URL_PATTERN = re.compile(
    r"https://oficina\.ista\.es/.*GestionFacturacion\.do\?.*6578706f7274=1.*"
)


async def test_invoice_export_url_log_masks_the_property_param(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """R2: the invoice export URL is logged without its property parameter."""
    caplog.set_level(logging.DEBUG)
    mock_responses.get(
        re.compile(re.escape(INVOICES_URL) + r".*metodo=buscarRecibos.*"),
        status=200,
        body=f"<html><body>{EXPORT_ANCHOR}</body></html>".encode(),
        repeat=True,
    )
    mock_responses.get(
        EXPORT_URL_PATTERN,
        status=200,
        headers={"Content-Type": "application/vnd.ms-excel"},
        body=b"not a workbook",
        repeat=True,
    )
    client = VirtualApi(
        username=TEST_EMAIL, password=SECRET_PASSWORD, session=mock_aiohttp_session
    )

    with pytest.raises(IstaApiError):
        await client.get_invoice_xls()

    export_lines = [
        record.getMessage()
        for record in caplog.records
        if "invoice XLS export URL" in record.getMessage()
    ]
    assert export_lines, "expected the export URL debug log"
    assert SECRET_PROPERTY_PARAM not in caplog.text
    assert MASKED_VALUE in export_lines[0]


async def test_billed_export_url_log_masks_the_property_param(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """R2: the billed export URL is logged without its property parameter."""
    caplog.set_level(logging.DEBUG)
    mock_responses.get(
        re.compile(re.escape(CONSUMPTION_URL) + r".*metodo=buscarLecturas.*"),
        status=200,
        body=b"<html>preload</html>",
        repeat=True,
    )
    mock_responses.post(
        re.compile(re.escape(CONSUMPTION_URL) + r".*metodo=buscarLecturas.*"),
        status=200,
        body=f"<html><body>{EXPORT_ANCHOR}</body></html>".encode(),
        repeat=True,
    )
    mock_responses.get(
        EXPORT_URL_PATTERN,
        status=200,
        headers={"Content-Type": "application/vnd.ms-excel"},
        body=b"not a workbook",
        repeat=True,
    )
    client = VirtualApi(
        username=TEST_EMAIL, password=SECRET_PASSWORD, session=mock_aiohttp_session
    )

    with pytest.raises(IstaApiError):
        await client.get_billed_consumption()

    export_lines = [
        record.getMessage()
        for record in caplog.records
        if "billed consumption export URL" in record.getMessage()
    ]
    assert export_lines, "expected the export URL debug log"
    assert SECRET_PROPERTY_PARAM not in caplog.text
    assert MASKED_VALUE in export_lines[0]


async def test_connection_error_message_masks_sensitive_query_values(
    mock_aiohttp_session, mock_responses: aioresponses, caplog
):
    """The raised error and its log line do not repeat a sensitive query value.

    A connection error carries the request URL in its own text, and consumers
    log library exceptions, so that text is masked as well.
    """
    caplog.set_level(logging.DEBUG)
    url = f"https://oficina.ista.es/GesCon/GestionFacturacion.do?param={SECRET_PROPERTY_PARAM}"
    mock_responses.get(
        re.compile(re.escape(url) + r".*"),
        exception=aiohttp.ClientConnectionError(f"Connection refused: GET {url}"),
        repeat=True,
    )
    client = VirtualApi(
        username=TEST_EMAIL, password=SECRET_PASSWORD, session=mock_aiohttp_session
    )

    with pytest.raises(IstaConnectionError) as error:
        await client._send_request("GET", url, retry_attempts=0)

    assert "Connection refused" in str(error.value)
    assert SECRET_PROPERTY_PARAM not in str(error.value)
    assert SECRET_PROPERTY_PARAM not in caplog.text
