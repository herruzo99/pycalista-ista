# Installation Guide

## Requirements

- Python 3.12 or higher
- pip package manager

## Installation Methods

### From PyPI (Recommended)

```bash
pip install pycalista-ista
```

### From Source

1. Clone the repository:
```bash
git clone https://github.com/herruzo99/pycalista-ista.git
cd pycalista-ista
```

2. Install in development mode:
```bash
pip install -e .
```

## Verification

Verify the installation by running:

```python
import pycalista_ista
print(pycalista_ista.__version__)
```

## Dependencies

The package automatically installs the following dependencies:
- requests>=2.31.0: For HTTP requests
- xlrd>=2.0.1: For Excel file parsing

## Optional Dependencies

For development:
```bash
pip install pytest pytest-cov requests-mock black isort
