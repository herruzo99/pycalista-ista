"""HTML parser for the Ista Calista linked-property selector.

The portal renders the properties linked to a login in a ``<select>``
element named ``idAbonado``. Every authenticated page contains that
selector, but this parser only uses the read-only radio preload page
(``metodo=preCargaLecturasRadio``), which lists the linked properties and
marks the currently selected one.

Property IDs and labels are personal data. This module never logs them.
"""

from __future__ import annotations

import logging
from typing import Final

from bs4 import BeautifulSoup, Tag

from .models.portal_account import PortalAccount

_LOGGER: Final = logging.getLogger(__name__)

# Name (and id) of the property selector in the portal HTML
ACCOUNT_SELECT_NAME: Final = "idAbonado"


class AccountParser:
    """Parser for the linked-property selector of the Ista Calista portal."""

    def _find_select(self, soup: BeautifulSoup) -> Tag | None:
        """Return the property ``<select>`` element, or None."""
        select = soup.find("select", attrs={"name": ACCOUNT_SELECT_NAME})
        if isinstance(select, Tag):
            return select
        select = soup.find("select", attrs={"id": ACCOUNT_SELECT_NAME})
        if isinstance(select, Tag):
            return select
        return None

    @staticmethod
    def _clean_option(option: Tag) -> tuple[str, str] | None:
        """Return ``(value, label)`` for a usable option, or None.

        Placeholder and separator options are rejected: they have an empty
        value, a disabled attribute, an empty label, or a label without any
        letter or digit (for example ``"-----"``).
        """
        if option.has_attr("disabled"):
            return None
        value = str(option.get("value") or "").strip()
        label = option.get_text(strip=True)
        if not value or not label:
            return None
        if not any(char.isalnum() for char in value):
            return None
        if not any(char.isalnum() for char in label):
            return None
        return value, label

    def parse_accounts(self, html: str) -> list[PortalAccount]:
        """Extract the linked properties from the portal HTML.

        Separator options are ignored and repeated IDs are deduplicated
        (the first label wins). The order of the portal is preserved.

        Args:
            html: Raw HTML of an authenticated portal page.

        Returns:
            List of PortalAccount objects. Empty if the page has no selector.
        """
        soup = BeautifulSoup(html, "html.parser")
        select = self._find_select(soup)
        if select is None:
            _LOGGER.debug("No linked-property selector found in the page.")
            return []

        accounts: list[PortalAccount] = []
        seen: set[str] = set()
        for option in select.find_all("option"):
            if not isinstance(option, Tag):
                continue
            cleaned = self._clean_option(option)
            if cleaned is None:
                continue
            value, label = cleaned
            if value in seen:
                continue
            seen.add(value)
            accounts.append(PortalAccount(account_id=value, label=label))

        _LOGGER.debug("Parsed %d linked property option(s).", len(accounts))
        return accounts

    def selected_account_id(self, html: str) -> str | None:
        """Return the opaque ID of the option marked as selected.

        Args:
            html: Raw HTML of an authenticated portal page.

        Returns:
            The value of the ``selected`` option, or None if the page has no
            selector or no option is marked as selected.
        """
        soup = BeautifulSoup(html, "html.parser")
        select = self._find_select(soup)
        if select is None:
            return None
        for option in select.find_all("option"):
            if not isinstance(option, Tag) or not option.has_attr("selected"):
                continue
            cleaned = self._clean_option(option)
            if cleaned is None:
                return None
            return cleaned[0]
        return None
