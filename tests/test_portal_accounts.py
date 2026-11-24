"""Tests for linked-property discovery and selection (experimental)."""

import asyncio
import re
from typing import Any

import pytest
from aioresponses import CallbackResult, aioresponses

from pycalista_ista import PyCalistaIsta
from pycalista_ista.const import ACCOUNT_SWITCH_URL, DATA_URL
from pycalista_ista.exception_classes import IstaApiError
from pycalista_ista.models import PortalAccount
from pycalista_ista.virtual_api import VirtualApi
from tests.conftest import TEST_EMAIL, TEST_PASSWORD, mock_login_success

pytestmark = pytest.mark.asyncio

PRELOAD_PATTERN = re.compile(re.escape(DATA_URL) + r".*preCargaLecturasRadio.*")
SWITCH_PATTERN = re.compile(re.escape(ACCOUNT_SWITCH_URL) + r".*metodo=cambioAbonado.*")

# Opaque IDs and labels modelled on the portal: long, meaningless strings.
ACCOUNT_A = "9f3c1a77b2e4d001"
ACCOUNT_B = "4b8e2d55c9a1f022"
LABEL_A = "Calle Mayor 1, 2ºA"
LABEL_B = "Garaje Calle Mayor 1"


def account_page(options: list[tuple[str, str]], selected: str | None = None) -> str:
    """Return a synthetic portal page with the linked-property selector."""
    rendered = []
    for value, label in options:
        chosen = " selected" if value == selected else ""
        rendered.append(f'<option value="{value}"{chosen}>{label}</option>')
    return (
        "<html><body><form name='seleccionAbonado'>"
        '<select name="idAbonado" id="idAbonado" class="form-control">'
        f"{''.join(rendered)}</select>"
        "</form></body></html>"
    )


def install_account_mocks(
    mock_resp: aioresponses,
    options: list[tuple[str, str]],
    selected: str | None = None,
    apply_switch: bool = True,
    switch_hook: Any = None,
) -> dict[str, Any]:
    """Mock the preload page and the property-switch POST.

    The preload page reports the property switched by the last POST, like
    the portal does. With ``apply_switch=False`` the mocked portal answers
    the POST but keeps the page unchanged. ``switch_hook`` is awaited with
    the switch count before the page is updated. Returns a state dict with
    the recorded switches.
    """
    state: dict[str, Any] = {
        "selected": selected,
        "apply_switch": apply_switch,
        "switches": [],
    }

    def preload_callback(url, **kwargs):
        return CallbackResult(
            status=200,
            body=account_page(options, state["selected"]),
            content_type="text/html; charset=UTF-8",
        )

    async def switch_callback(url, **kwargs):
        data = dict(kwargs.get("data") or {})
        state["switches"].append({"url": str(url), "data": data})
        if switch_hook is not None:
            await switch_hook(len(state["switches"]))
        if state["apply_switch"]:
            state["selected"] = data.get("idAbonado")
        return CallbackResult(
            status=200,
            body="<html><body>OK</body></html>",
            content_type="text/html; charset=UTF-8",
        )

    # Registered before mock_login_success(), so this preload page wins.
    mock_resp.get(PRELOAD_PATTERN, callback=preload_callback, repeat=True)
    mock_resp.post(SWITCH_PATTERN, callback=switch_callback, repeat=True)
    return state


# --- list_accounts ---


async def test_list_accounts_one_property(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """A login with one linked property lists exactly one account."""
    install_account_mocks(mock_responses, [(ACCOUNT_A, LABEL_A)])

    accounts = await ista_api_client.list_accounts()

    assert accounts == [PortalAccount(account_id=ACCOUNT_A, label=LABEL_A)]


async def test_list_accounts_two_properties(
    ista_main_client: PyCalistaIsta, mock_responses: aioresponses
):
    """Two linked properties are listed in portal order."""
    install_account_mocks(mock_responses, [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)])

    accounts = await ista_main_client.list_accounts()

    assert [account.account_id for account in accounts] == [ACCOUNT_A, ACCOUNT_B]
    assert [account.label for account in accounts] == [LABEL_A, LABEL_B]


# --- select_account ---


