"""DataUpdateCoordinator for Ista Calista integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from .pycalista_ista import LoginError, PyCalistaIsta, ServerError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IstaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Ista Calista data update coordinator."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, ista: PyCalistaIsta) -> None:
        """Initialize ista Calista data update coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(days=1),
        )
        self.ista = ista


    # def get_consumption_data(self) -> dict[str, Any]:
    #     """Get raw json data for all consumption units."""

    #     return {
    #         consumption_unit: self.ista.get_consumption_data(consumption_unit)
    #         for consumption_unit in self.ista.get_uuids()
    #     }

    # async def async_get_details(self) -> dict[str, Any]:
    #     """Retrieve details of consumption units."""

    #     result = await self.hass.async_add_executor_job(
    #         self.ista.get_consumption_unit_details
    #     )

    #     return {
    #         consumption_unit: next(
    #             details
    #             for details in result["consumptionUnits"]
    #             if details["id"] == consumption_unit
    #         )
    #         for consumption_unit in self.ista.get_uuids()
    #     }
        
    async def _async_update_data(self):
        """Fetch ista Calista data."""

        try:
            await self.hass.async_add_executor_job(self.ista.login)
            return await self.hass.async_add_executor_job(self.ista.get_sensors_data)

        except ServerError as e:
            raise UpdateFailed(
                "Unable to connect and retrieve data from ista Calista, try again later"
            ) from e
        except (LoginError) as e:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="authentication_exception",
                translation_placeholders={
                    CONF_EMAIL: self.config_entry.data[CONF_EMAIL]
                },
            ) from e

