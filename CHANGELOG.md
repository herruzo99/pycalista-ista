# Changelog

All notable changes to this project will be documented in this file.

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
