"""API client for Ista Calista virtual office (Async).

This module provides an async client for interacting with the Ista Calista
virtual office web interface using aiohttp. It handles authentication,
session management, and data retrieval for utility consumption readings.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any, Final
from urllib.parse import quote

import aiohttp
from aiohttp import ClientError, ClientResponseError, ClientSession
from yarl import URL

from .account_parser import AccountParser
from .const import (
    ACCOUNT_SWITCH_URL,
    CONSUMPTION_URL,
    DATA_URL,
    DATE_FORMAT,
    INVOICE_PDF_URL,
    INVOICE_XLS_FALLBACK_URL,
    INVOICES_URL,
    KC_AUTH_URL,
    KC_CLIENT_ID,
    KC_REDIRECT_URI,
    KC_STATE,
    LOGOUT_URL,
    MAX_INVOICE_PAGES,
    USER_AGENT,
)
from .consumption_parser import ConsumptionParser
from .excel_parser import ExcelParser
from .exception_classes import (
    IstaApiError,
    IstaConnectionError,
    IstaLoginError,
    IstaParserError,
)
from .invoice_parser import InvoiceParser
from .invoice_xls_parser import InvoiceXlsParser
from .models import Device
from .models.billed_reading import BilledReading
from .models.invoice import Invoice
from .models.portal_account import PortalAccount

_LOGGER = logging.getLogger(__name__)

# Constants
MAX_RETRIES: Final = 2
RETRY_BACKOFF: Final = 2
RETRY_STATUS_CODES: Final = {408, 429, 502, 503, 504}
MAX_DAYS_PER_REQUEST: Final = 240
EXCEL_CONTENT_TYPE: Final = "application/vnd.ms-excel;charset=iso-8859-1"
REQUEST_TIMEOUT: Final = 30  # seconds

# Query and form keys whose values must never reach the logs.
# password: credentials. idAbonado/param: opaque property ID. The rest are
# one-time auth tokens of the Keycloak and portal redirects.
SENSITIVE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "idabonado",
        "param",
        "code",
        "state",
        "ticket",
        "session_code",
        "execution",
        "tab_id",
        "client_data",
    }
)
MASKED_VALUE: Final[str] = "***(hidden)"
# Marker of the linked-property selector inside a page body
ACCOUNT_SELECT_MARKER: Final[str] = "idAbonado"


def _mask_value(key: str, value: object) -> object:
    """Return a loggable value for one query/form pair."""
    if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
        return MASKED_VALUE
    return value


def _redact_mapping(data: object) -> object:
    """Return a copy of a query/form mapping with sensitive values masked."""
    if data is None:
        return None
    if isinstance(data, dict):
        return {key: _mask_value(key, value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        try:
            return [
                (_mask_value(str(key), value),) + tuple(rest)
                for key, *rest in data
            ]
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return MASKED_VALUE
    return MASKED_VALUE


def _redact_url(url: object) -> str:
    """Return a URL string with sensitive query values masked."""
    try:
        parsed = URL(str(url))
    except (TypeError, ValueError):
        return "<unparsable url>"
    if not parsed.query:
        return str(parsed)
    pairs = [
        (key, MASKED_VALUE if key.lower() in SENSITIVE_KEYS else value)
        for key, value in parsed.query.items()
    ]
    return str(parsed.with_query(pairs))


def _cookie_names(session: ClientSession, url: object) -> list[str]:
    """Return the sorted cookie names sent to a URL (never the values)."""
    try:
        filtered = session.cookie_jar.filter_cookies(URL(str(url)))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return []
    return sorted(cookie.key for cookie in filtered.values())


def _redact_response_snippet(text: str) -> str:
    """Return a short loggable response snippet without property data.

    Any authenticated page carries the linked-property selector, whose
    options hold opaque property IDs and labels. Such pages are not logged.
    """
    if ACCOUNT_SELECT_MARKER in text:
        return "<page with linked-property selector omitted>"
    return text[:250].replace("\n", "")


def _normalize_page_url(url: object) -> str:
    """Return a comparable form of a page URL (sorted query parameters)."""
    try:
        parsed = URL(str(url))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(url)
    if not parsed.query:
        return str(parsed)
    return str(parsed.with_query(sorted(parsed.query.items())))


class VirtualApi:
    """Async client for the Ista Calista virtual office API.

    Handles interactions with the Ista Calista web interface using aiohttp.

    Attributes:
        username: The username for authentication.
        password: The password for authentication.
        session: The aiohttp ClientSession for making HTTP requests.
        _close_session: Flag indicating if the session was created internally.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: ClientSession | None = None,
        account_id: str | None = None,
    ) -> None:
        """Initialize the async API client.

        Args:
            username: The username for authentication.
            password: The password for authentication.
            session: An optional external aiohttp ClientSession.
                     If None, a new session is created internally.
            account_id: Optional opaque ID of the linked property to select
                     after every successful authentication.
        """
        self.username: str = username
        self.password: str = password
        self._close_session: bool = session is None

        self.session: ClientSession = session or aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        )
        self._login_lock = asyncio.Lock()  # Prevent concurrent login attempts
        # Per-client lock: property selection must not race on one cookie jar.
        self._account_lock = asyncio.Lock()
        self._account_id: str | None = account_id
        # True while select_account() runs, to stop login() from recursing
        # into another selection after a relogin.
        self._selecting_account: bool = False

    @property
    def account_id(self) -> str | None:
        """The opaque ID of the selected linked property, or None."""
        return self._account_id

    async def close(self) -> None:
        """Close the underlying aiohttp session if created internally."""
        if self._close_session and self.session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self) -> "VirtualApi":
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        await self.close()

    def _strip_quoted_cookies(self) -> None:
        """Strip quotes from cookies in the jar.

        Keycloak session cookies (like KC_AUTH_SESSION_HASH) sometimes arrive with
        literal quotes. aiohttp might send them back quoted, which is rejected by
        Keycloak. This method ensures all cookies in the jar are unquoted.
        """
        for cookie in self.session.cookie_jar:
            if cookie.value.startswith('"') and cookie.value.endswith('"'):
                cookie.set(cookie.key, cookie.value[1:-1], cookie.value[1:-1])

    async def _send_request(
        self,
        method: str,
        url: str | URL,
        retry_attempts: int = MAX_RETRIES,
        relogin: bool = True,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Send an HTTP request with the session, including retry logic.

        Args:
            method: The HTTP method (e.g., "GET", "POST").
            url: The URL to send the request to.
            retry_attempts: Number of retry attempts left.
            **kwargs: Additional arguments for session.request().

        Returns:
            The aiohttp ClientResponse.

        Raises:
            IstaConnectionError: If the request fails after retries.
            IstaLoginError: If a request fails due to expired session after relogin attempt.
        """
        _LOGGER.debug(
            "Sending request: Method=%s, URL=%s, Retries left=%d, Params/Data=%s, Cookies=%s",
            method,
            _redact_url(url),
            retry_attempts,
            _redact_mapping(kwargs.get("params") or kwargs.get("data")),
            _cookie_names(self.session, url),
        )

        if self.session is None or self.session.closed:
            _LOGGER.error("Cannot send request, session is closed.")
            raise IstaConnectionError("Session is closed")

        try:
            response = await self.session.request(method, url, **kwargs)
            # Read body once; reused for logging and session-expiry detection.
            response_text: str = ""
            try:
                response_text = await response.text()
                response_text_snippet = _redact_response_snippet(response_text)
            except UnicodeDecodeError:
                response_text_snippet = "<binary content>"
                _LOGGER.debug(
                    "Response content is binary, skipping session expiry check."
                )

            _LOGGER.debug(
                "Received response: Status=%s, Content-Type=%s, URL=%s, Snippet=%s",
                response.status,
                response.headers.get("Content-Type"),
                response.url,
                response_text_snippet,
            )

            # Check for potential session expiry:
            #  - The final URL lands on login.ista.com (cross-domain redirect
            #    followed automatically by aiohttp).
            session_expired = False
            if response.status == 200:
                final_host = str(response.url.host)
                if final_host == URL(KC_AUTH_URL).host:
                    # We landed on the Keycloak login page – session expired.
                    session_expired = True

            if session_expired and relogin:
                _LOGGER.info(
                    "Request to %s returned a login page. Session may have expired. Attempting relogin.",
                    url,
                )
                if await self.relogin():  # Attempt relogin
                    # Retry through _send_request with relogin disabled to prevent
                    # infinite recursion while still getting full response validation.
                    _LOGGER.debug(
                        "Relogin successful, retrying original request to %s", url
                    )
                    return await self._send_request(
                        method, url, retry_attempts, relogin=False, **kwargs
                    )
                else:
                    # Relogin failed, raise specific error
                    _LOGGER.error("Relogin failed. Unable to complete request.")
                    raise IstaLoginError("Relogin failed, cannot complete request.")

            # Raise exception for non-success status codes after potential relogin
            response.raise_for_status()
            return response

        except ClientResponseError as err:
            if err.status in RETRY_STATUS_CODES and retry_attempts > 0:
                wait_time = RETRY_BACKOFF * (MAX_RETRIES - retry_attempts + 1)
                _LOGGER.warning(
                    "Request failed with recoverable status %s, retrying in %ds... (%d attempts left)",
                    err.status,
                    wait_time,
                    retry_attempts,
                )
                await asyncio.sleep(wait_time)
                # Decrement retry counter for the recursive call
                return await self._send_request(
                    method, url, retry_attempts - 1, relogin=relogin, **kwargs
                )
            _LOGGER.error(
                "Request failed with unrecoverable status %s for URL %s: %s",
                err.status,
                url,
                err.message,
            )
            raise IstaConnectionError(
                f"Request failed: {err.status} {err.message}"
            ) from err
        except (ClientError, asyncio.TimeoutError) as err:
            # Special case: catch DNS errors for internal ISTA hosts.
            # The portal incorrectly redirects to internal hostnames (e.g. gescon.ista.net)
            # when the session expires, causing a ClientConnectorDNSError.
            if relogin and "gescon.ista.net" in str(err):
                _LOGGER.warning(
                    "Detected redirect to internal ISTA host (session likely expired). Attempting relogin."
                )
                try:
                    await self.relogin()
                    # Retry the original request after relogin
                    return await self._send_request(
                        method, url, retry_attempts, relogin=False, **kwargs
                    )
                except Exception as relogin_err:
                    _LOGGER.error(
                        "Relogin failed after internal host redirect: %s", relogin_err
                    )
                    raise IstaLoginError(
                        f"Session expired and relogin failed: {relogin_err}"
                    ) from relogin_err

            if retry_attempts > 0:
                wait_time = (MAX_RETRIES - retry_attempts + 1) * 2
                _LOGGER.warning(
                    "Request failed with %s, retrying in %ds... (%d attempts left)",
                    type(err).__name__,
                    wait_time,
                    retry_attempts,
                )
                await asyncio.sleep(wait_time)
                return await self._send_request(
                    method, url, retry_attempts - 1, relogin=relogin, **kwargs
                )
            _LOGGER.error(
                "Request to %s failed after all retries due to %s: %s",
                url,
                type(err).__name__,
                err,
            )
            raise IstaConnectionError(f"Request failed after retries: {err}") from err

    async def relogin(self) -> bool:
        """Perform a fresh login, clearing old session state if necessary.

        Returns:
            True if login was successful, False otherwise.
        """
        _LOGGER.info("Attempting relogin for user %s", self.username)
        # Clear cookies specific to these domains to prevent stale session errors
        # during the Keycloak OAuth2 flow in long-lived client sessions.
        self.session.cookie_jar.clear_domain("oficina.ista.es")
        self.session.cookie_jar.clear_domain("login.ista.com")
        self.session.cookie_jar.clear_domain("acceso.ista.es")
        
        return await self.login()

    @staticmethod
    def _parse_kc_form_action(html: str) -> tuple[str | None, dict[str, str]]:
        """Extract the Keycloak login form ``action`` URL from HTML.

        Keycloak renders a standard HTML ``<form method="post" action="...">``
        that contains a one-time ``session_code``, ``execution``, and
        ``client_data`` embedded in the action URL.  We must POST credentials
        to that exact URL so Keycloak can tie the submission to the pending
        auth session.

        Args:
            html: Raw HTML of the Keycloak login page.

        Returns:
            A tuple of (action_url, form_inputs). action_url is None if no
            <form> with method="post" is found.
        """

        class _FormActionParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.action: str | None = None
                self.inputs: dict[str, str] = {}
                self._current_tag: str | None = None
                self._current_name: str | None = None

            def handle_starttag(
                self, tag: str, attrs: list[tuple[str, str | None]]
            ) -> None:
                attr_dict = dict(attrs)
                if tag == "form" and self.action is None:
                    method = (attr_dict.get("method") or "").lower()
                    if method == "post":
                        self.action = attr_dict.get("action") or ""
                elif tag in ("input", "button", "select"):
                    name = attr_dict.get("name")
                    value = attr_dict.get("value") or ""
                    if name:
                        self.inputs[name] = value
                        self._current_tag = tag
                        self._current_name = name

            def handle_data(self, data: str) -> None:
                # Some buttons use the label as the value if value is missing
                if self._current_tag == "button" and self._current_name:
                    if not self.inputs.get(self._current_name):
                        self.inputs[self._current_name] = data.strip()

            def handle_endtag(self, tag: str) -> None:
                self._current_tag = None
                self._current_name = None

        parser = _FormActionParser()
        parser.feed(html)
        return parser.action, parser.inputs

    async def _discover_kc_form(self) -> tuple[str, str, dict[str, str]]:
        """Perform the Keycloak OIDC discovery step.

        Sends a GET to the Keycloak authorization endpoint with the portal's
        OAuth2 parameters.  Keycloak responds with a login HTML page whose
        ``<form action="...">`` contains a session-scoped, one-time-use URL
        (embedding ``session_code``, ``execution``, ``client_data``, etc.).

        Returns:
            A tuple of (referer_url, action_url, form_inputs).

        Raises:
            IstaLoginError: If the response is not 200 or the form action
                cannot be extracted from the HTML.
            IstaConnectionError: If the network request fails.
        """
        params = {
            "client_id": KC_CLIENT_ID,
            "response_type": "code",
            "scope": "openid",
            "redirect_uri": KC_REDIRECT_URI,
            "state": KC_STATE,
            "prompt": "login",
            "max_age": "0",
        }
        _LOGGER.debug("Discovering Keycloak login form from %s", KC_AUTH_URL)
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es,en;q=0.5",
        }
        response = await self._send_request(
            "GET", KC_AUTH_URL, params=params, relogin=False, headers=headers
        )
        self._strip_quoted_cookies()
        if response.status != 200:
            raise IstaLoginError(
                f"Keycloak discovery returned unexpected status {response.status}"
            )
        html = await response.text()
        action, inputs = self._parse_kc_form_action(html)
        if not action:
            raise IstaLoginError(
                "Could not find Keycloak login form action URL in discovery response"
            )
        _LOGGER.debug(
            "Keycloak form action URL discovered on host %s (Inputs: %s)",
            URL(action).host,
            sorted(inputs),
        )
        return str(response.url), action, inputs

    async def _submit_credentials(
        self, referer_url: str, action_url: str, form_inputs: dict[str, str]
    ) -> aiohttp.ClientResponse:
        """POST credentials to the Keycloak login form endpoint.

        Keycloak will validate the credentials and, on success, issue a 302
        redirect to the portal's ``redirect_uri`` carrying an ``?code=…``
        parameter.  ``aiohttp`` follows the full redirect chain automatically
        (including cross-domain hops from ``acceso.ista.es`` → ``oficina.ista.es``)
        so the returned response is the final response from
        ``oficina.ista.es``.

        On invalid credentials Keycloak returns 200 with an error page
        (no redirect), which this method detects and converts to
        ``IstaLoginError``.

        Args:
            action_url: The one-time form action URL obtained from
                :meth:`_discover_kc_form`.

        Returns:
            The final ``aiohttp.ClientResponse`` after all redirects.

        Raises:
            IstaLoginError: If Keycloak rejects the credentials.
            IstaConnectionError: If a network error occurs.
        """
        self._strip_quoted_cookies()

        # Use credentials as provided, but keep all other form-discovered inputs.
        # CRITICAL: Experience shows 'login' field should be empty even if button has a label.
        data = {
            **form_inputs,
            "username": self.username,
            "password": self.password,
            "login": "",
        }
        _LOGGER.debug(
            "Submitting credentials for %s with data: %s",
            self.username,
            list(data.keys()),
        )
        u = URL(action_url)
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "es,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Referer": referer_url,
            "Origin": f"{u.scheme}://{u.host}",
        }
        # allow_redirects=True so aiohttp follows all cross-domain hops
        response = await self._send_request(
            "POST",
            action_url,
            data=data,
            relogin=False,
            allow_redirects=True,
            headers=headers,
        )

        # On bad credentials Keycloak returns 200 with an error page
        # instead of redirecting.  Detect by final response host.
        final_host = str(response.url.host)
        kc_host = URL(KC_AUTH_URL).host
        if final_host == kc_host:
            try:
                error_body = await response.text()
                err_msg = self._extract_kc_error(error_body)

                _LOGGER.error(
                    "Login failed for %s: %s. Response snippet: %s",
                    self.username,
                    err_msg,
                    error_body[:300].replace("\n", ""),
                )
                raise IstaLoginError(f"Login failed – {err_msg}")
            except IstaLoginError:
                raise
            except Exception:
                _LOGGER.exception(
                    "Unexpected error parsing Keycloak failure for %s", self.username
                )
                raise IstaLoginError("Login failed – Keycloak rejected the credentials")

        return response

    async def login(self) -> bool:
        """Authenticate with the Ista Calista virtual office asynchronously.

        Implements the three-step Keycloak OAuth2 Authorization Code flow:

        1. **Discover** – GET the Keycloak OIDC auth endpoint to obtain a
           one-time login form action URL (step supplies ``session_code``,
           ``execution``, ``client_data``, etc.).
        2. **Submit** – POST credentials to that action URL.  Keycloak
           issues a 302 that ``aiohttp`` follows through
           ``acceso.ista.es/auth/callback/abonado`` → ``AuthHandler.do``
           → ``GestionOficinaVirtual.do``, accumulating cookies along the
           way so ``oficina.ista.es`` recognises the session.
        3. **Preload** – GET the reading-metadata endpoint to finish
           session initialisation.
        4. **Select property** – when an ``account_id`` was configured and
           this login is not itself part of a selection, reselect and
           verify that linked property.

        Uses a per-client lock to prevent concurrent login attempts. The
        property selection runs after that lock is released, so the login
        lock and the account lock are never held at the same time.

        Returns:
            True if login was successful.

        Raises:
            IstaLoginError: If Keycloak rejects the credentials or the
                flow cannot be completed.
            IstaConnectionError: If a network request fails.
            IstaApiError: If the configured property can no longer be
                selected or verified.
        """
        async with self._login_lock:
            _LOGGER.info("Attempting Keycloak OAuth2 login for user: %s", self.username)
            try:
                # Step 1 – obtain one-time form action URL and hidden inputs from Keycloak.
                referer_url, action_url, form_inputs = await self._discover_kc_form()

                # Step 2 – submit credentials; follow full redirect chain.
                await self._submit_credentials(referer_url, action_url, form_inputs)

                _LOGGER.info(
                    "Keycloak login successful for %s; session established.",
                    self.username,
                )

                # Step 3 – preload metadata required for later data requests.
                await self._preload_reading_metadata()

            except IstaConnectionError as err:
                _LOGGER.error(
                    "Connection error during login for %s: %s", self.username, err
                )
                raise
            except IstaLoginError:  # Re-raise specific login errors
                raise
            except Exception:
                _LOGGER.exception(
                    "An unexpected error occurred during login for %s", self.username
                )
                raise

        # Step 4 – restore the configured property selection. A login started
        # from inside select_account() (relogin) skips it: that caller verifies
        # the selection itself.
        if self._account_id is not None and not self._selecting_account:
            await self.select_account(self._account_id)

        return True

    async def logout(self) -> None:
        """Log out from the Ista Calista virtual office asynchronously."""
        _LOGGER.info("Logging out user: %s", self.username)
        try:
            # We expect a redirect to login page or similar, so we disable auto-relogin
            # to prevent an infinite loop or unnecessary login after logout.
            await self._send_request("GET", LOGOUT_URL, relogin=False)
            _LOGGER.info("Logout successful for %s.", self.username)
        except Exception as err:
            _LOGGER.warning("Logout failed for %s: %s", self.username, err)
            # We don't raise here as logout failure shouldn't block the main process result

    async def _fetch_radio_preload(self) -> str:
        """GET the read-only radio preload page and return its HTML.

        The page lists the linked properties and marks the selected one, so
        it is the discovery and verification page for property selection.

        Returns:
            Raw HTML of the preload page.

        Raises:
            IstaConnectionError: If the request fails.
            IstaLoginError: If session expired and relogin failed.
        """
        _LOGGER.debug("Fetching radio preload page.")
        params = {"metodo": "preCargaLecturasRadio"}
        try:
            response = await self._send_request("GET", DATA_URL, params=params)
            return await response.text()
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to fetch the radio preload page: %s", err)
            raise
        except Exception:
            _LOGGER.exception("An unexpected error occurred while preloading metadata.")
            raise

    async def _preload_reading_metadata(self) -> None:
        """Preload reading metadata required for subsequent requests (async).

        Raises:
            IstaConnectionError: If the request fails.
            IstaLoginError: If session expired and relogin failed.
        """
        _LOGGER.debug("Preloading reading metadata for Excel export.")
        await self._fetch_radio_preload()
        _LOGGER.debug("Successfully preloaded reading metadata.")

    async def list_accounts(self) -> list[PortalAccount]:
        """List the properties linked to the authenticated login.

        Uses only the read-only radio preload page. Login must already have
        happened. Separator options are ignored and repeated IDs are
        deduplicated.

        EXPERIMENTAL: multi-property support is not yet validated against an
        account with more than one linked property.

        Returns:
            List of PortalAccount objects in portal order. Empty if the page
            has no linked-property selector.

        Raises:
            IstaConnectionError: If the request fails.
            IstaLoginError: If the session expired and relogin failed.
        """
        html = await self._fetch_radio_preload()
        accounts = AccountParser().parse_accounts(html)
        _LOGGER.info("Discovered %d linked properties.", len(accounts))
        return accounts

    async def select_account(self, account_id: str) -> None:
        """Select one linked property and verify the portal applied it.

        Sends the same request as the portal selector: a POST to
        ``GestionOficinaVirtual.do`` with ``metodo=cambioAbonado`` and the
        opaque property ID, followed by a GET of the radio preload page to
        verify the selected option.

        EXPERIMENTAL: multi-property support is not yet validated against an
        account with more than one linked property.

        Args:
            account_id: Opaque property ID from :meth:`list_accounts`.

        Raises:
            IstaApiError: If the ID is not linked to this login, or if the
                portal did not apply the selection.
            IstaConnectionError: If a request fails.
            IstaLoginError: If the session expired and relogin failed.
        """
        if not account_id or not account_id.strip():
            raise IstaApiError("Account ID must be a non-empty string")

        async with self._account_lock:
            self._selecting_account = True
            try:
                await self._select_account_locked(account_id.strip())
            finally:
                self._selecting_account = False

    async def _select_account_locked(self, account_id: str) -> None:
        """Validate, switch and verify a property selection (lock held)."""
        parser = AccountParser()

        # 1. Read the linked properties from the read-only preload page.
        html = await self._fetch_radio_preload()
        known_ids = {account.account_id for account in parser.parse_accounts(html)}
        if account_id not in known_ids:
            _LOGGER.error(
                "Property selection refused: the requested account is not linked "
                "to this login (%d linked properties).",
                len(known_ids),
            )
            raise IstaApiError(
                "Unknown account ID: the property is not linked to this login"
            )

        # 2. Switch property the way the portal selector does.
        _LOGGER.debug("Sending linked-property switch request.")
        params = {
            "metodo": "cambioAbonado",
            "param": account_id,
            "metodoDestino": "preCargaLecturasRadio",
        }
        data = {"idAbonado": account_id}
        await self._send_request("POST", ACCOUNT_SWITCH_URL, params=params, data=data)

        # 3. Verify: the preload page must mark the requested option selected.
        verify_html = await self._fetch_radio_preload()
        selected_id = parser.selected_account_id(verify_html)
        if selected_id is None:
            _LOGGER.error(
                "Property selection could not be verified: no selected option found."
            )
            raise IstaApiError(
                "Account selection could not be verified: the portal page shows "
                "no selected property"
            )
        if selected_id != account_id:
            _LOGGER.error(
                "Property selection could not be verified: the portal kept a "
                "different property selected."
            )
            raise IstaApiError(
                "Account selection could not be verified: the portal kept a "
                "different property selected"
            )

        self._account_id = account_id
        _LOGGER.info("Linked-property selection verified.")

    async def _get_readings_chunk(
        self,
        start: date,
        end: date,
        max_days: int = MAX_DAYS_PER_REQUEST,
    ) -> io.BytesIO:
        """Get readings for a specific date range chunk asynchronously.

        Args:
            start: Start date for the chunk.
            end: End date for the chunk.
            max_days: Maximum number of days per request.

        Returns:
            BytesIO object containing the Excel data.

        Raises:
            ValueError: If the date range exceeds max_days.
            IstaConnectionError: If the request fails.
            IstaLoginError: If session expired and relogin failed.
            IstaApiError: For unexpected errors.
        """
        delta_days = (end - start).days
        if delta_days >= max_days:  # Use >= to be safe
            _LOGGER.error(
                "Date range (%d days) exceeds maximum of %d days.",
                delta_days,
                max_days,
            )
            raise ValueError(
                f"Date range exceeds maximum {max_days} days: {delta_days} days"
            )
        if delta_days < 0:
            _LOGGER.error("Start date (%s) is after end date (%s).", start, end)
            raise ValueError("Start date must be before end date")

        _LOGGER.debug(
            "Fetching readings chunk for date range: %s to %s",
            start.isoformat(),
            end.isoformat(),
        )

        params = {
            "d-4360165-e": "2",  # 2=xlsx format
            "fechaHastaRadio": quote(end.strftime(DATE_FORMAT)),
            "metodo": "listadoLecturasRadio",
            "fechaDesdeRadio": quote(start.strftime(DATE_FORMAT)),
            "6578706f7274": "1",  # Export flag
        }

        try:
            response = await self._send_request("GET", DATA_URL, params=params)

            content_type = response.headers.get("Content-Type", "")
            # Check if content type indicates Excel (ignoring charset details)
            if "application/vnd.ms-excel" not in content_type.lower():
                # This case is now more likely to be handled by the relogin logic
                # in _send_request, but we keep a specific check as a safeguard.
                try:
                    response_text = await response.text()
                except UnicodeDecodeError:
                    # If we can't decode it, it's likely binary (maybe the Excel file itself?)
                    # even if the content-type header was wrong.
                    # Let's log a snippet of the binary data for debugging.
                    content_bytes = await response.read()
                    _LOGGER.error(
                        "Expected Excel file but received content type '%s'. "
                        "Could not decode response text (UnicodeDecodeError). "
                        "First 100 bytes of response: %s",
                        content_type,
                        content_bytes[:100],
                    )
                    # Check for ZIP (xlsx) or OLE2 (xls) magic numbers
                    # PK.. = Zip/XLSX
                    # D0CF11E0 = OLE2/XLS
                    if content_bytes.startswith(b"PK") or content_bytes.startswith(
                        b"\xd0\xcf\x11\xe0"
                    ):
                        _LOGGER.warning(
                            "Response has valid Excel signature (PK or OLE2), assuming it is the Excel file despite Content-Type mismatch."
                        )
                        return io.BytesIO(content_bytes)

                    raise IstaApiError(
                        f"Received unexpected content type '{content_type}' and could not decode response."
                    )

                _LOGGER.error(
                    "Expected Excel file but received content type '%s'. This may indicate a session or API issue. Response snippet: %s",
                    content_type,
                    response_text[:250].replace("\n", ""),
                )
                if (
                    "text/html" in content_type
                    and "GestionOficinaVirtual.do" in response_text
                ):
                    raise IstaLoginError(
                        "Received login page instead of Excel file, session likely expired and relogin failed."
                    )
                raise IstaApiError(
                    f"Received unexpected content type '{content_type}' instead of Excel file."
                )

            # Read response content into BytesIO
            content = await response.read()
            _LOGGER.debug(
                "Successfully downloaded Excel data chunk of size %d bytes.",
                len(content),
            )
            return io.BytesIO(content)

        except (IstaConnectionError, IstaLoginError, IstaApiError) as err:
            _LOGGER.error(
                "Failed to download readings chunk from %s to %s: %s", start, end, err
            )
            raise  # Re-raise the caught exception
        except Exception:
            _LOGGER.exception(
                "An unexpected error occurred while downloading readings chunk from %s to %s",
                start,
                end,
            )
            raise

    async def _get_readings(
        self,
        start: date,
        end: date,
        max_days: int = MAX_DAYS_PER_REQUEST,
    ) -> list[tuple[int, io.BytesIO]]:
        """Get all readings within a date range, splitting into chunks asynchronously.

        Args:
            start: Start date for readings.
            end: End date for readings.
            max_days: Maximum days per chunk request.

        Returns:
            List of tuples containing (year, file_buffer) for each chunk.

        Raises:
            ValueError: If start date is after end date.
            IstaConnectionError: If any chunk request fails.
            IstaLoginError: If session expired and relogin failed.
            IstaApiError: For unexpected errors.
        """
        if start > end:
            raise ValueError("Start date must be before or equal to end date")

        file_buffers: list[tuple[int, io.BytesIO]] = []
        current_start = start

        _LOGGER.debug(
            "Starting to fetch all readings from %s to %s in chunks of max %d days.",
            start.isoformat(),
            end.isoformat(),
            max_days,
        )

        while current_start <= end:
            current_end = min(current_start + timedelta(days=max_days - 1), end)

            _LOGGER.info(
                "Requesting data chunk for period: %s to %s",
                current_start.isoformat(),
                current_end.isoformat(),
            )

            try:
                # Fetch the chunk asynchronously
                file_buffer = await self._get_readings_chunk(current_start, current_end)
                # Store the buffer along with the *end* year for the parser context
                file_buffers.append((current_end.year, file_buffer))
            except (
                IstaConnectionError,
                IstaLoginError,
                IstaApiError,
                ValueError,
            ) as err:
                _LOGGER.error(
                    "Aborting history fetch. Failed to get readings for chunk %s to %s: %s",
                    current_start.isoformat(),
                    current_end.isoformat(),
                    err,
                )
                raise  # Propagate the error to stop the process

            # Move to the next day after the current chunk's end date
            current_start = current_end + timedelta(days=1)

        _LOGGER.info("Successfully retrieved %d data chunk(s).", len(file_buffers))
        return file_buffers

    async def get_devices_history(
        self,
        start: date,
        end: date,
    ) -> dict[str, Device]:
        """Get historical consumption data for all devices asynchronously.

        Args:
            start: Start date for the history period.
            end: End date for the history period.

        Returns:
            Dictionary mapping device serial numbers to device objects with history.

        Raises:
            ValueError: If start date is after end date.
            IstaConnectionError: If data retrieval fails.
            IstaLoginError: If session expired and relogin failed.
            IstaParserError: If Excel parsing fails.
            IstaApiError: For unexpected errors.
        """
        _LOGGER.info(
            "Getting full device history from %s to %s",
            start.isoformat(),
            end.isoformat(),
        )
        if start > end:
            raise ValueError("Start date must be before end date")

        try:
            # Get list of (year, file_buffer) tuples asynchronously
            current_year_file_buffers = await self._get_readings(start, end)

            if not current_year_file_buffers:
                _LOGGER.warning(
                    "No data files were retrieved from Ista for the period %s to %s. This can be normal if there are no new readings.",
                    start.isoformat(),
                    end.isoformat(),
                )
                return {}  # Return empty dict if no files were fetched

            device_lists: list[dict[str, Device]] = []
            loop = asyncio.get_running_loop()

            # Process parsing in executor as pandas/xlrd are synchronous
            _LOGGER.debug(
                "Creating %d parsing tasks to run in executor.",
                len(current_year_file_buffers),
            )
            tasks = []
            for current_year, file_buffer in current_year_file_buffers:
                parser = ExcelParser(file_buffer, current_year)
                # Run synchronous parser in executor thread
                tasks.append(loop.run_in_executor(None, parser.get_devices_history))

            # Wait for all parsing tasks to complete
            parsed_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for parsing errors
            for i, result in enumerate(parsed_results):
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "An error occurred during the parsing of an Excel file (chunk %d).",
                        i + 1,
                        exc_info=result,
                    )
                    # Raise the first encountered parser error
                    raise IstaParserError(
                        "Failed to parse one or more Excel files"
                    ) from result
                if isinstance(result, dict):
                    device_lists.append(result)
                else:
                    _LOGGER.error(
                        "Unexpected result of type '%s' returned from parser task.",
                        type(result),
                    )
                    raise IstaParserError("Unexpected result during parsing.")

            _LOGGER.debug(
                "All %d parsing tasks completed. Proceeding to merge results.",
                len(parsed_results),
            )
            # Merge the results from different files/chunks
            merged_devices = self.merge_device_histories(device_lists)
            _LOGGER.info(
                "Successfully merged history, resulting in %d unique devices.",
                len(merged_devices),
            )
            return merged_devices

        except (
            IstaConnectionError,
            IstaLoginError,
            IstaParserError,
            IstaApiError,
            ValueError,
        ) as err:
            _LOGGER.error(
                "Failed to get complete device history: %s", err, exc_info=True
            )
            raise  # Re-raise the specific error
        except Exception:
            _LOGGER.exception("An unexpected error occurred in get_devices_history.")
            raise

    def merge_device_histories(
        self, device_lists: list[dict[str, Device]]
    ) -> dict[str, Device]:
        """Merge device histories from multiple time periods.

        This method combines historical readings from different time periods
        into a single consolidated history for each device. It also handles
        interpolation for missing readings.

        Args:
            device_lists: List of dictionaries containing device histories.

        Returns:
            Dictionary with merged and interpolated device histories.
        """
        merged_devices: dict[str, Device] = {}
        _LOGGER.debug("Merging %d list(s) of parsed devices.", len(device_lists))

        for i, device_list in enumerate(device_lists):
            _LOGGER.debug(
                "Processing device list #%d with %d devices.", i + 1, len(device_list)
            )
            for serial_number, device in device_list.items():
                if not isinstance(device, Device):
                    _LOGGER.warning(
                        "Skipping invalid item in device list (not a Device object): %s",
                        device,
                    )
                    continue

                if serial_number not in merged_devices:
                    # Create a new instance of the correct device type
                    _LOGGER.debug(
                        "Discovered new device SN %s. Creating entry in merged list.",
                        serial_number,
                    )
                    merged_devices[serial_number] = device.__class__(
                        serial_number=device.serial_number, location=device.location
                    )

                existing_device = merged_devices[serial_number]
                # Add readings, ensuring no duplicates based on date
                existing_dates = {r.date for r in existing_device.history}
                new_readings_count = 0
                for reading in device.history:
                    if reading.date not in existing_dates:
                        existing_device.add_reading(reading)
                        existing_dates.add(reading.date)
                        new_readings_count += 1
                if new_readings_count > 0:
                    _LOGGER.debug(
                        "Added %d new unique readings to device SN %s.",
                        new_readings_count,
                        serial_number,
                    )

        # Interpolate and trim final merged devices
        _LOGGER.debug(
            "Finished merging. Now interpolating and trimming %d devices.",
            len(merged_devices),
        )
        final_devices: dict[str, Device] = {}
        for serial_number, device in merged_devices.items():
            try:
                final_devices[serial_number] = (
                    self._interpolate_and_trim_device_reading(device)
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to interpolate readings for device %s. "
                    "Falling back to raw readings without interpolation. Error: %s",
                    serial_number,
                    e,
                    exc_info=True,
                )
                final_devices[serial_number] = device

        _LOGGER.debug(
            "Finished merging and interpolation, resulting in %d final devices.",
            len(final_devices),
        )
        return final_devices

    def _interpolate_and_trim_device_reading(self, device: Device) -> Device:
        """Creates a new device with linear interpolation of missing readings and
        trimming of last missing readings, applying special rules.

        Args:
            device (Device): Device to fix

        Returns:
            Device: Fixed device of the same type.

        Raises:
            ValueError: If device type is unknown or interpolation fails.
        """
        _LOGGER.debug(
            "Interpolating and trimming readings for device SN %s.",
            device.serial_number,
        )
        try:
            fixed_device = device.__class__(device.serial_number, device.location)
        except TypeError as e:
            raise ValueError(
                f"Could not instantiate device class {device.__class__.__name__}"
            ) from e

        sorted_readings = sorted(device.history, key=lambda r: r.date)
        valid_readings = [
            r for r in sorted_readings if r.reading is not None and r.reading >= 0
        ]

        if len(valid_readings) < 2:
            _LOGGER.debug(
                "Device SN %s has fewer than 2 valid readings (%d). Skipping interpolation.",
                device.serial_number,
                len(valid_readings),
            )
            for reading in valid_readings:
                fixed_device.add_reading(reading)
            return fixed_device

        first_valid_date = valid_readings[0].date
        last_valid_date = valid_readings[-1].date
        filtered_readings = [
            r for r in sorted_readings if first_valid_date <= r.date <= last_valid_date
        ]

        valid_reading_pairs = []
        for i in range(len(valid_readings) - 1):
            valid_reading_pairs.append((valid_readings[i], valid_readings[i + 1]))

        interpolated_count = 0
        for start_reading, end_reading in valid_reading_pairs:
            if (
                not fixed_device.history
                or fixed_device.history[-1].date != start_reading.date
            ):
                fixed_device.add_reading(start_reading)

            to_interpolate = [
                r
                for r in filtered_readings
                if start_reading.date < r.date < end_reading.date
                and (r.reading is None or r.reading < 0)
            ]

            if to_interpolate:
                _LOGGER.debug(
                    "Found %d readings to interpolate for SN %s between %s and %s.",
                    len(to_interpolate),
                    device.serial_number,
                    start_reading.date.isoformat(),
                    end_reading.date.isoformat(),
                )
                start_val = start_reading.reading
                end_val = end_reading.reading

                if end_val < start_val:
                    _LOGGER.info(
                        "Detected a meter reset for device SN %s (from %.2f to %.2f). "
                        "Interpolating %d missing values as 0.",
                        device.serial_number,
                        start_val,
                        end_val,
                        len(to_interpolate),
                    )
                    for r in sorted(to_interpolate, key=lambda x: x.date):
                        fixed_device.add_reading_value(0, r.date)
                        interpolated_count += 1
                    continue  # Move to the next pair of valid readings

                start_date_ts = start_reading.date.timestamp()
                end_date_ts = end_reading.date.timestamp()

                time_span = end_date_ts - start_date_ts
                value_span = end_val - start_val

                if time_span == 0:
                    _LOGGER.warning(
                        "Cannot interpolate for SN %s, found identical timestamps for different readings: %s",
                        device.serial_number,
                        start_reading.date,
                    )
                    continue

                for r in sorted(to_interpolate, key=lambda x: x.date):
                    elapsed_time = r.date.timestamp() - start_date_ts
                    fraction = elapsed_time / time_span

                    interpolated_value = round(start_val + (value_span * fraction), 4)

                    final_value = max(start_val, min(end_val, interpolated_value))

                    fixed_device.add_reading_value(final_value, r.date)
                    interpolated_count += 1

        if (
            not fixed_device.history
            or fixed_device.history[-1].date != valid_readings[-1].date
        ):
            fixed_device.add_reading(valid_readings[-1])

        _LOGGER.debug(
            "Interpolation complete for device SN %s. Total interpolated points: %d. Final reading count: %d",
            device.serial_number,
            interpolated_count,
            len(fixed_device.history),
        )
        return fixed_device

    async def get_invoices(self) -> list[Invoice]:
        """Fetch every invoice-list page and return the deduplicated list.

        The portal paginates the HTML invoice list (15 rows per page). This
        method follows the paging anchors until the last page, stops on a
        repeated page URL (portal loop), and reads at most
        ``MAX_INVOICE_PAGES`` pages. Invoices with the same non-empty
        ``invoice_id`` appear once.

        Returns:
            List of Invoice objects parsed from all pages, in portal order.

        Raises:
            IstaConnectionError: If a request fails.
            IstaLoginError: If the session has expired and relogin failed.
            IstaParserError: If a page cannot be parsed.
        """
        _LOGGER.info("Fetching invoice list.")
        parser = InvoiceParser()
        invoices: list[Invoice] = []
        seen_ids: set[str] = set()
        visited: set[str] = set()
        url: str | URL = INVOICES_URL
        params: dict[str, str] | None = {"metodo": "buscarRecibos"}
        pages = 0

        while pages < MAX_INVOICE_PAGES:
            try:
                response = await self._send_request("GET", url, params=params)
                html = await response.text()
                current_url = str(response.url)
            except (IstaConnectionError, IstaLoginError) as err:
                _LOGGER.error("Failed to fetch invoice list: %s", err)
                raise

            pages += 1
            visited.add(_normalize_page_url(current_url))

            try:
                page_invoices = parser.parse(html)
            except IstaParserError:
                _LOGGER.error("Failed to parse invoice list HTML.", exc_info=True)
                raise

            for invoice in page_invoices:
                if invoice.invoice_id:
                    if invoice.invoice_id in seen_ids:
                        continue
                    seen_ids.add(invoice.invoice_id)
                invoices.append(invoice)

            next_url = parser.next_page_url(html, current_url)
            if next_url is None:
                break
            if _normalize_page_url(next_url) in visited:
                _LOGGER.debug(
                    "Invoice pagination returned to an already read page; stopping."
                )
                break
            url = next_url
            params = None
        else:
            _LOGGER.warning(
                "Invoice list reached the maximum of %d pages; later invoices "
                "may be missing.",
                MAX_INVOICE_PAGES,
            )

        _LOGGER.info(
            "Successfully retrieved %d invoice(s) from %d page(s).",
            len(invoices),
            pages,
        )
        return invoices

    async def get_invoice_pdf(self, invoice_id: str) -> bytes:
        """Download a single invoice as a PDF.

        Args:
            invoice_id: The opaque server-side invoice ID (from Invoice.invoice_id).

        Returns:
            Raw PDF bytes.

        Raises:
            IstaConnectionError: If the request fails.
            IstaLoginError: If the session has expired and relogin failed.
            IstaApiError: If the response is not a PDF.
        """
        _LOGGER.info("Downloading PDF for invoice_id=%s.", invoice_id)
        params = {
            "metodo": "duplicarReciboIndividualCalista",
            "idRecibo": invoice_id,
        }
        try:
            response = await self._send_request("GET", INVOICE_PDF_URL, params=params)
            content_type = response.headers.get("Content-Type", "")
            content = await response.read()
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to download invoice PDF %s: %s", invoice_id, err)
            raise

        # Validate it looks like a PDF (magic bytes %PDF)
        if not content.startswith(b"%PDF") and "pdf" not in content_type.lower():
            _LOGGER.error(
                "Expected PDF for invoice_id=%s but got Content-Type=%s, first bytes=%s",
                invoice_id,
                content_type,
                content[:16],
            )
            raise IstaApiError(
                f"Expected PDF response for invoice {invoice_id}, got Content-Type: {content_type}"
            )

        _LOGGER.debug(
            "Downloaded PDF for invoice_id=%s (%d bytes).", invoice_id, len(content)
        )
        return content

    async def get_invoice_xls(self) -> list[Invoice]:
        """Fetch the full invoice history as an XLS export (Mis Recibos → Excel).

        Flow:
          1. GET the invoice listing page to establish session state.
          2. Find the Excel export link in the HTML.
          3. GET the XLS and parse it.

        Returns:
            List of Invoice objects parsed from the XLS. invoice_id is "" for all
            entries (the XLS does not include server-side IDs).

        Raises:
            IstaConnectionError: If any request fails.
            IstaLoginError: If the session has expired and relogin failed.
            IstaParserError: If the XLS cannot be parsed.
        """
        _LOGGER.info("Fetching invoice XLS export.")
        params = {"metodo": "buscarRecibos"}

        # 1. Fetch invoice listing page (establishes session state + gives us the export link)
        try:
            response = await self._send_request("GET", INVOICES_URL, params=params)
            html = await response.text()
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to fetch invoice listing page: %s", err)
            raise

        # 2. Find export link, fall back to known URL if not found
        export_url = self._find_export_url(html, url_fragment="GestionFacturacion")
        if export_url:
            _LOGGER.debug("Found invoice XLS export URL: %s", export_url)
        else:
            _LOGGER.warning(
                "Could not find invoice XLS export link in HTML; using fallback URL."
            )
            export_url = INVOICE_XLS_FALLBACK_URL

        # 3. Download and parse the XLS
        try:
            xls_response = await self._send_request("GET", export_url)
            xls_content = await xls_response.read()
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to download invoice XLS: %s", err)
            raise

        try:
            parser = InvoiceXlsParser()
            loop = asyncio.get_running_loop()
            invoices = await loop.run_in_executor(
                None, parser.parse, io.BytesIO(xls_content)
            )
        except IstaParserError:
            _LOGGER.error("Failed to parse invoice XLS.", exc_info=True)
            raise

        _LOGGER.info("Successfully retrieved %d invoice XLS row(s).", len(invoices))
        return invoices

    @staticmethod
    def _find_export_url(html: str, url_fragment: str | None = None) -> str | None:
        """Find a display-tag Excel export URL in an HTML page.

        Looks for anchor tags whose href contains the hex-encoded export flag
        ``6578706f7274`` (= "export"), optionally filtered by a substring of the
        URL (e.g. ``"GestionFacturacion"`` to target only invoice export links).
        Forces XLS format by rewriting ``d-NNNNN-e=N`` → ``d-NNNNN-e=2``.

        Args:
            html: Raw HTML from a portal page.
            url_fragment: Optional substring that the href must contain.

        Returns:
            Absolute URL string, or None if not found.
        """
        import re

        from bs4 import BeautifulSoup, Tag

        soup = BeautifulSoup(html, "html.parser")

        def _to_absolute(href: str) -> str:
            if not href.startswith("http"):
                href = f"https://oficina.ista.es/{href.lstrip('/')}"
            return re.sub(r"(d-\d+-e)=\d+", r"\1=2", href)

        for link in soup.find_all("a", href=re.compile(r"6578706f7274")):
            if isinstance(link, Tag):
                href = link.get("href", "")
                if href and (url_fragment is None or url_fragment in href):
                    return _to_absolute(str(href))

        # Fallback: any display-tag export link (only when no fragment filter)
        if url_fragment is None:
            for link in soup.find_all("a", href=re.compile(r"d-\d+-e=\d+")):
                if isinstance(link, Tag):
                    href = link.get("href", "")
                    if href:
                        return _to_absolute(str(href))

        return None

    async def get_billed_consumption(self) -> list[BilledReading]:
        """Fetch all billed consumption readings (Mis Consumos).

        Flow:
          1. GET the search page to establish session state.
          2. POST to trigger the search and receive results HTML.
          3. Parse the HTML to find the Excel export link.
          4. GET the export XLS and parse it.

        Returns:
            List of BilledReading objects, newest first.

        Raises:
            IstaConnectionError: If any request fails.
            IstaLoginError: If the session has expired and relogin failed.
            IstaParserError: If the HTML or XLS cannot be parsed.
            IstaApiError: If the export link cannot be found in the page.
        """
        _LOGGER.info("Fetching billed consumption data.")
        params = {"metodo": "buscarLecturas"}

        # 1. Preload
        try:
            await self._send_request("GET", CONSUMPTION_URL, params=params)
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to preload billed consumption page: %s", err)
            raise

        # 2. POST search
        data = {
            "metodo": "buscarLecturas",
            "idAbonado": "",
            "validacion": "true",
        }
        try:
            response = await self._send_request(
                "POST", CONSUMPTION_URL, params=params, data=data
            )
            html = await response.text()
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to fetch billed consumption search results: %s", err)
            raise

        # 3. Find the Excel export link in the HTML
        export_url = self._find_export_url(html)
        if not export_url:
            raise IstaApiError(
                "Could not find Excel export link in billed consumption page. "
                "The page structure may have changed."
            )
        _LOGGER.debug("Found billed consumption export URL: %s", export_url)

        # 4. Download and parse the XLS
        try:
            xls_response = await self._send_request("GET", export_url)
            xls_content = await xls_response.read()
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to download billed consumption XLS: %s", err)
            raise

        try:
            parser = ConsumptionParser()
            readings = parser.parse(io.BytesIO(xls_content))
        except IstaParserError:
            _LOGGER.error("Failed to parse billed consumption XLS.", exc_info=True)
            raise

        _LOGGER.info("Successfully retrieved %d billed reading(s).", len(readings))
        return readings

    @staticmethod
    def _extract_kc_error(html: str) -> str:
        """Extract a human-readable error from Keycloak's HTML response.

        Searches for common Keycloak CSS classes and IDs used for error feedback.
        """
        import re

        # Look for typical Keycloak error containers
        indicators = [
            r'class="kc-feedback-text">([^<]+)',
            r'class="alert-error">[^<]*<span[^>]*>([^<]+)',
            r'id="input-error-password">([^<]+)',
            r'id="input-error-username">([^<]+)',
            r'class="alert-error">([^<]+)',
        ]
        for pattern in indicators:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return "Unknown Keycloak error"