async def test_select_account_unknown_id_raises_without_switch(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """An ID that is not linked raises IstaApiError and posts nothing."""
    state = install_account_mocks(
        mock_responses, [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)]
    )

    with pytest.raises(IstaApiError):
        await ista_api_client.select_account("0000000000000000")

    assert state["switches"] == []
    assert ista_api_client.account_id is None


async def test_select_account_sends_browser_compatible_request(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """The switch POST matches the browser: query parameters and idAbonado."""
    state = install_account_mocks(
        mock_responses, [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)]
    )

    await ista_api_client.select_account(ACCOUNT_B)

    assert len(state["switches"]) == 1
    switch = state["switches"][0]
    assert switch["data"] == {"idAbonado": ACCOUNT_B}
    query = switch["url"].split("?", 1)[1]
    assert "metodo=cambioAbonado" in query
    assert f"param={ACCOUNT_B}" in query
    assert "metodoDestino=preCargaLecturasRadio" in query
    assert ista_api_client.account_id == ACCOUNT_B


async def test_select_account_failed_verification_raises(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """A portal that keeps another property selected is rejected."""
    # The POST is accepted but the preload page still shows ACCOUNT_A.
    install_account_mocks(
        mock_responses,
        [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)],
        selected=ACCOUNT_A,
        apply_switch=False,
    )

    with pytest.raises(IstaApiError):
        await ista_api_client.select_account(ACCOUNT_B)

    assert ista_api_client.account_id is None


async def test_select_account_without_selected_option_raises(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """Two linked properties and no selected attribute are a failure."""
    state = install_account_mocks(
        mock_responses,
        [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)],
        apply_switch=False,
    )

    with pytest.raises(IstaApiError):
        await ista_api_client.select_account(ACCOUNT_B)

    assert len(state["switches"]) == 1
    assert ista_api_client.account_id is None


async def test_select_account_never_guesses_between_properties(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """The HTML default option is not accepted when two properties exist.

    Here the first usable option is the requested one, so a careless default
    check would accept it. The library must not guess between properties.
    """
    state = install_account_mocks(
        mock_responses,
        [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)],
        apply_switch=False,
    )

    with pytest.raises(IstaApiError):
        await ista_api_client.select_account(ACCOUNT_A)

    assert len(state["switches"]) == 1
    assert ista_api_client.account_id is None


async def test_select_account_single_property_without_selected_succeeds(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """One linked property and no selected attribute is accepted.

    This is the live shape: after the switch POST the preload page has no
    selected option. With one property the HTML default is that property.
    """
    state = install_account_mocks(
        mock_responses, [(ACCOUNT_A, LABEL_A)], apply_switch=False
    )

    await ista_api_client.select_account(ACCOUNT_A)

    assert len(state["switches"]) == 1
    assert ista_api_client.account_id == ACCOUNT_A


async def test_select_account_single_property_with_separator_succeeds(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """A separator option before the only property does not break the default."""
    state = install_account_mocks(
        mock_responses,
        [("", "Seleccione un abonado"), ("----", "--------"), (ACCOUNT_A, LABEL_A)],
        apply_switch=False,
    )

    await ista_api_client.select_account(ACCOUNT_A)

    assert len(state["switches"]) == 1
    assert ista_api_client.account_id == ACCOUNT_A


async def test_facade_select_account_maps_errors(
    ista_main_client: PyCalistaIsta, mock_responses: aioresponses
):
    """The facade propagates IstaApiError for an unknown property."""
    install_account_mocks(mock_responses, [(ACCOUNT_A, LABEL_A)])

    with pytest.raises(IstaApiError):
        await ista_main_client.select_account(ACCOUNT_B)


# --- login and relogin ---


async def test_login_selects_configured_account(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """login(account_id=...) selects and verifies the property."""
    state = install_account_mocks(
        mock_responses, [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)]
    )
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session,
        account_id=ACCOUNT_B,
    )

    assert await client.login() is True

    assert client.account_id == ACCOUNT_B
    assert len(state["switches"]) == 1
    assert state["switches"][0]["data"] == {"idAbonado": ACCOUNT_B}
    # Session ownership is unchanged: an injected session stays open.
    assert not mock_aiohttp_session.closed


async def test_login_without_account_id_selects_nothing(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """The default one-property behavior sends no switch request."""
    state = install_account_mocks(mock_responses, [(ACCOUNT_A, LABEL_A)])
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL, password=TEST_PASSWORD, session=mock_aiohttp_session
    )

    assert await client.login() is True

    assert client.account_id is None
    assert state["switches"] == []


async def test_relogin_reselects_the_property(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """A relogin selects the configured property again."""
    state = install_account_mocks(
        mock_responses, [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)]
    )
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session,
        account_id=ACCOUNT_B,
    )
    assert await client.login() is True
    assert len(state["switches"]) == 1

    assert await client._virtual_api.relogin() is True

    assert len(state["switches"]) == 2
    assert client.account_id == ACCOUNT_B


