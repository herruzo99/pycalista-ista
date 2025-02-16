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

You can run tests through GitHub Actions in two ways:

1. **Automatic Runs**:
   - Tests run automatically on every push to main
   - Tests run on every pull request
   - Results appear in the Actions tab

2. **Manual Runs**:
   1. Go to [Actions](https://github.com/herruzo99/pycalista-ista/actions)
   2. Click on the "Test" workflow in the left sidebar
   3. Click the "Run workflow" button (blue button, top right)
   4. Select branch to test (default: main)
   5. Optionally enable debug logging for verbose output
   6. Click "Run workflow" green button

The workflow performs:
- Python 3.12 environment setup
- Dependency installation
- Code formatting checks (black, isort)
- Test execution with coverage
- Coverage report upload to Codecov

View results:
- Click on the workflow run in Actions
- Expand job steps to see details
- Check Codecov for coverage report
- Review any test or formatting failures

This is useful for:
- Verifying changes before PR
- Testing in clean environment
- Debugging test issues
- Generating coverage reports

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run the tests to ensure they pass
4. Commit your changes (`git commit -m 'Add amazing feature'`)
5. Push to the branch (`git push origin feature/amazing-feature`)
6. Open a Pull Request

## Interact with the Project

### Get the Software

1. Install from PyPI:
```bash
pip install pycalista-ista
```

2. Clone the repository:
```bash
git clone https://github.com/herruzo99/pycalista-ista.git
```

### Provide Feedback

We welcome your feedback and bug reports!

1. **Bug Reports**: [Open an issue](https://github.com/herruzo99/pycalista-ista/issues/new?template=bug_report.md) for any problems you encounter
2. **Feature Requests**: [Submit an enhancement](https://github.com/herruzo99/pycalista-ista/issues/new?template=feature_request.md) for new features
3. **Questions**: [Start a discussion](https://github.com/herruzo99/pycalista-ista/discussions) for usage questions

### Contribute

We encourage contributions! See our [Contributing Guide](CONTRIBUTING.md) for:
- Development setup
- Code standards
- Testing requirements
- Pull request process

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
