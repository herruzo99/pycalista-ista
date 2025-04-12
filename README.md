# PyCalista-ista

[![PyPI version](https://badge.fury.io/py/pycalista-ista.svg)](https://badge.fury.io/py/pycalista-ista) [![Downloads](https://pepy.tech/badge/pycalista-ista)](https://pepy.tech/project/pycalista-ista)
[![GitHub issues](https://img.shields.io/github/issues/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista/issues)
[![GitHub forks](https://img.shields.io/github/forks/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista)
[![GitHub stars](https://img.shields.io/github/stars/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista)
[![GitHub license](https://img.shields.io/github/license/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista/blob/main/LICENSE)
![GitHub Release Date](https://img.shields.io/github/release-date/herruzo99/pycalista-ista?style=for-the-badge&logo=github)
[![codecov](https://codecov.io/github/herruzo99/pycalista-ista/branch/main/graph/badge.svg?token=BHU8J3OVRT)](https://codecov.io/github/herruzo99/pycalista-ista)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/9868/badge)](https://www.bestpractices.dev/projects/9868)

---

Unofficial **async** Python library for the Ista Calista service API. This library allows you to interact with your Ista Calista account to retrieve consumption data from heating and water meters using `asyncio` and `aiohttp`.

This project is based on [ecotrend-ista](https://github.com/Ludy87/ecotrend-ista) and adapted for the Calista portal and asynchronous operation.

## Features

-   **Asynchronous:** Uses `asyncio` and `aiohttp` for non-blocking I/O.
-   Login and session management with automatic cookie handling.
-   Retrieve consumption data for heating and water meters.
-   Parse Excel reports (`.xls`, `.xlsx`) from Ista Calista using `pandas` and `openpyxl`.
-   Support for different meter types (heating, hot water, cold water).
-   Automatic handling of session expiration and relogin attempts.
-   Data interpolation for missing readings.
-   Configurable retries for network requests.

## Installation

Requires Python 3.12+

```bash
pip install pycalista-ista
```

This will install the library along with its dependencies (`aiohttp`, `pandas`, `openpyxl`, `unidecode`, `yarl`).

## Usage

```python
import asyncio
from datetime import date
import aiohttp

from pycalista_ista import PyCalistaIsta, IstaLoginError, IstaConnectionError

async def main():
    # It's recommended to reuse aiohttp ClientSession
    async with aiohttp.ClientSession() as session:
        # Initialize the client, optionally passing the session
        client = PyCalistaIsta("your@email.com", "your_password", session=session)

        try:
            # Login to the service (async)
            await client.login()
            print("Login successful!")

            # Get device history for a date range (async)
            start_date = date(2025, 1, 1)
            end_date = date(2025, 1, 31)
            devices = await client.get_devices_history(start_date, end_date)
            print(f"Retrieved data for {len(devices)} devices.")

            # Access device data
            for serial, device in devices.items():
                print("-" * 20)
                print(f"Device Serial: {serial}")
                print(f"Type: {device.__class__.__name__}")
                print(f"Location: {device.location}")
                if device.last_reading:
                    print(f"Last Reading: {device.last_reading.reading} on {device.last_reading.date.date()}")
                else:
                    print("Last Reading: N/A")
                # Access full history if needed: device.history

        except IstaLoginError as err:
            print(f"Login failed: {err}")
        except IstaConnectionError as err:
            print(f"Connection error: {err}")
        except Exception as err:
            print(f"An unexpected error occurred: {err}")

        # No need to explicitly call client.close() if session is managed externally
        # If client created its own session, call await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## Development

### Setup Development Environment

1.  Clone the repository:
    ```bash
    git clone [https://github.com/herruzo99/pycalista-ista.git](https://github.com/herruzo99/pycalista-ista.git)
    cd pycalista-ista
    ```
2.  Create and activate a virtual environment (recommended):
    ```bash
    python -m venv .venv
    source .venv/bin/activate # or .venv\Scripts\activate on Windows
    ```
3.  Install development dependencies:
    ```bash
    pip install -e ".[dev]"
    ```
    This installs the package in editable mode plus dev tools like `pytest`, `pytest-asyncio`, `aresponses`, `black`, `isort`, `mypy`, `ruff`.

4.  Set up pre-commit hooks (optional but recommended):
    ```bash
    pre-commit install
    ```

### Running Tests

The project uses `pytest` and `pytest-asyncio`.

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=pycalista_ista

# Run specific test file
pytest tests/test_virtual_api.py
```

Tests require mocking external requests, which is handled using `aresponses`.

### Code Style and Linting

-   Code is formatted using `black`.
-   Imports are sorted using `isort`.
-   Linting is done using `ruff`.
-   Type checking is done using `mypy`.

Run checks manually:
```bash
black . --check
isort . --check-only
ruff check .
mypy pycalista_ista tests
```
Or run pre-commit hooks: `pre-commit run --all-files`

## Contributing

Contributions are welcome! Please follow the guidelines in [CONTRIBUTING.md](CONTRIBUTING.md).

1.  Fork the repository.
2.  Create your feature branch (`git checkout -b feature/amazing-feature`).
3.  Make your changes, ensuring tests pass and coverage is maintained.
4.  Update documentation if necessary.
5.  Commit your changes following Conventional Commits.
6.  Push to the branch (`git push origin feature/amazing-feature`).
7.  Open a Pull Request.

## Interact with the Project

### Get the Software

1.  Install from PyPI:
    ```bash
    pip install pycalista-ista
    ```
2.  Clone the repository:
    ```bash
    git clone [https://github.com/herruzo99/pycalista-ista.git](https://github.com/herruzo99/pycalista-ista.git)
    ```

### Provide Feedback

Use GitHub Issues and Discussions:

1.  **Bug Reports**: [Open an issue](https://github.com/herruzo99/pycalista-ista/issues/new?template=bug_report.md)
2.  **Feature Requests**: [Submit an enhancement](https://github.com/herruzo99/pycalista-ista/issues/new?template=feature_request.md)
3.  **Questions**: [Start a discussion](https://github.com/herruzo99/pycalista-ista/discussions)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
