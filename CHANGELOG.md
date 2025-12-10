# Changelog

All notable changes to this project will be documented in this file.

## [0.7.0] - 2025-12-10

### Added
- **Logout Functionality**: Added a `logout` method to `VirtualApi` to cleanly close the session.
- **Automatic Logout**: `get_devices_history` now automatically calls `logout` after data retrieval.
- **Robust Binary Handling**: Added logic to handle Excel files returned with incorrect `Content-Type` headers or as OLE2 binary files, preventing `UnicodeDecodeError`.

### Changed
- **Login Validation**: Updated `login` to explicitly treat HTTP 302 as failure and HTTP 200 as success.
- **Session Management**: Improved session expiry checks to handle binary responses gracefully.
- **Dependencies**: Updated dependencies to support new functionality.
