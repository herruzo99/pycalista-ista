"""HTML parser for Ista Calista invoice listings.

Parses the HTML response from GestionFacturacionBuscar.do?metodo=buscarRecibos
to extract invoice metadata and server-side IDs needed to download PDFs.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Final
from urllib.parse import urljoin

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

# Portal table paging. The listing page numbers its pages with a display-tag
# parameter such as "d-148657-p=2". The display-tag number is not stable, so
# the parser matches any "d-<number>-p=<page>" pair.
_PAGE_PARAM_RE: Final = re.compile(r"[?&;]d-\d+-p=(\d+)")
# Sort/target selectors: "d-<number>-o=<n>" orders the table and
# "d-<number>-e=<n>" selects the export format. They are not page links.
_SELECTOR_PARAM_RE: Final = re.compile(r"[?&;]d-\d+-[oet]=")
# Anchors that jump more than one page
_MULTI_PAGE_LABELS: Final = frozenset({">>", "<<", ">>|", "|<<", "»", "«"})


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

    def next_page_url(self, html: str, current_url: str) -> str | None:
        """Return the URL of the next invoice-list page, or None.

        The listing page publishes paging anchors whose href contains
        ``metodo=listadoRecibos`` and a ``d-<number>-p=<page>`` parameter.
        The exact ``>`` anchor wins. Otherwise the unique anchor that points
        to ``current_page + 1`` is used. Anchors that jump several pages
        (``>>``), sort links, and export links are ignored.

        Args:
            html: Raw HTML of the current invoice listing page.
            current_url: URL of the current page, used to resolve relative
                hrefs and to read the current page number.

        Returns:
            Absolute URL of the next page, or None on the last page or when
            the next page cannot be identified without ambiguity.

        Raises:
            IstaParserError: If the HTML cannot be parsed at all.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as err:
            raise IstaParserError(f"Failed to parse invoice HTML: {err}") from err

        current_page = self._page_number(current_url) or 1
        exact_next: str | None = None
        candidates: set[str] = set()

        for link in soup.find_all("a", href=True):
            href = str(link.get("href", "")).strip()
            if not href or "listadoRecibos" not in href:
                continue
            if _SELECTOR_PARAM_RE.search(href):
                continue
            page = self._page_number(href)
            if page is None:
                continue
            label = link.get_text(strip=True)
            if label in _MULTI_PAGE_LABELS:
                continue
            url = urljoin(current_url, href)
            if label == ">" and exact_next is None:
                exact_next = url
            if page == current_page + 1:
                candidates.add(url)

        if exact_next is not None:
            return exact_next
        if len(candidates) == 1:
            return next(iter(candidates))
        if len(candidates) > 1:
            _LOGGER.debug(
                "Invoice pagination is ambiguous: %d candidate next pages.",
                len(candidates),
            )
        return None

    @staticmethod
    def _page_number(url: str) -> int | None:
        """Return the paging number of a URL, or None when it has none."""
        match = _PAGE_PARAM_RE.search(url)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:  # pragma: no cover - regex only matches digits
            return None

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
