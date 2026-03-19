"""HTML parser for Ista Calista invoice listings.

Parses the HTML response from GestionFacturacionBuscar.do?metodo=buscarRecibos
to extract invoice metadata and server-side IDs needed to download PDFs.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Final

from bs4 import BeautifulSoup

from .exception_classes import IstaParserError
from .models.invoice import Invoice

_LOGGER: Final = logging.getLogger(__name__)

# Pattern to extract idRecibo from href attributes
_ID_RECIBO_RE: Final = re.compile(r"idRecibo=([A-Za-z0-9_=+/\-]+)")
# Invoice number pattern: digits/digits  e.g. "4448373/26"
_INVOICE_NUMBER_RE: Final = re.compile(r"^\d+/\d+$")
# Date pattern: dd/mm/yyyy
_DATE_RE: Final = re.compile(r"^\d{2}/\d{2}/\d{4}$")
# Amount pattern: digits with optional comma/dot decimal and optional € symbol
_AMOUNT_RE: Final = re.compile(r"^[\d]+[.,][\d]+\s*€?$")
# Period range pattern: "dd/mm/yyyy-dd/mm/yyyy" or "dd/mm/yyyy - dd/mm/yyyy"
_PERIOD_RE: Final = re.compile(r"(\d{2}/\d{2}/\d{4})\s*[-–]\s*(\d{2}/\d{2}/\d{4})")


class InvoiceParser:
    """Parser for the Ista Calista invoice listing HTML page."""

    def parse(self, html: str) -> list[Invoice]:
        """Parse the invoice listing HTML and return a list of Invoice objects.

        Extracts invoice IDs from download links, then correlates with table
        row data (invoice number, date, amount) via pattern matching.

        Args:
            html: Raw HTML string from the buscarRecibos endpoint.

        Returns:
            List of Invoice objects. Fields other than invoice_id may be None
            if the HTML structure does not match expected patterns.

        Raises:
            IstaParserError: If the HTML cannot be parsed at all.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as err:
            raise IstaParserError(f"Failed to parse invoice HTML: {err}") from err

        # Find every <a> whose href contains idRecibo=
        invoice_rows: dict[int, tuple[str, any]] = {}
        for link in soup.find_all("a", href=_ID_RECIBO_RE):
            href = link.get("href", "")
            match = _ID_RECIBO_RE.search(href)
            if not match:
                continue
            invoice_id = match.group(1)
            row = link.find_parent("tr")
            if row is None:
                _LOGGER.debug(
                    "Link with idRecibo=%s has no parent <tr>, skipping.", invoice_id
                )
                continue
            # Use Python object id to key uniquely on the row element
            invoice_rows[id(row)] = (invoice_id, row)

        if not invoice_rows:
            _LOGGER.warning(
                "No invoice links found in HTML. "
                "The page structure may have changed or there are no invoices."
            )
            return []

        _LOGGER.debug("Found %d invoice row(s) in HTML.", len(invoice_rows))

        invoices: list[Invoice] = []
        for invoice_id, row in invoice_rows.values():
            invoice = self._parse_row(invoice_id, row)
            invoices.append(invoice)
            _LOGGER.debug("Parsed invoice: %r", invoice)

        return invoices

    def _parse_row(self, invoice_id: str, row: any) -> Invoice:
        """Extract invoice metadata from a table row.

        Uses pattern matching against cell text — no assumption about column
        order, so it degrades gracefully if columns change.

        Args:
            invoice_id: Server-side opaque ID from the download link.
            row: BeautifulSoup Tag representing the <tr>.

        Returns:
            Invoice with as many fields populated as could be parsed.
        """
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        _LOGGER.debug("Row cells for invoice_id=%s: %s", invoice_id, cells)

        invoice_date: date | None = None
        amount: float | None = None
        device_type: str | None = None

        # The listing page table has: date | device type label | amount | (actions)
        # invoice_number and period are NOT present in the HTML — only in the PDF.
        for cell in cells:
            if not cell:
                continue

            # Date: "10/02/2026"
            if invoice_date is None and _DATE_RE.match(cell):
                try:
                    invoice_date = datetime.strptime(cell, "%d/%m/%Y").date()
                except ValueError:
                    _LOGGER.warning("Could not parse date cell: '%s'", cell)
                continue

            # Amount: "80,12" or "80,12 €"
            if amount is None and _AMOUNT_RE.match(cell):
                try:
                    amount = float(cell.replace("€", "").replace(",", ".").strip())
                except ValueError:
                    _LOGGER.warning("Could not parse amount cell: '%s'", cell)
                continue

            # Device type label (anything else that is not a date or amount)
            if (
                device_type is None
                and not _DATE_RE.match(cell)
                and not _AMOUNT_RE.match(cell)
            ):
                device_type = cell

        if amount is None:
            _LOGGER.warning(
                "Could not extract amount for idRecibo=%s. Cells: %s",
                invoice_id,
                cells,
            )

        return Invoice(
            invoice_id=invoice_id,
            invoice_date=invoice_date,
            amount=amount,
            device_type=device_type,
        )
