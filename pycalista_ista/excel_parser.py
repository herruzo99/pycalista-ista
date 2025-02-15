"""Excel parser for Ista Calista meter readings.

This module provides functionality to parse Excel files containing meter
readings from the Ista Calista system. It handles various meter types
and their historical readings, including data normalization and validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Final, IO, TypeVar

import xlrd
from xlrd.sheet import Sheet

from .exception_classes import ParserError
from .models.cold_water_device import ColdWaterDevice
from .models.device import Device
from .models.heating_device import HeatingDevice
from .models.hot_water_device import HotWaterDevice

_LOGGER: Final = logging.getLogger(__name__)

# Type variable for device dictionaries
DeviceDict = TypeVar("DeviceDict", bound=dict[str, Device])

# Constants for Excel parsing
METADATA_COLUMNS: Final[set[str]] = {"tipo", "n_serie", "ubicacion"}
DATE_FORMAT: Final[str] = "%d/%m/%Y"

# Device type identifiers
COLD_WATER_TYPE: Final[str] = "Radio agua fría"
HOT_WATER_TYPE: Final[str] = "Radio agua caliente"
HEATING_TYPE: Final[str] = "Distribuidor de Costes de Calefacción"


class ExcelParser:
    """Parser for Ista Calista Excel meter reading files.
    
    This class handles parsing of Excel files containing meter readings,
    including data normalization, validation, and conversion into device
    objects with their reading histories.
    
    Attributes:
        io_file: File-like object containing the Excel data
        current_year: Year to use for readings without explicit year
    """

    def __init__(self, io_file: IO[bytes], current_year: int | None = None) -> None:
        """Initialize the Excel parser.
        
        Args:
            io_file: File-like object containing the Excel data
            current_year: Year to use for readings (defaults to current year)
            
        Raises:
            ValueError: If io_file is None
        """
        if io_file is None:
            raise ValueError("io_file cannot be None")
            
        self.io_file = io_file
        self.current_year = current_year or datetime.now().year

    def _get_rows_as_dict(self) -> list[dict[str, Any]]:
        """Parse Excel rows into dictionaries.
        
        Returns:
            List of dictionaries containing row data
            
        Raises:
            ParserError: If file is empty or parsing fails
        """
        try:
            file_data = self.io_file.read()
            if not file_data:
                raise ParserError("File content is empty")
                
            wb = xlrd.open_workbook(file_contents=file_data)
            sheet = wb.sheet_by_index(0)
            
            return self._process_sheet(sheet)
            
        except xlrd.XLRDError as err:
            raise ParserError(f"Failed to parse Excel file: {err}") from err
        except Exception as err:
            raise ParserError(f"Unexpected error parsing file: {err}") from err

    def _process_sheet(self, sheet: Sheet) -> list[dict[str, Any]]:
        """Process an Excel sheet into normalized row dictionaries.
        
        Args:
            sheet: Excel worksheet to process
            
        Returns:
            List of normalized row dictionaries
        """
        headers = self._normalize_headers(sheet.row_values(0))
        rows = []
        
        for row_index in range(1, sheet.nrows):
            row_values = sheet.row_values(row_index)
            row_dict = {headers[i]: row_values[i] for i in range(len(headers))}
            rows.append(row_dict)
            
        return self._fill_missing_readings(rows, headers)

    def _normalize_headers(self, raw_headers: list[str]) -> list[str]:
        """Normalize Excel column headers.
        
        Args:
            raw_headers: Raw header strings from Excel
            
        Returns:
            List of normalized header strings
        """
        return [
            header.strip().lower().replace("º", "").replace(" ", "_")
            for header in raw_headers
        ]

    def _fill_missing_readings(
        self,
        rows: list[dict[str, Any]],
        headers: list[str],
    ) -> list[dict[str, Any]]:
        """Fill missing readings with next available value.
        
        Args:
            rows: Raw row dictionaries
            headers: Normalized column headers
            
        Returns:
            Rows with missing readings filled
        """
        data = []
        
        for row_dict in rows:
            previous_reading_value = None
            
            for column in reversed(headers):
                reading_value = row_dict.get(column)
                
                if not reading_value and previous_reading_value:
                    row_dict[column] = (
                        previous_reading_value
                        if column not in METADATA_COLUMNS
                        else ""
                    )
                elif column not in METADATA_COLUMNS:
                    previous_reading_value = reading_value
                    
            data.append(row_dict)
            
        return data

    def get_devices_history(self) -> DeviceDict:
        """Get device histories from Excel data.
        
        Returns:
            Dictionary mapping serial numbers to device objects
            
        Raises:
            ParserError: If parsing fails
        """
        try:
            sensors = self._get_rows_as_dict()
            devices: DeviceDict = {}
            
            for row in sensors:
                device = self._process_device_row(row)
                if device:
                    devices[device.serial_number] = device
                    
            return devices
            
        except Exception as err:
            raise ParserError(f"Failed to process device histories: {err}") from err

    def _process_device_row(self, row: dict[str, Any]) -> Device | None:
        """Process a single device row.
        
        Args:
            row: Dictionary containing device data
            
        Returns:
            Device object if successful, None if device type unknown
        """
        location = row.get("ubicacion", "")
        serial_number = row.get("n_serie", "")
        device_type = row.get("tipo", "")
        
        device = self._create_device(device_type, serial_number, location)
        if not device:
            _LOGGER.warning("Unknown device type: %s", device_type)
            return None
            
        readings = {
            k: v for k, v in row.items() if k not in METADATA_COLUMNS
        }
        
        self._add_device_readings(device, readings)
        return device

    def _create_device(
        self,
        device_type: str,
        serial_number: str,
        location: str,
    ) -> Device | None:
        """Create appropriate device instance based on type.
        
        Args:
            device_type: Type string from Excel
            serial_number: Device serial number
            location: Device location
            
        Returns:
            Device instance or None if type unknown
        """
        if COLD_WATER_TYPE in device_type:
            return ColdWaterDevice(serial_number, location)
        if HOT_WATER_TYPE in device_type:
            return HotWaterDevice(serial_number, location)
        if HEATING_TYPE in device_type:
            return HeatingDevice(serial_number, location)
        return None

    def _add_device_readings(
        self,
        device: Device,
        readings: dict[str, Any],
    ) -> None:
        """Add readings to a device.
        
        Args:
            device: Device to add readings to
            readings: Dictionary of date strings to reading values
        """
        last_processed_date = None
        previous_year = self.current_year - 1
        in_previous_year = False
        
        for date_str, reading in readings.items():
            try:
                reading_date = self._parse_reading_date(
                    date_str,
                    last_processed_date,
                    previous_year,
                    in_previous_year,
                )
                
                if reading_date.month > (last_processed_date.month if last_processed_date else 0):
                    in_previous_year = True
                    
                last_processed_date = reading_date
                
                reading_value = float(str(reading).replace(",", ".")) if reading else 0.0
                device.add_reading_value(reading_value, reading_date)
                
            except ValueError as err:
                _LOGGER.error(
                    "Invalid reading value for %s on %s: %s. Error: %s",
                    device.serial_number,
                    date_str,
                    reading,
                    err,
                )
            except Exception as err:
                _LOGGER.error(
                    "Unexpected error for %s on %s: %s",
                    device.serial_number,
                    date_str,
                    err,
                )

    def _parse_reading_date(
        self,
        date_str: str,
        last_processed_date: datetime | None,
        previous_year: int,
        in_previous_year: bool,
    ) -> datetime:
        """Parse a reading date string.
        
        Args:
            date_str: Date string from Excel
            last_processed_date: Previously processed date
            previous_year: Previous year value
            in_previous_year: Whether processing previous year
            
        Returns:
            Parsed datetime with correct year
            
        Raises:
            ValueError: If date parsing fails
        """
        parsed_date = datetime.strptime(
            f"{date_str}/{self.current_year}",
            DATE_FORMAT,
        ).replace(tzinfo=timezone.utc)
        
        if not last_processed_date:
            return parsed_date.replace(year=self.current_year)
            
        return parsed_date.replace(
            year=previous_year if in_previous_year else self.current_year
        )
