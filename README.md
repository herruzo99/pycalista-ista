# PyCalista-ista

[![PyPI version](https://badge.fury.io/py/pycalista-ista.svg)](https://badge.fury.io/py/pycalista-ista) [![Downloads](https://pepy.tech/badge/pycalista-ista)](https://pepy.tech/project/pycalista-ista) [![Downloads](https://pepy.tech/badge/pycalista-ista/month)](https://pepy.tech/project/pycalista-ista) [![Downloads](https://pepy.tech/badge/pycalista-ista/week)](https://pepy.tech/project/pycalista-ista)

[![GitHub issues](https://img.shields.io/github/issues/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista/issues)
[![GitHub forks](https://img.shields.io/github/forks/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista)
[![GitHub stars](https://img.shields.io/github/stars/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista)
[![GitHub license](https://img.shields.io/github/license/herruzo99/pycalista-ista?style=for-the-badge&logo=github)](https://github.com/herruzo99/pycalista-ista/blob/main/LICENSE)
![GitHub Release Date](https://img.shields.io/github/release-date/herruzo99/pycalista-ista?style=for-the-badge&logo=github)
[![codecov](https://codecov.io/github/herruzo99/pycalista-ista/branch/main/graph/badge.svg?token=BHU8J3OVRT)](https://codecov.io/github/herruzo99/pycalista-ista)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/9868/badge)](https://www.bestpractices.dev/projects/9868)

---

Unofficial Python library for the Ista Calista service API. This library allows you to interact with your Ista Calista account to retrieve consumption data from heating and water meters.

This project is based on [ecotrend-ista](https://github.com/Ludy87/ecotrend-ista)

## Features

- Login and session management
- Retrieve consumption data for heating and water meters
- Parse Excel reports from Ista Calista
- Support for different meter types (heating, hot water, cold water)
- Automatic handling of session expiration

## Installation

### From PyPI

```bash
pip install pycalista-ista
```

### For Development

```bash
git clone https://github.com/herruzo99/pycalista-ista.git
cd pycalista-ista
pip install -e .
```

## Usage

```python
from pycalista_ista import PyCalistaIsta
from datetime import date

# Initialize the client
client = PyCalistaIsta("your@email.com", "your_password")

# Login to the service
client.login()

# Get device history for a date range
start_date = date(2025, 1, 1)
end_date = date(2025, 1, 31)
devices = client.get_devices_history(start_date, end_date)

# Access device data
for serial, device in devices.items():
    print(f"Device {serial} at {device.location}")
    print(f"Last reading: {device.last_reading}")
    print(f"Last consumption: {device.last_consumption}")
```

## Development

### Setup Development Environment

1. Clone the repository:
```bash
git clone https://github.com/herruzo99/pycalista-ista.git
cd pycalista-ista
```

2. Install development dependencies:
```bash
pip install -e ".[dev]"
pip install pytest pytest-cov requests-mock black isort
```

3. Run tests:
```bash
pytest
```

4. Check code formatting:
```bash
black .
isort .
```

### Running Tests

#### Locally

The project uses pytest for testing. To run the tests locally:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=pycalista_ista

# Run specific test file
pytest tests/test_parser.py
```

#### GitHub Actions

You can also run tests through GitHub Actions:

1. Go to the [Actions tab](https://github.com/herruzo99/pycalista-ista/actions) in the repository
2. Select the "Test" workflow
3. Click "Run workflow"
4. Optional: Enable debug logging for verbose output
5. Click "Run workflow" to start the tests

The workflow will:
- Check code formatting (black, isort)
- Run all tests with coverage
- Upload coverage report to Codecov

This is useful for:
- Verifying the current state of the codebase
- Testing in a clean environment
- Generating coverage reports

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run the tests to ensure they pass
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
