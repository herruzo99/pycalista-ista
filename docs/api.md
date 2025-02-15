# API Reference

## PyCalistaIsta

Main client class for interacting with the Ista Calista service.

```python
from pycalista_ista import PyCalistaIsta

client = PyCalistaIsta(username="user@example.com", password="password")
```

### Methods

#### login()
Authenticate with the Ista Calista service.

```python
client.login()
```

#### get_devices_history(start_date: date, end_date: date)
Retrieve consumption history for all devices.

```python
from datetime import date

history = client.get_devices_history(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 1, 31)
)
```

Returns a dictionary mapping device serial numbers to Device objects.

## Device Classes

### Device
Base class for all meter types.

#### Properties
- `serial_number`: Unique identifier for the device
- `location`: Physical location description
- `history`: List of readings ordered by date
- `last_reading`: Most recent reading
- `last_consumption`: Consumption between last two readings

### HeatingDevice
Specialized class for heating meters.

```python
from pycalista_ista import HeatingDevice

device = HeatingDevice("12345", "Living Room")
```

### WaterDevice
Base class for water meters.

### HotWaterDevice
Specialized class for hot water meters.

### ColdWaterDevice
Specialized class for cold water meters.

## Reading
Class representing a single meter reading.

#### Properties
- `date`: Timestamp of the reading
- `reading`: The meter value

#### Methods
- `__sub__`: Calculate consumption between two readings
