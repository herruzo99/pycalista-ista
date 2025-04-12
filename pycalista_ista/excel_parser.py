"""Excel parser for Ista Calista meter readings.

Handles parsing of Excel files (.xls and .xlsx) containing meter
readings, including data normalization, validation, date/year handling,
and conversion into device objects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import IO, Any, Final, TypeVar

import pandas as pd
from unidecode import unidecode

# Use the specific exception class
from .exception_classes import IstaParserError
from .models.cold_water_device import ColdWaterDevice
from .models.device import Device
from .models.heating_device import HeatingDevice
from .models.hot_water_device import HotWaterDevice

_LOGGER: Final = logging.getLogger(__name__)

# Type variable for device dictionaries
DeviceDict = TypeVar("DeviceDict", bound=dict[str, Device])

# Constants for Excel parsing
# Define expected metadata columns explicitly for validation
EXPECTED_METADATA_COLUMNS: Final[set[str]] = {"tipo", "n_serie", "ubicacion"}
# Normalized header names (lowercase, underscores, no accents)
NORMALIZED_TYPE_HEADER: Final[str] = "tipo"
NORMALIZED_SERIAL_HEADER: Final[str] = "n_serie"
NORMALIZED_LOCATION_HEADER: Final[str] = "ubicacion"

DATE_FORMAT: Final[str] = "%d/%m/%Y" # Full date format including year
DATE_HEADER_FORMAT: Final[str] = "%d/%m" # Format expected in headers initially

# Device type identifiers (normalized)
COLD_WATER_TYPE_ID: Final[str] = "radio agua fria"
HOT_WATER_TYPE_ID: Final[str] = "radio agua caliente"
HEATING_TYPE_ID: Final[str] = "distribuidor de costes de calefaccion" # Normalized


class ExcelParser:
    """Parser for Ista Calista Excel meter reading files (.xls, .xlsx).

    Handles parsing, data normalization, validation, and conversion into device
    objects with reading histories.

    Attributes:
        io_file: File-like object containing the Excel data.
        current_year: Year context for parsing date headers.
    """

    def __init__(self, io_file: IO[bytes], current_year: int | None = None) -> None:
        """Initialize the Excel parser.

        Args:
            io_file: File-like object containing the Excel data.
            current_year: Year context for readings (defaults to current year).

        Raises:
            ValueError: If io_file is None.
            IstaParserError: If current_year is invalid.
        """
        if io_file is None:
            raise ValueError("io_file cannot be None")

        self.io_file: IO[bytes] = io_file
        try:
            self.current_year: int = current_year or datetime.now(timezone.utc).year
            # Basic validation for the year
            if not 1900 < self.current_year < 2100:
                 raise ValueError(f"Invalid year provided: {current_year}")
        except ValueError as err:
            raise IstaParserError(f"Invalid current_year for parser: {err}") from err

        _LOGGER.debug("ExcelParser initialized with year context: %d", self.current_year)


    def _normalize_headers(self, raw_headers: list[str]) -> list[str]:
        """Normalize Excel column headers.

        Converts to lowercase, replaces spaces with underscores, removes accents,
        and handles specific variations like '°'/'º'.

        Args:
            raw_headers: Raw header strings from Excel.

        Returns:
            List of normalized header strings.
        """
        normalized_headers = []
        for header in raw_headers:
            if not isinstance(header, str):
                 _LOGGER.warning("Skipping non-string header: %s (%s)", header, type(header))
                 normalized_headers.append(f"unknown_header_{len(normalized_headers)}")
                 continue
            # Normalize: lowercase, strip whitespace, remove accents, replace specific chars
            norm = header.strip().replace("°", "").replace("º", "").replace(" ", "_").replace("n_", "n").lower() # Handle 'nº' -> 'n_serie'
            norm = unidecode(norm)

            normalized_headers.append(norm)
        _LOGGER.debug("Normalized headers: %s", normalized_headers)
        return normalized_headers

    def _assign_years_to_date_headers(self, headers: list[str]) -> list[str]:
        """Assigns the correct year to date headers (e.g., 'dd/mm').

        Iterates through headers, identifying date-like strings ('dd/mm').
        Assigns the `current_year` context, decrementing the year if the month
        decreases compared to the previous date header (indicating year rollover).

        Args:
            headers: List of normalized headers.

        Returns:
            List of headers with years assigned to date columns ('dd/mm/yyyy').
            Metadata columns remain unchanged.

        Raises:
            IstaParserError: If a header looks like a date but cannot be parsed.
        """
        processed_headers: list[str] = []
        assigned_year = self.current_year
        last_processed_month: int | None = None

        for header in headers:
            if header in EXPECTED_METADATA_COLUMNS:
                processed_headers.append(header)
                continue

            # Try parsing as 'dd/mm'
            try:
                # Use a dummy year (like 2000) for parsing, we only care about day/month
                parsed_date = datetime.strptime(f"{header}/2000", f"{DATE_HEADER_FORMAT}/%Y")
                current_month = parsed_date.month

                # Check for year rollover (month decreases compared to last processed date)
                if last_processed_month is not None and current_month > last_processed_month:
                    assigned_year -= 1
                    _LOGGER.debug(
                        "Detected year rollover for header '%s'. Assigning year: %d",
                        header, assigned_year
                    )

                # Format header with the assigned year
                full_date_header = f"{header}/{assigned_year}"
                processed_headers.append(full_date_header)
                last_processed_month = current_month # Update last month for next iteration

            except ValueError:
                 # Header doesn't match 'dd/mm' format, treat as non-date or raise error
                 _LOGGER.warning("Header '%s' could not be parsed as a date (%s). Treating as non-date.", header, DATE_HEADER_FORMAT)
                 # Option 1: Treat as metadata (might hide errors)
                 # processed_headers.append(header)
                 # Option 2: Raise an error if strict date format is expected
                 raise IstaParserError(f"Unexpected header format: '{header}'. Expected metadata or 'dd/mm'.")
            except Exception as e:
                 # Catch other unexpected errors during date processing
                 raise IstaParserError(f"Error processing header '{header}': {e}") from e


        _LOGGER.debug("Headers with assigned years: %s", processed_headers)
        return processed_headers


    def _read_and_prepare_dataframe(self) -> pd.DataFrame:
        """Reads the Excel file into a pandas DataFrame and prepares it.

        Handles reading, header normalization, year assignment,
        and basic validation.

        Returns:
            Prepared pandas DataFrame.

        Raises:
            IstaParserError: If file reading, header processing, or validation fails.
        """
        try:
            # Ensure file pointer is at the beginning
            self.io_file.seek(0)
            df = pd.read_excel(self.io_file, engine='xlrd')
            _LOGGER.debug("Successfully read Excel")

        except Exception as err:
            # Catch errors during file reading (e.g., invalid format, permissions)
            raise IstaParserError(f"Failed to read Excel file: {err}") from err

        if df.empty:
            _LOGGER.warning("Excel file is empty.")
            # Return empty DataFrame, let caller handle it
            return df

        # --- Header Processing ---
        if not df.columns.to_list():
             raise IstaParserError("Excel file has no header row.")

        raw_headers = df.columns.astype(str).to_list()
        normalized_headers = self._normalize_headers(raw_headers)

        # Assign years to date headers
        try:
             final_headers = self._assign_years_to_date_headers(normalized_headers)
        except IstaParserError as err:
             _LOGGER.error("Failed to assign years to date headers: %s", err)
             raise # Re-raise the specific parser error

        # Check if number of headers matches original
        if len(final_headers) != len(raw_headers):
             raise IstaParserError("Header processing resulted in mismatched column count.")

        df.columns = final_headers

        # --- Metadata Validation ---
        missing_metadata = EXPECTED_METADATA_COLUMNS - set(df.columns)
        if missing_metadata:
            raise IstaParserError(f"Missing required metadata columns: {missing_metadata}")

        # Fill NaN in metadata columns with empty strings for consistency
        metadata_cols_list = list(EXPECTED_METADATA_COLUMNS)
        df[metadata_cols_list] = df[metadata_cols_list].fillna('')

        return df


    def get_devices_history(self) -> DeviceDict:
        """Parses the Excel data and returns device histories.

        Reads the Excel file, processes headers and rows, creates Device objects,
        and populates their reading history.

        Returns:
            Dictionary mapping device serial numbers to Device objects.

        Raises:
            IstaParserError: If any step of the parsing process fails.
        """
        _LOGGER.info("Starting Excel parsing process.")
        try:
            df = self._read_and_prepare_dataframe()
        except IstaParserError as err:
             _LOGGER.error("Failed to read or prepare DataFrame: %s", err)
             raise # Propagate error

        if df.empty:
             _LOGGER.info("No data found in Excel file.")
             return {} # Return empty dict if DataFrame is empty

        devices: DeviceDict = {}
        processed_rows = 0
        skipped_rows = 0

        # Iterate through DataFrame rows as dictionaries
        for index, row_dict in df.iterrows():
            processed_rows += 1
            try:
                device = self._process_device_row(row_dict)
                if device:
                    # Add or update device in the dictionary
                    if device.serial_number in devices:
                         # Merge readings if device already exists (shouldn't happen with unique serials per file)
                         _LOGGER.warning("Duplicate serial number found: %s. Merging readings.", device.serial_number)
                         existing_device = devices[device.serial_number]
                         existing_dates = {r.date for r in existing_device.history}
                         for reading in device.history:
                              if reading.date not in existing_dates:
                                   existing_device.add_reading(reading)
                    else:
                         devices[device.serial_number] = device
                else:
                     # Device creation failed (e.g., unknown type)
                     skipped_rows += 1

            except (ValueError, TypeError, IstaParserError) as err:
                _LOGGER.error("Error processing row %d: %s. Data: %s", index, err, row_dict, exc_info=True)
                skipped_rows += 1
            except Exception as err:
                 _LOGGER.exception("Unexpected error processing row %d: %s", index, err)
                 skipped_rows += 1


        _LOGGER.info(
            "Excel parsing finished. Processed %d rows, created/updated %d devices, skipped %d rows.",
            processed_rows, len(devices), skipped_rows
        )
        if skipped_rows > 0:
             _LOGGER.warning("%d rows were skipped due to errors during processing.", skipped_rows)

        return devices


    def _process_device_row(self, row: dict[str, Any]) -> Device | None:
        """Processes a single row from the DataFrame into a Device object.

        Extracts metadata, creates the appropriate Device subclass, and adds readings.

        Args:
            row: Dictionary representing a row from the DataFrame.

        Returns:
            Device object with populated history, or None if creation fails.

        Raises:
            ValueError: If essential metadata (serial number) is missing or invalid.
            IstaParserError: If device type is unknown or reading parsing fails.
        """
        # Extract metadata using normalized header names
        serial_number = str(row.get(NORMALIZED_SERIAL_HEADER, "")).strip()
        location = str(row.get(NORMALIZED_LOCATION_HEADER, "")).strip()
        # Normalize device type string for reliable matching
        device_type_str = str(row.get(NORMALIZED_TYPE_HEADER, "")).strip().lower()
        device_type_str = unidecode(device_type_str) # Remove accents

        if not serial_number:
            raise ValueError("Missing or empty serial number in row.")
        if not device_type_str:
            raise ValueError("Missing or empty device type in row.")

        # Create device instance based on normalized type
        device = self._create_device(device_type_str, serial_number, location)
        if not device:
            # Log warning but allow skipping this row if type is unknown
            _LOGGER.warning(
                "Unknown device type '%s' for serial %s. Skipping row.",
                row.get(NORMALIZED_TYPE_HEADER), serial_number
            )
            return None # Indicate failure to create device

        # Extract and add readings
        # Identify reading columns (those not in metadata)
        reading_columns = {k: v for k, v in row.items() if k not in EXPECTED_METADATA_COLUMNS}
        self._add_device_readings(device, reading_columns)

        return device


    def _create_device(
        self,
        normalized_device_type: str,
        serial_number: str,
        location: str,
    ) -> Device | None:
        """Creates the appropriate Device subclass based on the normalized type string.

        Args:
            normalized_device_type: Normalized (lowercase, accent-free) type string.
            serial_number: Device serial number.
            location: Device location.

        Returns:
            An instance of a Device subclass (HeatingDevice, HotWaterDevice,
            ColdWaterDevice) or None if the type is not recognized.
        """
        if HEATING_TYPE_ID in normalized_device_type:
            return HeatingDevice(serial_number, location)
        if HOT_WATER_TYPE_ID in normalized_device_type:
            return HotWaterDevice(serial_number, location)
        if COLD_WATER_TYPE_ID in normalized_device_type:
            return ColdWaterDevice(serial_number, location)

        # Type not recognized
        return None


    def _add_device_readings(
        self,
        device: Device,
        readings_dict: dict[str, Any],
    ) -> None:
        """Adds readings from the row data to the Device object.

        Parses date headers and reading values, handling potential errors.

        Args:
            device: The Device object to add readings to.
            readings_dict: Dictionary where keys are date strings ('dd/mm/yyyy')
                           and values are the reading values.

        Raises:
            IstaParserError: If date parsing fails for a column header.
        """
        added_count = 0
        skipped_count = 0
        for date_str, reading_val in readings_dict.items():
            try:
                # Parse date string (should already include year)
                reading_date = datetime.strptime(date_str, DATE_FORMAT).replace(tzinfo=timezone.utc)

                # Parse reading value
                if pd.isna(reading_val):
                    # Treat NaN/NaT as None (missing reading)
                    reading_value_float = None
                else:
                    # Convert to float, handling potential commas as decimal separators
                    reading_str = str(reading_val).replace(",", ".")
                    try:
                        reading_value_float = float(reading_str)
                        # Optional: Check for negative values if they are invalid
                        # if reading_value_float < 0:
                        #     _LOGGER.warning("Negative reading value found for %s on %s: %s. Storing as None.",
                        #                     device.serial_number, date_str, reading_value_float)
                        #     reading_value_float = None # Treat negative as missing/invalid
                    except ValueError:
                         _LOGGER.warning(
                            "Invalid reading value format for %s on %s: '%s'. Storing as None.",
                            device.serial_number, date_str, reading_val
                         )
                         reading_value_float = None # Treat unparseable as missing

                # Add the reading (value can be None)
                # The Device model handles sorting and potential negative value errors internally if needed
                device.add_reading_value(reading_value_float, reading_date)
                added_count += 1

            except ValueError as err:
                 # Catch errors from strptime or float conversion specifically
                 _LOGGER.error(
                    "Error parsing reading for %s - Date: '%s', Value: '%s'. Error: %s",
                    device.serial_number, date_str, reading_val, err
                 )
                 skipped_count += 1
            except Exception as err:
                 # Catch unexpected errors during parsing of a single reading
                 _LOGGER.exception(
                    "Unexpected error adding reading for %s - Date: '%s', Value: '%s'",
                    device.serial_number, date_str, reading_val
                 )
                 skipped_count += 1

        _LOGGER.debug(
            "Added %d readings, skipped %d readings for device %s",
            added_count, skipped_count, device.serial_number
        )

