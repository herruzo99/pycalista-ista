"""XLS parser for Ista Calista billed consumption (Mis Consumos).

Parses the Excel export from GestionLecturasBusqueda.do?metodo=buscarLecturas.
Unlike the radio readings parser, this file has proper named column headers
so parsing is straightforward.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import IO, Final

import pandas as pd

from .exception_classes import IstaParserError
from .models.billed_reading import BilledReading

_LOGGER: Final = logging.getLogger(__name__)

# Normalised column names after lowercasing and stripping (Spanish, as returned by the API)
_COL_SERIAL = "nº serie"
_COL_TYPE = "tipo equipo"
_COL_LOCATION = "ubicación"
_COL_ID = "id lectura"
_COL_DATE = "fecha"
_COL_INCIDENCE = "incidencia"
_COL_UNIT = "unidad medida"
_COL_PREV = "lectura anterior"
_COL_CURR = "lectura actual"
_COL_CONSUMPTION = "consumo"

_REQUIRED_COLS: Final[frozenset[str]] = frozenset({
    _COL_SERIAL, _COL_TYPE, _COL_DATE,
    _COL_PREV, _COL_CURR, _COL_CONSUMPTION,
})


class ConsumptionParser:
    """Parser for the Ista Calista billed consumption XLS export."""

    def parse(self, io_file: IO[bytes]) -> list[BilledReading]:
        """Parse the billed consumption XLS and return a list of BilledReading objects.

        Rows with invalid serial numbers (e.g. "_") are silently skipped.

        Args:
            io_file: File-like object containing the XLS data.

        Returns:
            List of BilledReading objects sorted by date descending (newest first).

        Raises:
            IstaParserError: If the file cannot be read or required columns are missing.
        """
        try:
            io_file.seek(0)
            magic = io_file.read(4)
            io_file.seek(0)
            engine = "openpyxl" if magic[:2] == b"PK" else "xlrd"
            df = pd.read_excel(io_file, engine=engine)
        except Exception as err:
            raise IstaParserError(
                f"Failed to read billed consumption Excel file: {err}"
            ) from err

        # Normalise column names
        df.columns = [str(c).strip().lower() for c in df.columns]

        missing = _REQUIRED_COLS - set(df.columns)
        if missing:
            raise IstaParserError(
                f"Billed consumption file missing required columns: {missing}. "
                f"Found: {df.columns.tolist()}"
            )

        readings: list[BilledReading] = []
        skipped = 0

        for _, row in df.iterrows():
            reading = self._parse_row(row)
            if reading is None:
                skipped += 1
            else:
                readings.append(reading)

        _LOGGER.info(
            "Parsed %d billed readings (%d rows skipped).", len(readings), skipped
        )
        return readings

    def _parse_row(self, row: pd.Series) -> BilledReading | None:
        serial = str(row.get(_COL_SERIAL, "")).strip()
        if not serial or serial == "_":
            return None

        try:
            date_val = row.get(_COL_DATE, "")
            if pd.isna(date_val):
                return None
            if isinstance(date_val, str):
                reading_date = datetime.strptime(date_val.strip(), "%d/%m/%Y").replace(
                    tzinfo=timezone.utc
                ).date()
            else:
                # pandas may parse it as a datetime already
                reading_date = pd.Timestamp(date_val).date()

            reading_id_raw = row.get(_COL_ID, 0)
            reading_id = int(reading_id_raw) if not pd.isna(reading_id_raw) else 0

            return BilledReading(
                serial_number=serial,
                device_type=str(row.get(_COL_TYPE, "")).strip(),
                location=str(row.get(_COL_LOCATION, "")).strip()
                if not pd.isna(row.get(_COL_LOCATION, ""))
                else "",
                reading_id=reading_id,
                date=reading_date,
                incidence=str(row.get(_COL_INCIDENCE, "")).strip()
                if not pd.isna(row.get(_COL_INCIDENCE, ""))
                else "",
                unit=str(row.get(_COL_UNIT, "")).strip()
                if not pd.isna(row.get(_COL_UNIT, ""))
                else "",
                previous_reading=float(row.get(_COL_PREV, 0) or 0),
                current_reading=float(row.get(_COL_CURR, 0) or 0),
                consumption=float(row.get(_COL_CONSUMPTION, 0) or 0),
            )
        except Exception as err:
            _LOGGER.warning("Skipping billed reading row due to error: %s", err)
            return None
