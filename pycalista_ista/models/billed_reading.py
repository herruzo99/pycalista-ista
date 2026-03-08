"""Billed consumption reading model for Ista Calista."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..const import INCIDENCE_NAMES


@dataclass(frozen=True)
class BilledReading:
    """A single billed meter reading from the Mis Consumos section.

    Represents one invoicing-period reading for a specific device, as
    returned by the GestionLecturasBusqueda export.

    Attributes:
        serial_number: Device serial number.
        device_type: Normalised device type string.
        location: Device location description.
        reading_id: Unique server-side reading identifier.
        date: Date the reading was taken (end of billing period).
        incidence: Incidence code (e.g. "4700"=Sin incidencia, "47A4"=Estimado,
            "47AA"=Arranque automático, "4741"=Contador nuevo).
        unit: Unit of measurement (e.g. "UN", "m3").
        previous_reading: Previous meter reading value.
        current_reading: Current meter reading value.
        consumption: Billed consumption (current - previous).
    """

    serial_number: str
    device_type: str
    location: str
    reading_id: int
    date: date
    incidence: str
    unit: str
    previous_reading: float
    current_reading: float
    consumption: float

    @property
    def is_estimated(self) -> bool:
        """Return True if the reading was estimated rather than measured."""
        return self.incidence == "47A4"

    @property
    def incidence_name(self) -> str:
        """Human-readable incidence label, or the raw code if unknown."""
        return INCIDENCE_NAMES.get(self.incidence, self.incidence)

    def __repr__(self) -> str:
        return (
            f"<BilledReading SN={self.serial_number} date={self.date}"
            f" consumption={self.consumption} unit={self.unit}>"
        )
