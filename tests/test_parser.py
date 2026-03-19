"""Tests for Excel parser functionality."""

from io import BytesIO

import pandas as pd  # Import pandas for creating test dataframes
import pytest

from pycalista_ista import ColdWaterDevice, HeatingDevice, HotWaterDevice
from pycalista_ista.excel_parser import ExcelParser
from pycalista_ista.exception_classes import IstaParserError


def test_header_normalization():
    """Test Excel header normalization."""
    parser = ExcelParser(BytesIO(b""), 2024)  # Provide dummy IO and year
    headers = [
        "Tipo",
        "N° Serie",
        "Nº Serie",
        "Ubicación",
        "1º Lectura",
        "26/11",
        " 25/11 ",
        "Agua Fría",
        "Distribuidor de Costes de Calefacción",
    ]
    normalized = parser._normalize_headers(headers)
    assert normalized == [
        "tipo",
        "n_serie",
        "n_serie",
        "ubicacion",
        "1_lectura",
        "26/11",
        "25/11",
        "agua_fria",
        "distribuidor_de_costes_de_calefaccion",
    ]
    # Test with non-string header
    assert parser._normalize_headers([123, "Header 2"]) == [
        "unknown_header_0",
        "header_2",
    ]


def test_assign_years_to_date_headers():
    """Test date header normalisation: dd/mm/yy -> dd/mm/yyyy."""
    parser = ExcelParser(BytesIO(b""), current_year=2026)
    headers = [
        "tipo",
        "n_serie",
        "ubicacion",
        "unidad_medida",
        "15/01/26",
        "01/01/26",
        "15/12/25",
        "01/12/25",
    ]
    processed = parser._assign_years_to_date_headers(headers)
    assert processed == [
        "tipo",
        "n_serie",
        "ubicacion",
        "unidad_medida",
        "15/01/2026",
        "01/01/2026",
        "15/12/2025",
        "01/12/2025",
    ]

    # Metadata-only row passes through unchanged
    assert parser._assign_years_to_date_headers(["tipo", "n_serie"]) == [
        "tipo",
        "n_serie",
    ]

    # Invalid date format raises
    with pytest.raises(IstaParserError, match="Unexpected header format: '15-01-2024'"):
        parser._assign_years_to_date_headers(["tipo", "15-01-2024"])


def test_device_type_creation():
    """Test device type detection and creation from normalized strings."""
    parser = ExcelParser(BytesIO(b""), 2024)
    # Use normalized type strings
    assert isinstance(
        parser._create_device("distribuidor de costes de calefaccion", "1", "L"),
        HeatingDevice,
    )
    assert isinstance(
        parser._create_device("radio agua caliente", "2", "L"), HotWaterDevice
    )
    assert isinstance(
        parser._create_device("radio agua fria", "3", "L"), ColdWaterDevice
    )
    assert parser._create_device("unknown type", "4", "L") is None


@pytest.mark.parametrize(
    "excel_file_content, expected_devices, expected_serials",
    [
        ("consulta_2023-12-29_2024-01-02.xls", 11, ["141740872", "414293326"]),
        ("consulta_2024-11-30_2025-01-01.xls", 11, ["141740872", "414293326"]),
        ("consulta_2025-01-10_2025-01-25.xls", 11, ["141740872", "414293326"]),
    ],
    indirect=["excel_file_content"],
)
def test_get_devices_history_from_file(
    excel_file_content: str,
    expected_devices: int,
    expected_serials: list[str],
):
    """Test parsing full consumption data from real Excel files."""
    parser = ExcelParser(io_file=BytesIO(excel_file_content))
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
            assert dates == sorted(
                dates
            ), f"Device {device.serial_number} readings not sorted"
            assert all(
                r.reading is None or isinstance(r.reading, (int, float))
                for r in device.history
            )


def test_parser_invalid_file_format():
    """Test parser behavior with non-Excel file."""
    invalid_file = BytesIO(b"this is not an excel file")
    parser = ExcelParser(invalid_file, 2024)
    with pytest.raises(IstaParserError, match="Failed to read Excel file"):
        parser.get_devices_history()


def test_parser_none_io_file():
    """ExcelParser raises ValueError when io_file is None."""
    with pytest.raises(ValueError, match="io_file cannot be None"):
        ExcelParser(None, 2024)


def test_parser_invalid_year_too_low():
    """ExcelParser raises IstaParserError for years below 1900."""
    with pytest.raises(IstaParserError, match="Invalid current_year"):
        ExcelParser(BytesIO(b""), 1899)


def test_parser_invalid_year_too_high():
    """ExcelParser raises IstaParserError for years above 2099."""
    with pytest.raises(IstaParserError, match="Invalid current_year"):
        ExcelParser(BytesIO(b""), 2100)


def test_parser_year_defaults_to_current():
    """ExcelParser uses the current year when current_year is not supplied."""
    from datetime import datetime

    parser = ExcelParser(BytesIO(b""))
    assert parser.current_year == datetime.now().year


def test_parser_non_string_headers_get_placeholder():
    """Non-string header values are replaced with a placeholder."""
    parser = ExcelParser(BytesIO(b""), 2024)
    result = parser._normalize_headers([None, 42, ["list"]])
    assert result[0] == "unknown_header_0"
    assert result[1] == "unknown_header_1"
    assert result[2] == "unknown_header_2"


