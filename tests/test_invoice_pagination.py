"""Tests for invoice-list pagination in VirtualApi and PyCalistaIsta."""

import re

import pytest
from aioresponses import CallbackResult, aioresponses

from pycalista_ista import PyCalistaIsta
from pycalista_ista.const import DATA_URL, INVOICES_URL, MAX_INVOICE_PAGES
from pycalista_ista.virtual_api import VirtualApi
from tests.conftest import TEST_EMAIL, TEST_PASSWORD, mock_login_success

pytestmark = pytest.mark.asyncio

FIRST_PAGE_PATTERN = re.compile(re.escape(INVOICES_URL) + r"\?metodo=buscarRecibos")
PAGE_PATTERN = re.compile(
    r"https://oficina\.ista\.es/GesCon/GestionFacturacion\.do\?.*d-148657-p=\d+.*"
)
PRELOAD_PATTERN = re.compile(re.escape(DATA_URL) + r".*preCargaLecturasRadio.*")


def invoice_row(invoice_id: str, day: int = 1) -> str:
    """Return one synthetic invoice table row, shaped like the portal."""
    return (
        f"<tr><td>{day:02d}/02/2026</td><td>Radio agua fría</td>"
        f"<td>80,12 €</td>"
        '<td><a href="GestionFacturacion.do?d-148657-e=2'
        f'&idRecibo={invoice_id}&metodo=duplicarReciboIndividualCalista">'
        "PDF</a></td></tr>"
    )


def anchor(page: int, label: str | None = None) -> str:
    """Return one synthetic paging anchor."""
    return (
        f'<a href="GestionFacturacion.do?d-148657-p={page}'
        f'&metodo=listadoRecibos&metodo=buscarRecibos">'
        f"{label or str(page)}</a>"
    )


def pager(*pages: int) -> str:
    """Return numbered paging anchors for the given page numbers."""
    return " ".join(anchor(page) for page in pages)


def listing_html(rows: str = "", pager_html: str = "") -> str:
    """Return a synthetic invoice listing page."""
    return (
        "<html><body><form name='listaRecibos'><table class='table'><tbody>"
        f"{rows}</tbody></table>"
        f"<table class='paginador'><tr><td>{pager_html}</td></tr></table>"
        "</form></body></html>"
    )


def mock_page_responses(mock_resp: aioresponses, pages: list[str]) -> None:
    """Register one response per page, in request order."""
    mock_resp.get(FIRST_PAGE_PATTERN, status=200, body=pages[0], repeat=False)
    for body in pages[1:]:
        mock_resp.get(PAGE_PATTERN, status=200, body=body, repeat=False)


async def test_get_invoices_single_page(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """A listing without paging anchors is read once."""
    mock_page_responses(mock_responses, [listing_html(rows=invoice_row("AAA111"))])

    invoices = await ista_api_client.get_invoices()

    assert [invoice.invoice_id for invoice in invoices] == ["AAA111"]
    assert len(mock_responses.requests) == 1


async def test_get_invoices_follows_all_pages_and_deduplicates(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """Three pages are read; an ID repeated across pages appears once."""
    page1 = listing_html(
        rows=invoice_row("AAA111", 1) + invoice_row("BBB222", 2),
        pager_html=anchor(2, "&gt;") + " " + pager(1, 2, 3),
    )
    page2 = listing_html(
        rows=invoice_row("BBB222", 2) + invoice_row("CCC333", 3),
        pager_html=anchor(3, "&gt;") + " " + pager(1, 2, 3),
    )
    page3 = listing_html(rows=invoice_row("DDD444", 4), pager_html=pager(1, 2, 3))
    mock_page_responses(mock_responses, [page1, page2, page3])

    invoices = await ista_api_client.get_invoices()

    assert [invoice.invoice_id for invoice in invoices] == [
        "AAA111",
        "BBB222",
        "CCC333",
        "DDD444",
    ]
    assert len(mock_responses.requests) == 3


async def test_get_invoices_stops_on_repeated_url(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """A paging anchor that points back to a read page ends the loop."""
    page1 = listing_html(rows=invoice_row("AAA111"), pager_html=anchor(2, "&gt;"))
    # The ">" anchor of page 2 points back to page 2 itself.
    page2 = listing_html(rows=invoice_row("BBB222"), pager_html=anchor(2, "&gt;"))
    mock_page_responses(mock_responses, [page1, page2])

    invoices = await ista_api_client.get_invoices()

    assert [invoice.invoice_id for invoice in invoices] == ["AAA111", "BBB222"]
    assert len(mock_responses.requests) == 2


async def test_get_invoices_caps_the_number_of_pages(
    ista_api_client: VirtualApi, mock_responses: aioresponses
):
    """Pagination stops at MAX_INVOICE_PAGES even if the portal never ends."""
    requested_pages: list[int] = []

    def next_page_callback(url, **kwargs):
        match = re.search(r"d-148657-p=(\d+)", str(url))
        page = int(match.group(1)) if match else 1
        requested_pages.append(page)
        body = listing_html(
            rows=invoice_row(f"INV{page:05d}", 1),
            pager_html=anchor(page + 1, "&gt;"),
        )
        return CallbackResult(
            status=200, body=body, content_type="text/html; charset=UTF-8"
        )

    mock_responses.get(
        FIRST_PAGE_PATTERN,
        callback=next_page_callback,
        repeat=True,
    )
    mock_responses.get(PAGE_PATTERN, callback=next_page_callback, repeat=True)

    invoices = await ista_api_client.get_invoices()

    assert len(requested_pages) == MAX_INVOICE_PAGES
    assert len(invoices) == MAX_INVOICE_PAGES
    assert requested_pages[0] == 1
    assert requested_pages[-1] == MAX_INVOICE_PAGES


async def test_facade_get_invoices_paginates(
    ista_main_client: PyCalistaIsta,
    mock_responses: aioresponses,
):
    """The public facade returns the invoices of every page."""
    page1 = listing_html(
        rows=invoice_row("AAA111", 1) + invoice_row("BBB222", 2),
        pager_html=anchor(2, "&gt;"),
    )
    page2 = listing_html(rows=invoice_row("CCC333", 3), pager_html=pager(1, 2))
    mock_page_responses(mock_responses, [page1, page2])

    invoices = await ista_main_client.get_invoices()

    assert [invoice.invoice_id for invoice in invoices] == [
        "AAA111",
        "BBB222",
        "CCC333",
    ]


async def test_get_invoices_works_after_login(
    mock_aiohttp_session, mock_responses: aioresponses
):
    """The authenticated flow still reads every page (relogin path unchanged)."""
    client = VirtualApi(
        username=TEST_EMAIL, password=TEST_PASSWORD, session=mock_aiohttp_session
    )
    mock_login_success(mock_responses)
    page1 = listing_html(rows=invoice_row("AAA111"), pager_html=anchor(2, "&gt;"))
    page2 = listing_html(rows=invoice_row("BBB222"), pager_html=pager(1, 2))
    mock_page_responses(mock_responses, [page1, page2])

    assert await client.login() is True
    invoices = await client.get_invoices()

    assert [invoice.invoice_id for invoice in invoices] == ["AAA111", "BBB222"]
