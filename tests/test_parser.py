"""Tests for Excel parser functionality."""

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd  # Import pandas for creating test dataframes
import pytest

from pycalista_ista import ColdWaterDevice, HeatingDevice, HotWaterDevice
from pycalista_ista.excel_parser import ExcelParser
from pycalista_ista.exception_classes import IstaParserError


def test_header_normalization():
    """Test Excel header normalization."""
    parser = ExcelParser(BytesIO(b""), 2024) # Provide dummy IO and year
    headers = [
        "Tipo", "N° Serie", "Nº Serie", "Ubicación", "1º Lectura",
        "26/11", " 25/11 ", "Agua Fría", "Distribuidor de Costes de Calefacción"
    ]
    normalized = parser._normalize_headers(headers)
    assert normalized == [
        "tipo", "n_serie", "n_serie", "ubicacion", "1_lectura",
        "26/11", "25/11", "agua_fria", "distribuidor_de_costes_de_calefaccion"
    ]
    # Test with non-string header
    assert parser._normalize_headers([123, "Header 2"]) == ["unknown_header_0", "header_2"]


def test_assign_years_to_date_headers():
    """Test year assignment logic."""
    parser = ExcelParser(BytesIO(b""), current_year=2024)
    headers = ["tipo", "n_serie", "15/01", "01/01", "15/12", "01/12"]
    processed = parser._assign_years_to_date_headers(headers)
    assert processed == ["tipo", "n_serie", "15/01/2024", "01/01/2024", "15/12/2023", "01/12/2023"]

    # Test single date
    headers_single = ["tipo", "15/06"]
    processed_single = parser._assign_years_to_date_headers(headers_single)
    assert processed_single == ["tipo", "15/06/2024"]

    # Test invalid date format
    headers_invalid = ["tipo", "15-01-2024"]
    with pytest.raises(IstaParserError, match="Unexpected header format: '15-01-2024'"):
        parser._assign_years_to_date_headers(headers_invalid)


def test_device_type_creation():
    """Test device type detection and creation from normalized strings."""
    parser = ExcelParser(BytesIO(b""), 2024)
    # Use normalized type strings
    assert isinstance(parser._create_device("distribuidor de costes de calefaccion", "1", "L"), HeatingDevice)
    assert isinstance(parser._create_device("radio agua caliente", "2", "L"), HotWaterDevice)
    assert isinstance(parser._create_device("radio agua fria", "3", "L"), ColdWaterDevice)
    assert parser._create_device("unknown type", "4", "L") is None


@pytest.mark.parametrize(
    "excel_file_content, expected_devices, year, expected_serials",
    [
        ("consulta_2023-12-29_2024-01-02.xls", 11, 2024, ["141740872", "414293326"]),
        ("consulta_2024-11-30_2025-01-01.xls", 11, 2025, ["141740872", "414293326"]),
        ("consulta_2025-01-10_2025-01-25.xls", 11, 2025, ["141740872", "414293326"]),
    ],
    indirect = ['excel_file_content']
)
def test_get_devices_history_from_file(
    excel_file_content: str, expected_devices: int, year: int, expected_serials: list[str]
):
    """Test parsing full consumption data from real Excel files."""
    # Use fixture to get file content
    parser = ExcelParser(io_file=BytesIO(excel_file_content), current_year=year)
    history = parser.get_devices_history()

    assert len(history) == expected_devices
    for serial in expected_serials:
        assert serial in history

    print(history)
    # Spot check device types and locations based on known serials
    assert isinstance(history["141740872"], HeatingDevice)
    assert history["141740872"].location == "(1-Cocina1)"
    assert isinstance(history["414293326"], ColdWaterDevice)

    # Check readings are ordered and valid
    for device in history.values():
        if device.history:
            dates = [reading.date for reading in device.history]
            assert dates == sorted(dates), f"Device {device.serial_number} readings not sorted"
            assert all(r.reading is None or isinstance(r.reading, (int, float)) for r in device.history)


def test_parser_invalid_file_format():
    """Test parser behavior with non-Excel file."""
    invalid_file = BytesIO(b"this is not an excel file")
    parser = ExcelParser(invalid_file, 2024)
    with pytest.raises(IstaParserError, match="Failed to read Excel file"):
        parser.get_devices_history()

def test_parser_reading_value_handling():
    """Test parsing various reading value formats."""
    parser = ExcelParser(BytesIO(b""), 2024)
    device = HeatingDevice("123", "Test")
    readings_dict = {
        "01/01/2024": 10,      # Integer
        "02/01/2024": "15.7",  # String float (dot)
        "03/01/2024": "20,5",  # String float (comma)
        "04/01/2024": None,    # None
        "05/01/2024": pd.NA,   # Pandas NA
        "06/01/2024": float('nan'), # Float NaN
        "07/01/2024": "invalid", # Invalid string
        # "08/01/2024": -5, # Example: Negative value handling (currently stored as is)
    }
    parser._add_device_readings(device, readings_dict)

    history_map = {r.date.strftime("%Y-%m-%d"): r.reading for r in device.history}

    assert history_map["2024-01-01"] == 10.0
    assert history_map["2024-01-02"] == 15.7
    assert history_map["2024-01-03"] == 20.5
    assert history_map["2024-01-04"] is None
    assert history_map["2024-01-05"] is None
    assert history_map["2024-01-06"] is None
    assert history_map["2024-01-07"] is None
    # assert history_map["2024-01-08"] is None # If negative values are treated as None
