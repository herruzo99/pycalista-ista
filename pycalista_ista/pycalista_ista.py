"""Main client for the Ista Calista API.

This module provides the main client class for interacting with the
Ista Calista virtual office API. It handles authentication, session
management, and data retrieval.

Example:
    ```python
    client = PyCalistaIsta("user@example.com", "password")
    client.login()

    # Get device readings for the last 30 days
    devices = client.get_devices_history(
        start=date.today() - timedelta(days=30)
    )

    for device in devices.values():
        print(f"{device}: {device.last_reading}")
    ```
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Final

from .__version import __version__
from .exception_classes import LoginError
from .models import Device
from .virtual_api import VirtualApi

_LOGGER: Final = logging.getLogger(__name__)

# Default time ranges
DEFAULT_HISTORY_DAYS: Final[int] = 30


class PyCalistaIsta:
    """Client for interacting with the Ista Calista API.

    This class provides high-level methods for authenticating with
    and retrieving data from the Ista Calista virtual office.

    Attributes:
        _email: Email address for authentication
        _password: Password for authentication
        _virtual_api: Low-level API client instance
    """

    def __init__(
        self,
        email: str,
        password: str,
    ) -> None:
        """Initialize the client.

        Args:
            email: Email address for authentication
            password: Password for authentication

        Raises:
            ValueError: If email or password is empty
        """
        if not email or not password:
            raise ValueError("Email and password are required")

        self._email: str = email.strip()
        self._password: str = password
        self._virtual_api = VirtualApi(
            username=self._email,
            password=self._password,
        )

    def get_account(self) -> str:
        """Get the account email address.

        Returns:
            The authenticated account's email address
        """
        return self._email

    def get_version(self) -> str:
        """Get the client version.

        Returns:
            Current version string
        """
        return __version__

    def get_devices_history(
        self,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Device]:
        """Get historical readings for all devices.

        Args:
            start: Start date for history (defaults to DEFAULT_HISTORY_DAYS ago)
            end: End date for history (defaults to today)

        Returns:
            Dictionary mapping device serial numbers to Device objects

        Raises:
            LoginError: If not authenticated
            ValueError: If start date is after end date
        """
        start = start or date.today() - timedelta(days=DEFAULT_HISTORY_DAYS)
        end = end or date.today()

        if start > end:
            raise ValueError("Start date must be before end date")

        try:
            return self._virtual_api.get_devices_history(start, end)
        except Exception as err:
            _LOGGER.error("Failed to get device history: %s", err)
            raise

    def login(self) -> bool:
        """Authenticate with the Ista Calista API.

        Returns:
            True if login successful

        Raises:
            LoginError: If authentication fails
        """
        try:
            self._virtual_api.login()
            return True
        except Exception as err:
            _LOGGER.error("Login failed: %s", err)
            raise LoginError(f"Failed to authenticate: {err}") from err
