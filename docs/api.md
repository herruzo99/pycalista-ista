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

**Input:**
- No parameters required (uses credentials from initialization)

**Output:**
- None
- Raises `LoginError` if authentication fails

**Example:**
```python
client.login()
```

#### get_devices_history(start_date: date, end_date: date)
Retrieve consumption history for all devices.

**Input:**
- `start_date` (date): Start date for history retrieval
- `end_date` (date): End date for history retrieval
  - Must be after start_date
  - Maximum range is 240 days

**Output:**
- Returns `dict[str, Device]`: Dictionary mapping device serial numbers to Device objects
- Each Device object contains:
  - `serial_number` (str): Device identifier
  - `location` (str): Physical location
  - `history` (list[Reading]): List of readings
- Raises:
  - `ParserError`: If data parsing fails
  - `RequestException`: If network request fails
  - `LoginError`: If session expired (auto-relogin attempted)

**Example:**
```python
from datetime import date

history = client.get_devices_history(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 1, 31)
)

# Access device data
device = history["12345"]
print(f"Location: {device.location}")
print(f"Readings: {len(device.history)}")
```

## Device Classes

### Device
Base class for all meter types.

#### Properties
- `serial_number` (str): Unique identifier for the device
- `location` (str): Physical location description
- `history` (list[Reading]): List of readings ordered by date
- `last_reading` (Reading | None): Most recent reading, None if no readings
- `last_consumption` (Reading | None): Consumption between last two readings, None if less than 2 readings

#### Methods

##### add_reading(reading: Reading) -> None
Add a new reading to the device history.

**Input:**
- `reading` (Reading): Reading object to add
  - Must have valid date and non-negative reading value

**Output:**
- None
- Raises `ValueError` if reading value is negative

##### add_reading_value(reading_value: float, date: datetime) -> None
Convenience method to add a reading using raw values.

**Input:**
- `reading_value` (float): The meter reading value
  - Must be non-negative
- `date` (datetime): Timestamp of the reading

**Output:**
- None
- Raises `ValueError` if reading_value is negative

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
- `date` (datetime): Timestamp of the reading (timezone-aware)
- `reading` (float): The meter value (non-negative)

#### Methods

##### __init__(date: datetime, reading: float)
Initialize a new reading.

**Input:**
- `date` (datetime): Timestamp of the reading
  - Will be converted to UTC if timezone-naive
- `reading` (float): The meter value
  - Must be non-negative

**Output:**
- None
- Raises `ValueError` if reading is negative

##### __sub__(other: Reading) -> float
Calculate consumption between two readings.

**Input:**
- `other` (Reading): Reading to subtract from this one

**Output:**
- Returns `float`: The consumption value (can be negative)
