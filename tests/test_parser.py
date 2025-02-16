"""Tests for Excel parser functionality."""

from datetime import datetime, timezone
from io import BytesIO

import pytest

from pycalista_ista import ColdWaterDevice, HeatingDevice, HotWaterDevice
from pycalista_ista.excel_parser import ExcelParser
from pycalista_ista.exception_classes import ParserError


def test_header_normalization():
    """Test Excel header normalization."""
    excel_parser = ExcelParser(BytesIO(b""))
    headers = [
        "Tipo",
        "N° Serie",
        "Nº Serie",
        "Ubicación",
        "1º Lectura",
        "26/11",
        "25/11",
    ]
    normalized = excel_parser._normalize_headers(headers)

    assert normalized == [
        "tipo",
        "n_serie",
        "n_serie",
        "ubicacion",
        "1_lectura",
        "26/11",
        "25/11",
    ]


def test_device_type_creation():
    """Test device type detection and creation."""
    excel_parser = ExcelParser(BytesIO(b""))

    # Test heating device
    device = excel_parser._create_device(
        "Distribuidor de Costes de Calefacción", "12345", "Location"
    )
    assert isinstance(device, HeatingDevice)

    # Test hot water device
    device = excel_parser._create_device("Radio agua caliente", "12345", "Location")
    assert isinstance(device, HotWaterDevice)

    # Test cold water device
    device = excel_parser._create_device("Radio agua fría", "12345", "Location")
    assert isinstance(device, ColdWaterDevice)

    # Test unknown device type
    device = excel_parser._create_device("Unknown Type", "12345", "Location")
    assert device is None


def test_fill_missing_readings():
    """Test filling of missing readings."""
    excel_parser = ExcelParser(BytesIO(b""))
    rows = [
        {
            "tipo": "Heating",
            "n_serie": "12345",
            "ubicacion": "Location",
            "27/12": 10,
            "28/12": "",
            "29/12": 30,
        }
    ]
    headers = ["tipo", "n_serie", "ubicacion", "27/12", "28/12", "29/12"]

    filled_rows = excel_parser._fill_missing_readings(rows, headers)
    print(filled_rows)
    assert filled_rows[0]["28/12"] == 30  # Should fill with next available value


@pytest.mark.parametrize(
    "excel_file,expected_devices,year",
    [
        (
            "data/consulta_2023-12-29_2024-01-02.xls",
            11,
            2024,
        ),  # Short range, empty water readings
        (
            "data/consulta_2024-11-30_2025-01-01.xls",
            11,
            2025,
        ),  # Long range, all devices
        (
            "data/consulta_2025-01-10_2025-01-25.xls",
            11,
            2025,
        ),  # Missing readings in some devices
    ],
    indirect=["excel_file"],
)
def test_get_consumption_data(
    excel_file: str, expected_devices: int, year: int
) -> None:
    """Test parsing of consumption data from Excel files."""
    excel_parser = ExcelParser(io_file=excel_file, current_year=year)
    history = excel_parser.get_devices_history()
    # Test device count

    assert len(history) == expected_devices

    # Test device types
    assert isinstance(history["141740872"], HeatingDevice)  # Cocina1
    assert isinstance(history["141740957"], HeatingDevice)  # Dormitorio1
    assert isinstance(history["414293326"], ColdWaterDevice)  # Agua fría
    assert isinstance(history["414306286"], HotWaterDevice)  # Agua caliente

    # Test locations
    assert history["141740872"].location == "(1-Cocina1)"
    assert history["141740957"].location == "(2-Dormitorio1)"

    # Test readings are ordered chronologically
    for device in history.values():
        if device.history:
            dates = [reading.date for reading in device.history]
            assert dates == sorted(dates)

    # Test missing readings are handled
    dormitorio2 = history["141740933"]  # Has missing reading in 2023-12-29
    assert all(reading.reading >= 0 for reading in dormitorio2.history)

    # Test water meter readings
    cold_water = history["414293326"]
    hot_water = history["414306286"]
    assert all(reading.reading >= 0 for reading in cold_water.history)
    assert all(reading.reading >= 0 for reading in hot_water.history)


def test_parser_empty_file(tmp_path):
    """Test parser behavior with empty file."""
    empty_file = BytesIO(b"")
    parser = ExcelParser(empty_file)

    with pytest.raises(ParserError):
        parser.get_devices_history()


def test_parser_invalid_file():
    """Test parser behavior with invalid file."""
    invalid_file = BytesIO(b"not an excel file")
    parser = ExcelParser(invalid_file)

    with pytest.raises(ParserError):
        parser.get_devices_history()


def test_parser_missing_required_columns():
    """Test parser behavior with missing required columns."""
    # Create a minimal Excel file with missing required columns
    import xlwt

    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Sheet1")

    # Add headers without required columns
    headers = ["some_column", "another_column"]  # Missing tipo, n_serie, ubicacion
    for col, header in enumerate(headers):
        sheet.write(0, col, header)

    # Write to BytesIO
    excel_data = BytesIO()
    workbook.save(excel_data)
    excel_data.seek(0)

    # Test with missing required columns
    excel_parser = ExcelParser(excel_data)
    with pytest.raises(ParserError):
        excel_parser.get_devices_history()


def test_parser_date_handling():
    """Test date parsing and year handling."""
    excel_parser = ExcelParser(BytesIO(b""), current_year=2025)

    # Test date parsing with current year
    date = excel_parser._parse_reading_date("15/01/2025")
    assert date.year == 2025
    assert date.month == 1
    assert date.day == 15
    assert date.tzinfo == timezone.utc


def test_parser_reading_value_handling():
    """Test reading value parsing and validation."""
    excel_parser = ExcelParser(BytesIO(b""))
    device = HeatingDevice("12345", "Test")

    # Test valid readings
    readings = {
        "03/01/2025": 20,
        "02/01/2025": "15.7",
        "01/01/2025": "10,5",
    }
    excel_parser._add_device_readings(device, readings)

    print(device.history)

    assert len(device.history) == 3
    assert device.history[0].reading == 10.5
    assert device.history[1].reading == 15.7
    assert device.history[2].reading == 20.0


def test_add_year_to_dates():
    """Test year addition to date headers."""
    excel_parser = ExcelParser(BytesIO(b""), current_year=2024)

    # Test headers with metadata and dates in decreasing order
    headers = [
        "tipo",
        "n_serie",
        "ubicacion",
        "15/01",  # Should be 2024
        "01/01",  # Should be 2024
        "15/12",  # Should be 2023 since it's a lower month after higher months
    ]

    processed_headers = excel_parser._add_year_to_dates(headers)

    # Verify metadata columns remain unchanged
    assert processed_headers[0] == "tipo"
    assert processed_headers[1] == "n_serie"
    assert processed_headers[2] == "ubicacion"

    # Verify date headers get correct years
    assert processed_headers[3] == "15/01/2024"
    assert processed_headers[4] == "01/01/2024"
    assert processed_headers[5] == "15/12/2023"  # Previous year due to month decrease
