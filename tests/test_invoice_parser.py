"""Tests for the invoice listing HTML parser and its paging anchors."""

import pytest

from pycalista_ista.invoice_parser import InvoiceParser

FIRST_PAGE_URL = (
    "https://oficina.ista.es/GesCon/GestionFacturacionBuscar.do?metodo=buscarRecibos"
)
SECOND_PAGE_URL = (
    "https://oficina.ista.es/GesCon/GestionFacturacion.do"
    "?d-148657-p=2&metodo=listadoRecibos&metodo=buscarRecibos"
)


def invoice_row(invoice_id: str, day: int = 1) -> str:
    """Return one synthetic invoice table row, shaped like the portal."""
    return (
        f"<tr><td>{day:02d}/02/2026</td><td>Radio agua fría</td>"
        f"<td>80,12 €</td>"
        '<td><a href="GestionFacturacion.do?d-148657-e=2'
        f'&idRecibo={invoice_id}&metodo=duplicarReciboIndividualCalista">'
        "PDF</a></td></tr>"
    )


def listing_html(rows: str = "", pager: str = "") -> str:
    """Return a synthetic invoice listing page."""
    return (
        "<html><body><form name='listaRecibos'><table class='table'>"
        "<thead><tr><th>Fecha lectura</th><th>Tipo equipo</th>"
        "<th>Importe</th><th>Descargar</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<table class='paginador'><tr><td>{pager}</td></tr></table>"
        "</form></body></html>"
    )


def page_anchor(page: int, label: str = "") -> str:
    """Return a synthetic paging anchor."""
    text = label or str(page)
    return (
        f'<a href="GestionFacturacion.do?d-148657-p={page}'
        f'&metodo=listadoRecibos&metodo=buscarRecibos">{text}</a>'
    )


def test_parse_extracts_invoice_id_date_and_amount():
    """The listing parser keeps the existing Invoice shape."""
    html = listing_html(invoice_row("ABC123", day=10))

    invoices = InvoiceParser().parse(html)

    assert len(invoices) == 1
    assert invoices[0].invoice_id == "ABC123"
    assert invoices[0].invoice_date.isoformat() == "2026-02-10"
    assert invoices[0].amount == pytest.approx(80.12)
    assert invoices[0].device_type == "Radio agua fría"


def test_parse_without_links_returns_empty_list():
    """A page without invoice links returns no invoices."""
    assert InvoiceParser().parse(listing_html()) == []


def test_next_page_url_prefers_exact_next_anchor():
    """The exact '>' anchor wins over the numbered anchors and '>>'."""
    pager = " ".join(
        [
            page_anchor(1),
            page_anchor(2, ">"),
            page_anchor(3, "&gt;&gt;"),
            page_anchor(4),
        ]
    )

    url = InvoiceParser().next_page_url(listing_html(pager=pager), FIRST_PAGE_URL)

    assert url == (
        "https://oficina.ista.es/GesCon/GestionFacturacion.do"
        "?d-148657-p=2&metodo=listadoRecibos&metodo=buscarRecibos"
    )


def test_next_page_url_ignores_multi_page_anchor_and_uses_fallback():
    """Without a '>' anchor, the unique current-page+1 anchor is used."""
    pager = " ".join(
        [
            page_anchor(1),
            page_anchor(2),
            page_anchor(3, "&gt;&gt;"),
        ]
    )

    url = InvoiceParser().next_page_url(listing_html(pager=pager), FIRST_PAGE_URL)

    assert url is not None
    assert "d-148657-p=2" in url
    assert "listadoRecibos" in url


def test_next_page_url_ignores_sort_links():
    """Sort selectors are not page links, even with a page parameter."""
    pager = (
        '<a href="GestionFacturacion.do?d-148657-o=2&d-148657-p=2'
        '&metodo=listadoRecibos&metodo=buscarRecibos">Importe</a>'
    )

    assert (
        InvoiceParser().next_page_url(listing_html(pager=pager), FIRST_PAGE_URL) is None
    )


def test_next_page_url_returns_none_on_last_page():
    """A page that only links to earlier pages has no next page."""
    pager = " ".join([page_anchor(1), page_anchor(2)])

    assert (
        InvoiceParser().next_page_url(listing_html(pager=pager), SECOND_PAGE_URL)
        is None
    )


def test_next_page_url_returns_none_when_ambiguous():
    """Two different candidates for the next page are not guessed."""
    pager = (
        '<a href="GestionFacturacion.do?d-148657-p=2'
        '&metodo=listadoRecibos&metodo=buscarRecibos">2</a>'
        '<a href="OtraPagina.do?d-148657-p=2'
        '&metodo=listadoRecibos&metodo=buscarRecibos">2</a>'
    )

    assert (
        InvoiceParser().next_page_url(listing_html(pager=pager), FIRST_PAGE_URL) is None
    )


def test_next_page_url_without_pager_returns_none():
    """A one-page listing has no paging anchors."""
    html = listing_html(rows=invoice_row("ABC123"))

    assert InvoiceParser().next_page_url(html, FIRST_PAGE_URL) is None


def test_next_page_url_uses_current_page_from_url():
    """The current page number comes from the current URL."""
    pager = " ".join([page_anchor(1), page_anchor(2), page_anchor(3)])

    url = InvoiceParser().next_page_url(listing_html(pager=pager), SECOND_PAGE_URL)

    assert url is not None
    assert "d-148657-p=3" in url