async def test_login_single_property_without_selected_succeeds(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """The live single-property login path verifies by the HTML default."""
    state = install_account_mocks(
        mock_responses, [(ACCOUNT_A, LABEL_A)], apply_switch=False
    )
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session,
        account_id=ACCOUNT_A,
    )

    assert await client.login() is True

    assert len(state["switches"]) == 1
    assert client.account_id == ACCOUNT_A


async def test_login_fails_when_property_is_no_longer_linked(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """A configured property removed from the login blocks the login."""
    install_account_mocks(mock_responses, [(ACCOUNT_A, LABEL_A)])
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session,
        account_id=ACCOUNT_B,
    )

    with pytest.raises(IstaApiError):
        await client.login()

    assert client.account_id is None


async def test_failed_reselection_clears_the_reported_property(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """After a failed reselection, account_id reports None, not a stale ID."""
    state = install_account_mocks(
        mock_responses, [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)]
    )
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session,
        account_id=ACCOUNT_B,
    )
    assert await client.login() is True
    assert client.account_id == ACCOUNT_B

    # The portal now keeps another property selected and ignores the switch.
    state["apply_switch"] = False
    state["selected"] = ACCOUNT_A

    with pytest.raises(IstaApiError):
        await client._virtual_api.relogin()

    assert client.account_id is None


async def test_logout_clears_the_reported_property(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """A logged-out client must not report a selected property."""
    install_account_mocks(mock_responses, [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)])
    mock_login_success(mock_responses)
    mock_responses.get(
        re.compile(
            re.escape("https://oficina.ista.es/GesCon/")
            + r"GestionOficinaVirtual\.do.*"
        ),
        status=200,
        body="<html>bye</html>",
    )
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session,
        account_id=ACCOUNT_B,
    )
    assert await client.login() is True
    assert client.account_id == ACCOUNT_B

    await client._virtual_api.logout()

    assert client.account_id is None


async def test_concurrent_login_does_not_skip_its_own_selection(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """A login in another task still selects and verifies the property.

    One task holds the property-selection lock; a second task logs in. The
    second login must not skip its own selection because of the first task.
    """
    in_switch = asyncio.Event()
    release_switch = asyncio.Event()

    async def hold_first_switch(switch_number: int) -> None:
        # Block only the first switch, so the other task stays inside
        # select_account() while the second task logs in.
        if switch_number == 1:
            in_switch.set()
            await release_switch.wait()

    state = install_account_mocks(
        mock_responses,
        [(ACCOUNT_A, LABEL_A), (ACCOUNT_B, LABEL_B)],
        switch_hook=hold_first_switch,
    )
    mock_login_success(mock_responses)
    client = PyCalistaIsta(
        email=TEST_EMAIL,
        password=TEST_PASSWORD,
        session=mock_aiohttp_session,
        account_id=ACCOUNT_B,
    )

    first = asyncio.create_task(client.select_account(ACCOUNT_B))
    await asyncio.wait_for(in_switch.wait(), timeout=5)
    second = asyncio.create_task(client.login())
    await asyncio.sleep(0.05)
    release_switch.set()
    await asyncio.wait_for(asyncio.gather(first, second), timeout=10)

    assert len(state["switches"]) == 2
    assert client.account_id == ACCOUNT_B
