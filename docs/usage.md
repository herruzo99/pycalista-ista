# Usage Guide

## Basic Usage

### Authentication

```python
from pycalista_ista import PyCalistaIsta

# Initialize client
client = PyCalistaIsta("your@email.com", "your_password")

# Login to the service
client.login()
```

### Retrieving Device History

```python
from datetime import date

# Define date range
start_date = date(2025, 1, 1)
end_date = date(2025, 1, 31)

# Get device history
devices = client.get_devices_history(start_date, end_date)
```

### Working with Devices

```python
# Iterate through devices
for serial, device in devices.items():
    print(f"Device {serial} at {device.location}")
    
    # Get latest reading
    if device.last_reading:
        print(f"Last reading: {device.last_reading.reading}")
        print(f"Reading date: {device.last_reading.date}")
    
    # Get latest consumption
    if device.last_consumption:
        print(f"Last consumption: {device.last_consumption.reading}")

# Access specific device by serial number
if "12345" in devices:
    device = devices["12345"]
    print(f"Device type: {device.__class__.__name__}")
```

### Reading History Analysis

```python
# Get all readings for a device
device = devices["12345"]
readings = device.history

# Calculate total consumption
total = 0
for i in range(1, len(readings)):
    consumption = readings[i] - readings[i-1]
    total += consumption

print(f"Total consumption: {total}")

# Get readings in date range
start = datetime(2025, 1, 1)
end = datetime(2025, 1, 15)
period_readings = [r for r in readings if start <= r.date <= end]
```

## Error Handling

```python
from pycalista_ista.exception_classes import LoginError, ParserError

try:
    client.login()
except LoginError as e:
    print(f"Login failed: {e}")

try:
    devices = client.get_devices_history(start_date, end_date)
except ParserError as e:
    print(f"Failed to parse device data: {e}")
```

## Best Practices

1. Session Management
   ```python
   # The client handles session expiration automatically
   # No need to manually relogin
   devices = client.get_devices_history(start_date, end_date)
   ```

2. Resource Cleanup
   ```python
   # The client handles cleanup automatically
   # No need for explicit cleanup
   ```

3. Date Handling
   ```python
   # Always use timezone-aware dates for consistency
   from datetime import datetime, timezone
   
   date = datetime(2025, 1, 1, tzinfo=timezone.utc)
   ```

4. Error Recovery
   ```python
   from requests.exceptions import RequestException
   
   try:
       devices = client.get_devices_history(start_date, end_date)
   except RequestException:
       # Wait and retry
       time.sleep(5)
       devices = client.get_devices_history(start_date, end_date)
