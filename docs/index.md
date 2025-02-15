# PyCalista-ista Documentation

PyCalista-ista is a Python library for interacting with the Ista Calista service, allowing you to retrieve and analyze consumption data from heating and water meters.

## Documentation Contents

1. [Installation Guide](installation.md)
   - Requirements
   - Installation methods
   - Dependency information

2. [Usage Guide](usage.md)
   - Basic usage
   - Working with devices
   - Reading history analysis
   - Error handling
   - Best practices

3. [API Reference](api.md)
   - PyCalistaIsta client
   - Device classes
   - Reading class
   - Method documentation

## Quick Start

```python
from pycalista_ista import PyCalistaIsta
from datetime import date

# Initialize and login
client = PyCalistaIsta("your@email.com", "your_password")
client.login()

# Get device history
devices = client.get_devices_history(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 1, 31)
)

# Access device data
for serial, device in devices.items():
    print(f"Device {serial} at {device.location}")
    print(f"Last reading: {device.last_reading}")
    print(f"Last consumption: {device.last_consumption}")
```

## Support

- [GitHub Issues](https://github.com/herruzo99/pycalista-ista/issues) for bug reports and feature requests
- [GitHub Discussions](https://github.com/herruzo99/pycalista-ista/discussions) for questions and community support

## Contributing

See our [Contributing Guide](../CONTRIBUTING.md) for information on how to contribute to the project.
