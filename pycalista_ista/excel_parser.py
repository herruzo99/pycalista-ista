from datetime import datetime, timezone
import logging
import re

import xlrd

from .models.cold_water_device import ColdWaterDevice
from .models.heating_device import HeatingDevice
from .models.hot_water_device import HotWaterDevice

_LOGGER = logging.getLogger(__name__)


class ExcelParser:
    def __init__(self, io_file, current_year: int = datetime.now().year):
        self.io_file = io_file
        self.current_year = current_year

    def _get_rows_as_dict(self):
        file_data = self.io_file.read()
        if not file_data:
            raise ValueError("File content is empty or None.")
        wb = xlrd.open_workbook(file_contents=file_data)
        sheet = wb.sheet_by_index(0)

        data = []

        # Normalize headers to remove extra spaces and make lowercase
        raw_headers = sheet.row_values(0)  # First row is the header
        headers = [
            header.strip().lower().replace("º", "").replace(" ", "_")
            for header in raw_headers
        ]

        # Reverse to iterate from most recent to oldest
        rows = []
        for row_index in range(1, sheet.nrows):  # Skip the header row
            row_values = sheet.row_values(row_index)
            row_dict = {headers[i]: row_values[i] for i in range(len(headers))}
            rows.append(row_dict)

        # Fill missing readings with the next available value (future readings)
        for row_dict in rows:
            # Track the previous valid reading for each column
            previous_reading_value = None

            for date_column in reversed(
                headers
            ):  # Start from most recent to oldest (backwards)
                reading_value = row_dict.get(date_column)

                # If the reading value is missing, replace it with the previous value
                if not reading_value and previous_reading_value:
                    row_dict[date_column] = previous_reading_value
                else:
                    previous_reading_value = reading_value

            data.append(row_dict)

        return data

    def get_devices_history(self):
        sensors = self._get_rows_as_dict()
        devices = {}
        for row in sensors:
            # Safely get data from row with default fallback
            location = row.get("ubicacion", "")
            serial_number = row.get("n_serie", "")
            device_type = row.get("tipo", "")
            readings = {
                k: v
                for k, v in row.items()
                if k not in {"ubicacion", "n_serie", "tipo"}
            }

            # Parse the location into ID and name
            try:
                location_id, location_name = ExcelParser._parse_location(location)
            except ValueError as e:
                _LOGGER.error(f"Failed to parse location '{location}': {e}")
                continue
            # Create the correct device instance
            if "Distribuidor de Agua fria" in device_type:
                device = ColdWaterDevice(serial_number, location_id, location_name)
            elif "Distribuidor de Costes de Agua caliente" in device_type:
                device = HotWaterDevice(serial_number, location_id, location_name)
            elif "Distribuidor de Costes de Calefacción" in device_type:
                device = HeatingDevice(serial_number, location_id, location_name)
            else:
                _LOGGER.warning(f"Unknown device type: {device_type}")
                continue

            # Add readings to the device's history
            last_processed_date = (
                None  # To track the last processed date and decide the year
            )
            previous_year = self.current_year - 1
            in_previous_year = False

            for date_str, reading in readings.items():
                try:
                    # Parse the day and month without a year
                    parsed_date = datetime.strptime(
                        date_str + "/" + str(self.current_year), "%d/%m/%Y"
                    ).replace(tzinfo=timezone.utc)
                    month = parsed_date.month

                    # Determine the correct year
                    if last_processed_date is None:
                        # First date, assume current year
                        reading_date = parsed_date.replace(year=self.current_year)
                    else:
                        # Compare with the last processed month
                        if month > last_processed_date.month and not in_previous_year:
                            in_previous_year = True

                        if in_previous_year:
                            reading_date = parsed_date.replace(year=previous_year)
                        else:
                            # Otherwise, it's in the current year
                            reading_date = parsed_date.replace(year=self.current_year)

                    # Update the last processed date
                    last_processed_date = reading_date

                    # Convert the reading to a float, handling commas as decimal separators
                    reading_value = (
                        float(str(reading).replace(",", ".")) if reading else 0.0
                    )
                    device.add_reading_value(reading_value, reading_date)

                except ValueError as e:
                    _LOGGER.error(
                        f"Invalid reading value for {serial_number} on {date_str}: {reading}. Error: {e}"
                    )
                except Exception as e:
                    _LOGGER.error(
                        f"Unexpected error for {serial_number} on {date_str}: {e}"
                    )

            devices[device.serial_number] = device
        return devices

    @staticmethod
    def _parse_location(location: str) -> tuple[int, str]:
        """
        Parses the 'Ubicacion' column value to extract the device id and name.
        Example: '(1-Cocina1)' -> (id: 1, name: 'Cocina1')
        """
        # Regular expression to match the pattern (number-name)
        match = re.match(r"\((\d+)-([^)]+)\)", location)

        if match:
            device_id = int(match.group(1))  # Extract the number as id
            location = match.group(2)  # Extract the name part
            return device_id, location
        else:
            # Return a default value if the format doesn't match
            _LOGGER.error(f"Invalid format for ubicacion: {location}")
            return None, None
