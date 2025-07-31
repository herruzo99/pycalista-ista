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
from .exception_classes import IstaApiError, IstaConnectionError, IstaLoginError
from .models import Device
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
        _close_session: Flag indicating if the session should be closed by this client.
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

        Raises:
            ValueError: If email or password is empty.
        """
        if not email or not password:
            raise ValueError("Email and password are required")

        self.account: str = email.strip()
        self._password: str = password  # Store password privately
        self._close_session = session is None  # Track if we need to close the session
        self._virtual_api = VirtualApi(
            username=self.account,
            password=self._password,
            session=session,  # Pass session to VirtualApi
        )
        _LOGGER.debug(
            "PyCalistaIsta client initialized for %s. Session will be managed internally: %s",
            self.account,
            self._close_session,
        )

    async def close(self) -> None:
        """Close the underlying API session if managed internally."""
        await self._virtual_api.close()
        _LOGGER.debug("PyCalistaIsta client for %s has been closed.", self.account)

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
