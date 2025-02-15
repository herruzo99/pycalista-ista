"""Tests for Excel parser functionality."""

from datetime import datetime, timezone
from io import BytesIO
import pytest

from pycalista_ista.exception_classes import ParserError
from pycalista_ista.excel_parser import ExcelParser
from pycalista_ista import HeatingDevice, HotWaterDevice, ColdWaterDevice


def test_header_normalization():
    """Test Excel header normalization."""
    excel_parser = ExcelParser(BytesIO(b""))
    headers = ["Tipo", "N° Serie", "Ubicación", "1º Lectura", "2ª Lectura"]
    normalized = excel_parser._normalize_headers(headers)

    assert normalized == ["tipo", "n_serie", "ubicacion", "1_lectura", "2_lectura"]


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
            "1_lectura": 10,
            "2_lectura": "",
            "3_lectura": 30,
        }
    ]
    headers = ["tipo", "n_serie", "ubicacion", "1_lectura", "2_lectura", "3_lectura"]

    filled_rows = excel_parser._fill_missing_readings(rows, headers)
    assert filled_rows[0]["2_lectura"] == 30  # Should fill with next available value


@pytest.mark.parametrize(
    "excel_file", ["data/consulta_2025-01-10_2025-01-25.xls"], indirect=True
)
def test_get_consumption_data(excel_file: str) -> None:
    """Test parsing of consumption data from Excel file."""
    excel_parser = ExcelParser(io_file=excel_file, current_year=2025)
    history = excel_parser.get_devices_history()

    # Test device types and counts
    assert len(history) == 5
    assert isinstance(history[1], HeatingDevice)
    assert isinstance(history[2], HeatingDevice)
    assert isinstance(history[3], HeatingDevice)
    assert isinstance(history[10], ColdWaterDevice)
    assert isinstance(history[11], HotWaterDevice)

    # Test device details
    assert history[1].location == "(1-Cocina1)"
    assert len(history[1].history) == 27
    assert history[1].last_consumption == 1
    assert history[1].last_reading == 27

    assert len(history[2].history) == 27
    assert history[2].last_consumption == 0
    assert history[2].last_reading == 0


def test_parser_empty_file(tmp_path):
    """Test parser behavior with empty file."""
    empty_file = BytesIO(b"")
    parser = ExcelParser(empty_file)

    with pytest.raises(ParserError, match="File content is empty"):
        parser.get_devices_history()


def test_parser_invalid_file():
    """Test parser behavior with invalid file."""
    invalid_file = BytesIO(b"not an excel file")
    parser = ExcelParser(invalid_file)

    with pytest.raises(ParserError, match="Failed to parse Excel file"):
        parser.get_devices_history()


def test_parser_missing_required_columns():
    """Test parser behavior with missing required columns."""
    # Create a minimal Excel-like data with missing required columns
    from xlrd.sheet import Sheet
    from xlrd import Book
    import xlrd

    # Create workbook and sheet
    book = Book()
    sheet = book.add_sheet("Sheet1")

    # Add headers without required columns
    headers = ["some_column", "another_column"]  # Missing tipo, n_serie, ubicacion
    for col, header in enumerate(headers):
        sheet.write(0, col, header)

    # Write to BytesIO
    excel_data = BytesIO()
    book.save(excel_data)
    excel_data.seek(0)

    # Test with missing required columns
    excel_parser = ExcelParser(excel_data)
    with pytest.raises(ParserError, match="Missing required columns"):
        excel_parser.get_devices_history()


def test_parser_date_handling():
    """Test date parsing and year handling."""
    excel_parser = ExcelParser(BytesIO(b""), current_year=2025)

    # Test date parsing with current year
    date = excel_parser._parse_reading_date("15/01", None, 2024, False)
    assert date.year == 2025
    assert date.month == 1
    assert date.day == 15
    assert date.tzinfo == timezone.utc

    # Test date parsing with previous year flag
    date = excel_parser._parse_reading_date(
        "15/01", datetime(2025, 12, 1, tzinfo=timezone.utc), 2024, True
    )
    assert date.year == 2024


def test_parser_reading_value_handling():
    """Test reading value parsing and validation."""
    excel_parser = ExcelParser(BytesIO(b""))
    device = HeatingDevice("12345", "Test")

    # Test valid readings
    readings = {
        "01/01": "10,5",
        "02/01": "15.7",
        "03/01": 20,
    }
    excel_parser._add_device_readings(device, readings)

    assert len(device.history) == 3
    assert device.history[0].reading == 10.5
    assert device.history[1].reading == 15.7
    assert device.history[2].reading == 20.0
