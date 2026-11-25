"""Tests for the billed consumption (Mis Consumos) XLS parser."""

from io import BytesIO

import pytest
import xlwt

from pycalista_ista.consumption_parser import ConsumptionParser
from pycalista_ista.exception_classes import IstaParserError

# Column headers as the ista portal returned them before ~October 2026.
OLD_HEADERS = [
    "nº serie",
    "tipo equipo",
    "ubicación",
    "id lectura",
    "fecha",
    "incidencia",
    "unidad medida",
    "lectura anterior",
    "lectura actual",
    "consumo",
]

# Since ~October 2026 the portal renamed the two reading columns.
NEW_HEADERS = [
    "nº serie",
    "tipo equipo",
    "ubicación",
    "id lectura",
    "fecha",
    "incidencia",
    "unidad medida",
    "lectura anterior facturada",
    "lectura facturada",
    "consumo",
]


def _make_xls(headers: list[str], rows: list[tuple]) -> BytesIO:
    """Build a minimal .xls billed-consumption export in memory."""
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    for col, header in enumerate(headers):
        ws.write(0, col, header)
    for r, row in enumerate(rows, start=1):
        for col, value in enumerate(row):
            ws.write(r, col, value)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


ROWS = [
    (
        "141740872",
        "Radio Distribuidor de Costes de Calefacción",
        "(1-Cocina1)",
        900001,
        "31/01/2026",
        "",
        "Unidades",
        120.0,
        135.0,
        15.0,
    ),
    (
        "414293326",
        "Radio Agua Fría",
        "(1-Baño)",
        900002,
        "30/01/2026",
        "",
        "m3",
        210.5,
        215.0,
        4.5,
    ),
]


def test_parse_old_column_names():
    """The export with the original column names still parses."""
    readings = ConsumptionParser().parse(_make_xls(OLD_HEADERS, ROWS))

    assert len(readings) == 2
    by_serial = {r.serial_number: r for r in readings}
    assert by_serial["141740872"].previous_reading == pytest.approx(120.0)
    assert by_serial["141740872"].current_reading == pytest.approx(135.0)
    assert by_serial["414293326"].previous_reading == pytest.approx(210.5)
    assert by_serial["414293326"].consumption == pytest.approx(4.5)


def test_parse_renamed_column_names():
    """The export with 'lectura anterior facturada' / 'lectura facturada' parses.

    Regression test for ista-calista#4: the portal renamed these two columns
    and billed consumption stopped updating.
    """
    readings = ConsumptionParser().parse(_make_xls(NEW_HEADERS, ROWS))

    assert len(readings) == 2
    by_serial = {r.serial_number: r for r in readings}
    assert by_serial["141740872"].previous_reading == pytest.approx(120.0)
    assert by_serial["141740872"].current_reading == pytest.approx(135.0)
    assert by_serial["141740872"].consumption == pytest.approx(15.0)
    assert by_serial["414293326"].previous_reading == pytest.approx(210.5)
    assert by_serial["414293326"].current_reading == pytest.approx(215.0)


def test_renamed_columns_do_not_duplicate_old_ones():
    """A file with both spellings keeps the original columns."""
    headers = OLD_HEADERS + ["lectura anterior facturada", "lectura facturada"]
    rows = [row + (999.0, 999.0) for row in ROWS]
    readings = ConsumptionParser().parse(_make_xls(headers, rows))

    by_serial = {r.serial_number: r for r in readings}
    assert by_serial["141740872"].previous_reading == pytest.approx(120.0)
    assert by_serial["141740872"].current_reading == pytest.approx(135.0)


def test_parse_missing_readings_column_raises():
    """A file without any reading column still raises IstaParserError."""
    headers = [
        h
        for h in NEW_HEADERS
        if h not in ("lectura anterior facturada", "lectura facturada")
    ]
    with pytest.raises(IstaParserError, match="missing required columns"):
        ConsumptionParser().parse(_make_xls(headers, []))


def test_parse_invalid_bytes_raises():
    """A non-Excel payload raises IstaParserError."""
    with pytest.raises(IstaParserError, match="Failed to read billed consumption"):
        ConsumptionParser().parse(BytesIO(b"not an excel file"))


def test_parse_skips_rows_without_serial():
    """Rows with '_' as serial are skipped, as before."""
    rows = [
        ("_", "Radio Agua Fría", "(1)", 1, "30/01/2026", "", "m3", 1.0, 2.0, 1.0)
    ] + ROWS
    readings = ConsumptionParser().parse(_make_xls(NEW_HEADERS, rows))

    assert len(readings) == 2
    assert all(r.serial_number != "_" for r in readings)


def test_decimal_comma_and_thousands_separator():
    """A Spanish-locale cell ('1.234,5') parses as 1234.5."""
    row = list(ROWS[0])
    row[7] = "1.234,5"   # lectura anterior
    row[8] = "1.240,5"   # lectura actual
    row[9] = "6,0"       # consumo
    parser = ConsumptionParser()
    readings = parser.parse(_make_xls(OLD_HEADERS, [tuple(row)]))
    assert len(readings) == 1
    assert readings[0].previous_reading == 1234.5
    assert readings[0].current_reading == 1240.5
    assert readings[0].consumption == 6.0


def test_empty_numeric_cell_drops_the_row():
    """A blank or NaN reading is not a zero: the row is skipped."""
    row = list(ROWS[0])
    row[8] = None        # lectura actual sin valor
    parser = ConsumptionParser()
    assert parser.parse(_make_xls(OLD_HEADERS, [tuple(row)])) == []


def test_empty_consumption_is_derived_from_the_readings():
    """An incidence row with both readings but no consumo is kept, not dropped."""
    row = list(ROWS[0])
    row[9] = None        # consumo vacío
    parser = ConsumptionParser()
    readings = parser.parse(_make_xls(OLD_HEADERS, [tuple(row)]))
    assert len(readings) == 1
    assert readings[0].consumption == readings[0].current_reading - readings[0].previous_reading


def test_english_thousands_separator():
    """'1,234.5' is one thousand two hundred, not one point two three four."""
    row = list(ROWS[0])
    row[7] = "1,234.5"
    row[8] = "1,240.5"
    row[9] = "6.0"
    parser = ConsumptionParser()
    readings = parser.parse(_make_xls(OLD_HEADERS, [tuple(row)]))
    assert readings[0].previous_reading == 1234.5
    assert readings[0].consumption == 6.0
