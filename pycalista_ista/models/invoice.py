"""Invoice model for Ista Calista billing records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Invoice:
    """A single invoice from the Ista Calista billing system.

    Attributes:
        invoice_id: Opaque server-side ID used to download the PDF.
            None for invoices sourced from the XLS export (no ID available).
        invoice_number: Human-readable invoice number (e.g. "4448373/26").
        invoice_date: Date the invoice was issued.
        period_start: Start of the billing period.
        period_end: End of the billing period.
        amount: Total amount in EUR, or None if not parsed.
    """

    invoice_id: str | None = None  # None for XLS-sourced entries (no server-side ID)
    invoice_number: str | None = None
    invoice_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    amount: float | None = None
    device_type: str | None = None  # billing category label from the listing page

    def __repr__(self) -> str:
        return (
            f"<Invoice {self.invoice_number or self.invoice_id}"
            f" date={self.invoice_date} amount={self.amount}>"
        )
