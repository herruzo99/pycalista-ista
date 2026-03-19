"""Main async client for the Ista Calista API.

Provides the main async client class for interacting with the
Ista Calista virtual office API. It handles authentication, session
management, and data retrieval using the async VirtualApi.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Final

from aiohttp import ClientSession

from .__version import __version__
from .const import LOG_LEVEL_MAP
from .exception_classes import IstaApiError, IstaConnectionError, IstaLoginError, IstaParserError
from .models import Device
from .models.billed_reading import BilledReading
from .models.invoice import Invoice
from .virtual_api import VirtualApi

_LOGGER: Final = logging.getLogger(__name__)

# Default time ranges
DEFAULT_HISTORY_DAYS: Final[int] = 30


class PyCalistaIsta:
    """Async client for interacting with the Ista Calista API.

    Provides high-level async methods for authenticating with
    and retrieving data from the Ista Calista virtual office.

    Attributes:
        account: The email address used for authentication.
        _password: Password for authentication (kept private).
        _virtual_api: Low-level async API client instance.
            Session lifecycle (create/close) is owned entirely by VirtualApi.
    """

    def __init__(
        self,
        email: str,
        password: str,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize the async client.

        Args:
            email: Email address for authentication.
            password: Password for authentication.
            session: An optional external aiohttp ClientSession.
                     If None, VirtualApi creates and owns one internally.

        Raises:
            ValueError: If email or password is empty.
        """
        if not email or not password:
            raise ValueError("Email and password are required")

        self.account: str = email.strip()
        self._password: str = password  # Store password privately
        self._virtual_api = VirtualApi(
            username=self.account,
            password=self._password,
            session=session,  # Pass session to VirtualApi; it owns the lifecycle
        )
        _LOGGER.debug(
            "PyCalistaIsta client initialized for %s.",
            self.account,
        )

    async def close(self) -> None:
        """Close the underlying API session if managed internally."""
        await self._virtual_api.close()
        _LOGGER.debug("PyCalistaIsta client for %s has been closed.", self.account)

    async def __aenter__(self) -> "PyCalistaIsta":
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        await self.close()

    def set_log_level(self, log_level: str) -> None:
        """Set the logging level for the entire pycalista_ista library.

        Args:
            log_level: The desired log level ("DEBUG", "INFO", "WARNING", "ERROR").

        Raises:
            ValueError: If the provided log_level is invalid.
        """
        level_int = LOG_LEVEL_MAP.get(log_level.upper())
        if level_int is None:
            _LOGGER.error("Invalid log level provided: '%s'", log_level)
            raise ValueError(
                f"Invalid log level: {log_level}. Must be one of {list(LOG_LEVEL_MAP.keys())}"
            )

        # Get the root logger for this package and set its level.
        # This will affect all loggers within the 'pycalista_ista' namespace.
        package_logger = logging.getLogger(__name__.split(".")[0])
        package_logger.setLevel(level_int)
        # Log at the new level to confirm it's working
        package_logger.info("pycalista_ista log level set to %s", log_level.upper())

    def get_version(self) -> str:
        """Get the client version.

        Returns:
            Current version string.
        """
        return __version__

    async def login(self) -> bool:
        """Authenticate with the Ista Calista API asynchronously.

        Returns:
            True if login successful.

        Raises:
            IstaLoginError: If authentication fails.
            IstaConnectionError: If the connection fails.
            IstaApiError: For other API errors during login.
        """
        _LOGGER.info("Attempting login for user: %s", self.account)
        try:
            # login method now returns bool, no need to check return value here
            # Exceptions will be raised on failure
            await self._virtual_api.login()
            _LOGGER.info("Login successful for user: %s", self.account)
            return True
        except IstaLoginError:
            _LOGGER.error("Login failed for user %s.", self.account)
            raise  # Re-raise specific login error
        except IstaConnectionError as err:
            _LOGGER.error(
                "Login failed for user %s due to a connection error: %s",
                self.account,
                err,
            )
            raise
        except Exception as err:
            # Catch other potential errors from VirtualApi.login
            _LOGGER.exception(
                "An unexpected error occurred during login for user %s.", self.account
            )
            # Wrap unexpected errors in a generic API error
            raise IstaApiError(
                f"An unexpected error occurred during login: {err}"
            ) from err

    async def get_devices_history(
        self,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Device]:
        """Get historical readings for all devices asynchronously.

        Args:
            start: Start date for history (defaults to DEFAULT_HISTORY_DAYS ago).
            end: End date for history (defaults to today).

        Returns:
            Dictionary mapping device serial numbers to Device objects.

        Raises:
            ValueError: If start date is after end date.
            IstaLoginError: If not authenticated or session expired.
            IstaConnectionError: If data retrieval fails due to connection issues.
            IstaParserError: If data parsing fails.
            IstaApiError: For other unexpected API errors.
        """
        start_date = start or (date.today() - timedelta(days=DEFAULT_HISTORY_DAYS))
        end_date = end or date.today()

        if start_date > end_date:
            _LOGGER.error(
                "Invalid date range provided. Start date (%s) cannot be after end date (%s).",
                start_date,
                end_date,
            )
            raise ValueError("Start date must be before or equal to end date")
        _LOGGER.info(
            "Requesting device history for %s from %s to %s",
            self.account,
            start_date.isoformat(),
            end_date.isoformat(),
        )

        try:
            # Call the async method in VirtualApi
            devices = await self._virtual_api.get_devices_history(start_date, end_date)
            _LOGGER.info(
                "Successfully retrieved and parsed history for %d device(s) for user %s.",
                len(devices),
                self.account,
            )
            return devices
        except (ValueError, IstaLoginError, IstaApiError, IstaConnectionError) as err:
            # Catch known specific errors and re-raise
            _LOGGER.error("Failed to get device history for %s: %s", self.account, err)
            raise
        except Exception as err:
            # Catch unexpected errors
            _LOGGER.exception(
                "An unexpected error occurred while getting device history for %s.",
                self.account,
            )
            raise IstaApiError(
                f"An unexpected error occurred while fetching device history: {err}"
            ) from err

    async def get_invoices(self) -> list[Invoice]:
        """Fetch the list of invoices from the portal.

        Returns:
            List of Invoice objects with metadata. Call get_invoice_pdf() to
            download the actual PDF for any invoice.

        Raises:
            IstaLoginError: If not authenticated or session expired.
            IstaConnectionError: If the request fails.
            IstaParserError: If the invoice listing page cannot be parsed.
            IstaApiError: For other unexpected errors.
        """
        _LOGGER.info("Requesting invoice list for %s.", self.account)
        try:
            invoices = await self._virtual_api.get_invoices()
            _LOGGER.info(
                "Successfully retrieved %d invoice(s) for %s.",
                len(invoices),
                self.account,
            )
            return invoices
        except (IstaLoginError, IstaConnectionError, IstaParserError) as err:
            _LOGGER.error("Failed to get invoices for %s: %s", self.account, err)
            raise
        except Exception as err:
            _LOGGER.exception(
                "An unexpected error occurred while getting invoices for %s.",
                self.account,
            )
            raise IstaApiError(
                f"An unexpected error occurred while fetching invoices: {err}"
            ) from err

    async def get_invoice_pdf(self, invoice_id: str) -> bytes:
        """Download a single invoice as raw PDF bytes.

        Args:
            invoice_id: The Invoice.invoice_id from a previously fetched Invoice.

        Returns:
            Raw PDF bytes.

        Raises:
            IstaLoginError: If not authenticated or session expired.
            IstaConnectionError: If the request fails.
            IstaApiError: If the response is not a valid PDF.
        """
        _LOGGER.info(
            "Requesting PDF for invoice_id=%s for %s.", invoice_id, self.account
        )
        try:
            pdf_bytes = await self._virtual_api.get_invoice_pdf(invoice_id)
            _LOGGER.info(
                "Successfully downloaded PDF for invoice_id=%s (%d bytes).",
                invoice_id,
                len(pdf_bytes),
            )
            return pdf_bytes
        except (IstaLoginError, IstaConnectionError, IstaApiError) as err:
            _LOGGER.error(
                "Failed to download invoice PDF %s for %s: %s",
                invoice_id,
                self.account,
                err,
            )
            raise
        except Exception as err:
            _LOGGER.exception(
                "An unexpected error occurred while downloading invoice PDF %s for %s.",
                invoice_id,
                self.account,
            )
            raise IstaApiError(
                f"An unexpected error occurred while downloading invoice PDF: {err}"
            ) from err

    async def get_invoice_xls(self) -> list[Invoice]:
        """Fetch the full invoice history from the XLS export (Mis Recibos → Excel).

        Returns the complete invoice history as parsed from the Excel export.
        Entries have invoice_id="" since the XLS does not include server-side IDs.

        Returns:
            List of Invoice objects from the XLS export.

        Raises:
            IstaLoginError: If not authenticated or session expired.
            IstaConnectionError: If a request fails.
            IstaParserError: If the XLS cannot be parsed.
        """
        _LOGGER.info("Requesting invoice XLS for %s.", self.account)
        try:
            invoices = await self._virtual_api.get_invoice_xls()
            _LOGGER.info(
                "Successfully retrieved %d invoice XLS row(s) for %s.",
                len(invoices),
                self.account,
            )
            return invoices
        except (IstaLoginError, IstaConnectionError, IstaParserError) as err:
            _LOGGER.error("Failed to get invoice XLS for %s: %s", self.account, err)
            raise
        except Exception as err:
            _LOGGER.exception(
                "An unexpected error occurred while getting invoice XLS for %s.",
                self.account,
            )
            raise IstaApiError(
                f"An unexpected error occurred while fetching invoice XLS: {err}"
            ) from err

    async def get_billed_consumption(self) -> list[BilledReading]:
        """Fetch all billed consumption readings (Mis Consumos).

        Returns the full history of invoiced readings for every device,
        as opposed to the daily radio readings from get_devices_history().

        Returns:
            List of BilledReading objects, newest first.

        Raises:
            IstaLoginError: If not authenticated or session expired.
            IstaConnectionError: If a request fails.
            IstaParserError: If the XLS cannot be parsed.
            IstaApiError: If the export link cannot be found or other API error.
        """
        _LOGGER.info("Requesting billed consumption for %s.", self.account)
        try:
            readings = await self._virtual_api.get_billed_consumption()
            _LOGGER.info(
                "Successfully retrieved %d billed reading(s) for %s.",
                len(readings),
                self.account,
            )
            return readings
        except (
            IstaLoginError,
            IstaConnectionError,
            IstaApiError,
            IstaParserError,
        ) as err:
            _LOGGER.error(
                "Failed to get billed consumption for %s: %s", self.account, err
            )
            raise
        except Exception as err:
            _LOGGER.exception(
                "An unexpected error occurred while getting billed consumption for %s.",
                self.account,
            )
            raise IstaApiError(
                f"An unexpected error occurred while fetching billed consumption: {err}"
            ) from err
