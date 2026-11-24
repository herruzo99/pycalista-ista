"""Portal account model for linked Ista Calista properties."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PortalAccount:
    """A property linked to the authenticated login.

    One email and password can have more than one linked property (for
    example a flat and a parking space). The portal selector identifies
    each property with an opaque ID that only makes sense for the current
    session.

    Attributes:
        account_id: Opaque property ID from the portal selector. Use it with
            :meth:`PyCalistaIsta.select_account` or the ``account_id``
            constructor argument.
        label: Human-readable property name shown by the portal.
    """

    account_id: str
    label: str
