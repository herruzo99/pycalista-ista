"""Tests for the linked-property selector HTML parser."""

from pycalista_ista.account_parser import AccountParser
from pycalista_ista.models import PortalAccount

ACCOUNT_A = "9f3c1a77b2e4d001"
ACCOUNT_B = "4b8e2d55c9a1f022"
LABEL_A = "Calle Mayor 1, 2ºA"
LABEL_B = "Garaje Calle Mayor 1"


def test_account_parser_ignores_separators_and_duplicate_ids():
    """Placeholders, separators and repeated IDs are not properties."""
    html = (
        "<html><body><select name='idAbonado'>"
        '<option value="">Seleccione un abonado</option>'
        '<option value="----">--------</option>'
        '<option disabled value="frozen">Bloqueado</option>'
        f'<option value="{ACCOUNT_A}">{LABEL_A}</option>'
        f'<option value="{ACCOUNT_A}">{LABEL_A} (repetido)</option>'
        f'<option value="{ACCOUNT_B}" selected>{LABEL_B}</option>'
        "</select></body></html>"
    )

    accounts = AccountParser().parse_accounts(html)

    assert accounts == [
        PortalAccount(account_id=ACCOUNT_A, label=LABEL_A),
        PortalAccount(account_id=ACCOUNT_B, label=LABEL_B),
    ]


def test_account_parser_without_selector_returns_empty():
    """A page without the selector lists no properties."""
    assert AccountParser().parse_accounts("<html><body>Sin abonado</body></html>") == []
    assert AccountParser().selected_account_id("<html><body></body></html>") is None


def test_account_parser_reads_selected_option():
    """The selected option value is returned; separators are skipped."""
    html = (
        "<html><body><select name='idAbonado'>"
        '<option value="">Seleccione</option>'
        f'<option value="{ACCOUNT_B}" selected>{LABEL_B}</option>'
        "</select></body></html>"
    )

    assert AccountParser().selected_account_id(html) == ACCOUNT_B


def test_effective_account_id_uses_first_usable_option_as_default():
    """Without a selected attribute, the first usable option is effective.

    Separator options come before it and are not properties, so they are not
    the default (this is the live single-property shape after a switch).
    """
    html = (
        "<html><body><select name='idAbonado'>"
        '<option value="">Seleccione un abonado</option>'
        '<option value="----">--------</option>'
        '<option disabled value="frozen">Bloqueado</option>'
        f'<option value="{ACCOUNT_A}">{LABEL_A}</option>'
        "</select></body></html>"
    )

    parser = AccountParser()
    assert parser.selected_account_id(html) is None
    assert parser.effective_account_id(html) == ACCOUNT_A


def test_effective_account_id_prefers_explicit_selection():
    """An explicit selected attribute wins over the first usable option."""
    html = (
        "<html><body><select name='idAbonado'>"
        f'<option value="{ACCOUNT_A}">{LABEL_A}</option>'
        f'<option value="{ACCOUNT_B}" selected>{LABEL_B}</option>'
        "</select></body></html>"
    )

    assert AccountParser().effective_account_id(html) == ACCOUNT_B


def test_effective_account_id_without_selector_is_none():
    """A page without usable properties has no effective selection."""
    assert AccountParser().effective_account_id("<html><body></body></html>") is None
    assert (
        AccountParser().effective_account_id(
            "<html><body><select name='idAbonado'>"
            '<option value="">Seleccione</option>'
            "</select></body></html>"
        )
        is None
    )