def test_parser_empty_excel_returns_empty_dict():
    """A valid Excel file with no data rows returns an empty device dict."""
    from io import BytesIO

    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    # Write only the header row – no data
    for col, header in enumerate(["Tipo", "Nº Serie", "Ubicación", "01/01/24"]):
        ws.write(0, col, header)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    parser = ExcelParser(buf, 2024)
    result = parser.get_devices_history()
    assert result == {}


def test_parser_unknown_device_type_returns_none():
    """_create_device returns None for unrecognised type strings."""
    parser = ExcelParser(BytesIO(b""), 2024)
    assert parser._create_device("thermostat", "SN1", "L1") is None


def test_parser_duplicate_serial_in_file():
    """Duplicate serial numbers in the same file are merged, not duplicated."""
    # Build a minimal in-memory Excel with two rows for the same serial
    from io import BytesIO

    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    headers = ["Tipo", "Nº Serie", "Ubicación", "01/01/24", "02/01/24"]
    for col, h in enumerate(headers):
        ws.write(0, col, h)
    # Two rows with the same serial number
    for row in range(1, 3):
        ws.write(row, 0, "Distribuidor de Costes de Calefacción")
        ws.write(row, 1, "DUPL001")
        ws.write(row, 2, "Kitchen")
        ws.write(row, 3, 100.0)
        ws.write(row, 4, 110.0)

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    parser = ExcelParser(buf, 2024)
    devices = parser.get_devices_history()

    assert "DUPL001" in devices
    # Readings should not be duplicated
    dates = [r.date for r in devices["DUPL001"].history]
    assert len(dates) == len(set(dates))


def test_parser_reading_value_handling():
    """Test parsing various reading value formats."""
    parser = ExcelParser(BytesIO(b""), 2024)
    device = HeatingDevice("123", "Test")
    readings_dict = {
        "01/01/2024": 10,  # Integer
        "02/01/2024": "15.7",  # String float (dot)
        "03/01/2024": "20,5",  # String float (comma)
        "04/01/2024": None,  # None
        "05/01/2024": pd.NA,  # Pandas NA
        "06/01/2024": float("nan"),  # Float NaN
        "07/01/2024": "invalid",  # Invalid string
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


# ---------------------------------------------------------------------------
# InvoiceXlsParser
# ---------------------------------------------------------------------------


def _make_invoice_xls(rows: list[tuple]) -> "BytesIO":
    """Build a minimal invoice XLS in memory using xlwt."""
    import xlwt

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    for col, header in enumerate(["Fecha lectura", "Tipo equipo", "Importe"]):
        ws.write(0, col, header)
    for r, (date_str, device_type, amount) in enumerate(rows, start=1):
        ws.write(r, 0, date_str)
        ws.write(r, 1, device_type)
        ws.write(r, 2, amount)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_invoice_xls_parser_basic():
    """InvoiceXlsParser returns Invoice objects with correct fields."""
    from datetime import date

    from pycalista_ista.invoice_xls_parser import InvoiceXlsParser
    from pycalista_ista.models.invoice import Invoice

    buf = _make_invoice_xls(
        [
            ("31/01/2026", "Radio Distribuidor de Costes de Calefacción", "80,12"),
            ("30/01/2026", "Agua caliente", "17,33"),
        ]
    )
    invoices = InvoiceXlsParser().parse(buf)

    assert len(invoices) == 2
    assert all(isinstance(inv, Invoice) for inv in invoices)
    assert invoices[0].invoice_id is None
    assert invoices[0].invoice_date == date(2026, 1, 31)
    assert invoices[0].amount == pytest.approx(80.12)
    assert invoices[0].device_type == "Radio Distribuidor de Costes de Calefacción"
    assert invoices[1].amount == pytest.approx(17.33)


def test_invoice_xls_parser_missing_required_column():
    """IstaParserError is raised when a required column is absent."""
    import xlwt

    from pycalista_ista.invoice_xls_parser import InvoiceXlsParser

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    ws.write(0, 0, "Tipo equipo")  # missing Fecha lectura and Importe
    ws.write(1, 0, "Calefacción")
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    with pytest.raises(IstaParserError, match="missing required columns"):
        InvoiceXlsParser().parse(buf)


def test_invoice_xls_parser_skips_bad_rows():
    """Rows with unparseable dates are silently skipped."""
    from pycalista_ista.invoice_xls_parser import InvoiceXlsParser

    buf = _make_invoice_xls(
        [
            ("not-a-date", "Calefacción", "10,00"),
            ("28/02/2025", "Calefacción", "50,00"),
        ]
    )
    invoices = InvoiceXlsParser().parse(buf)
    assert len(invoices) == 1
    assert invoices[0].amount == pytest.approx(50.0)


def test_invoice_xls_parser_invalid_bytes():
    """IstaParserError is raised for non-Excel content."""
    from pycalista_ista.invoice_xls_parser import InvoiceXlsParser

    with pytest.raises(IstaParserError):
        InvoiceXlsParser().parse(BytesIO(b"not-an-excel-file"))
