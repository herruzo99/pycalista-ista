"""XLS parser for Ista Calista invoice history (Mis Recibos export).

Parses the Excel export from GestionFacturacion.do?metodo=listadoRecibos.
The file has three columns: Fecha lectura, Tipo equipo, Importe.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import IO, Final

import pandas as pd

from .exception_classes import IstaParserError
from .models.invoice import Invoice

_LOGGER: Final = logging.getLogger(__name__)

_COL_DATE = "fecha lectura"
_COL_TYPE = "tipo equipo"
_COL_AMOUNT = "importe"

_REQUIRED_COLS: Final[frozenset[str]] = frozenset({_COL_DATE, _COL_AMOUNT})


class InvoiceXlsParser:
    """Parser for the Ista Calista invoice history XLS export."""

    def parse(self, io_file: IO[bytes]) -> list[Invoice]:
        """Parse the invoice history XLS and return a list of Invoice objects.

        The XLS export contains only date, device type and amount — no invoice ID.
        Returned objects have invoice_id="" since that field is not present in the file.

        Args:
            io_file: File-like object containing the XLS data.

        Returns:
            List of Invoice objects sorted by date descending (newest first).

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
            raise IstaParserError(f"Failed to read invoice XLS file: {err}") from err

        df.columns = [str(c).strip().lower() for c in df.columns]

        missing = _REQUIRED_COLS - set(df.columns)
        if missing:
            raise IstaParserError(
                f"Invoice XLS missing required columns: {missing}. "
                f"Found: {df.columns.tolist()}"
            )

        invoices: list[Invoice] = []
        skipped = 0

        for _, row in df.iterrows():
            invoice = self._parse_row(row)
            if invoice is None:
                skipped += 1
            else:
                invoices.append(invoice)

        _LOGGER.info("Parsed %d invoice XLS rows (%d skipped).", len(invoices), skipped)
        return invoices

    def _parse_row(self, row: pd.Series) -> Invoice | None:
        try:
            date_val = row.get(_COL_DATE, "")
            if pd.isna(date_val):
                return None
            if isinstance(date_val, str):
                invoice_date = datetime.strptime(date_val.strip(), "%d/%m/%Y").date()
            else:
                invoice_date = pd.Timestamp(date_val).date()

            amount_raw = row.get(_COL_AMOUNT, "")
            amount: float | None = None
            if not pd.isna(amount_raw):
                amount = float(
                    str(amount_raw).replace("€", "").replace(",", ".").strip()
                )

            device_type_raw = row.get(_COL_TYPE, "")
            device_type = (
                str(device_type_raw).strip() if not pd.isna(device_type_raw) else None
            )

            return Invoice(
                invoice_id=None,
                invoice_date=invoice_date,
                amount=amount,
                device_type=device_type,
            )
        except Exception as err:
            _LOGGER.warning("Skipping invoice XLS row due to error: %s", err)
            return None
