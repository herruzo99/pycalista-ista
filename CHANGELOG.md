# Changelog

All notable changes to this project will be documented in this file.

## [0.10.1] - 2026-11-25

### Fixed
- **Billed consumption with a decimal comma**: the export is served in Spanish locale, so `8,5` and `1.234,56` now parse instead of raising and dropping the row. `1,234.5` is read the other way round, by the separator that comes last.
- **Empty cells are not zeros**: a blank or NaN reading drops the row instead of storing a made-up reading.
- **Missing consumption on an incidence row**: when both readings are present but `consumo` is empty, it is derived instead of losing the billed reading.

Both come from the fork maintained by @macanakin (github.com/macanakin/ista-calista, MIT), which hit the same two edge cases in the live export.

## [0.10.0] - 2026-11-24

### Added
- **Linked-property discovery and selection (EXPERIMENTAL)**: `PyCalistaIsta.list_accounts()` returns the properties linked to a login as `PortalAccount(account_id, label)` objects, and `PyCalistaIsta.select_account(account_id)` switches to one of them with the same request as the portal selector. The opaque IDs make sense only in the current session. Separator options are ignored and repeated IDs are deduplicated. An unknown ID raises `IstaApiError`, and the selection is verified on the read-only radio preload page before it is accepted.
- **Selection verification**: an explicit `selected` option must match the requested property. When the portal page has no `selected` option (the live single-property page after a switch), the HTML default applies: the browser selects the first usable option. The library accepts that default only when the login has exactly one linked property, so it never guesses between properties.
- **Selection state is truthful**: `account_id` reports a property only after verification. It is cleared before every authentication, at the start of every `select_account()` call, and by `logout()` and `close()`, so a caller never reads a property that the session may no longer use.
- **Property selection at login**: `PyCalistaIsta(email, password, session=None, account_id=...)` selects and verifies the property after authentication, including after an automatic relogin. `PyCalistaIsta.account_id` reports the selected ID.
- **Experimental status**: multi-property support was validated with one live property only. An account with two or more linked properties is not yet validated against the live portal.
- **Complete invoice pagination**: `get_invoices()` now follows the invoice-list paging anchors and returns the invoices of every page, deduplicated by `invoice_id`. It stops on a repeated page URL and reads at most 50 pages. `InvoiceParser.next_page_url(html, current_url)` exposes the paging logic.

### Fixed
- **Login error mapping**: a documented `IstaApiError` from `login()` keeps its type and message. The facade no longer re-wraps it as an unexpected error.

### Security
- **Credential-safe logging**: `DEBUG` and `ERROR` logs no longer contain the login password, cookie values, opaque property IDs, property labels, or one-time Keycloak tokens. Every request URL, error-path URL, export URL, form body, response snippet, and the text of raised connection errors is masked. Sensitive query values are also masked inside arbitrary HTML, including HTML-escaped `&amp;` separators. Pages that contain the linked-property selector are not logged at all. Only cookie names are logged.

## [0.9.3] - 2026-11-24

### Fixed
- **Billed consumption after portal column rename**: around October 2026 the ista portal renamed the billed-consumption columns `lectura anterior` and `lectura actual` to `lectura anterior facturada` and `lectura facturada`, which made `ConsumptionParser` raise `IstaParserError: Billed consumption file missing required columns` and stopped the billed sensors from updating (ista-calista#4). Both spellings are now accepted; the new names are mapped onto the old ones only when the old ones are absent, so accounts that still receive the old export keep working.

### Changed
- **Version reporting**: `pycalista_ista.__version__` still reported 0.9.1 after the 0.9.2 release. It now matches the packaged version.

## [0.9.1] - 2026-03-26

### Fixed
- **Relogin Robustness**: Improved re-authentication logic by explicitly clearing session-scoped Keycloak and portal cookies before login attempts. This prevents "Unknown Keycloak error" failures in long-lived client sessions (e.g., Home Assistant).

## [0.9.0] - 2026-03-19

### Added
- **Keycloak OAuth2 Authentication**: Rewrote the login flow to support ISTA's new Keycloak-based security infrastructure.
- **Automatic Relogin**: Improved session management to automatically re-authenticate when the portal session expires.
- **Internal Host Redirect Handling**: Added logic to catch and handle misconfigured internal redirects from the portal, ensuring seamless session recovery.
- **Relogin Verification Script**: Added `scripts/verify_relogin.py` to demonstrate and verify the automatic re-authentication behavior.

### Changed
- **Header Mimicry**: Updated request headers to more accurately mimic modern browser behavior (Origin, Referer, User-Agent).
- **Error Extraction**: Centralized and improved Keycloak error parsing for better diagnostic feedback.

### Fixed
- **Cookie Handling**: Fixed issues with quoted cookies from Keycloak that caused authentication failures.
- **Type Safety**: Addressed BeautifulSoup `PageElement` attribute errors during export link parsing.

## [0.8.0] - 2026-03-08

### Added
- **Billed Consumption Support**: Added ability to retrieve billed readings and parse invoice information from the portal.
- **Invoice Parsing**: New parsers for HTML invoice listings and detailed Excel exports.
- **Models**: Added `BilledReading` and `Invoice` models.
- **Example Script**: Added `example.py` as a comprehensive usage example and smoke test.

### Changed
- **Dependencies**: Added `openpyxl` and `beautifulsoup4` for enhanced data extraction.
- **Python Support**: Added metadata for Python 3.13 and 3.14.

### Fixed
- **Ignore Rules**: Fixed typo in `.gitignore` for example script helpers.

## [0.7.0] - 2025-12-10

### Added
- **Logout Functionality**: Added a `logout` method to `VirtualApi` to cleanly close the session.
- **Automatic Logout**: `get_devices_history` now automatically calls `logout` after data retrieval.
- **Robust Binary Handling**: Added logic to handle Excel files returned with incorrect `Content-Type` headers or as OLE2 binary files, preventing `UnicodeDecodeError`.

### Changed
- **Login Validation**: Updated `login` to explicitly treat HTTP 302 as failure and HTTP 200 as success.
- **Session Management**: Improved session expiry checks to handle binary responses gracefully.
- **Dependencies**: Updated dependencies to support new functionality.
