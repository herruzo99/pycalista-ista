"""API client for Ista Calista virtual office.

This module provides a client for interacting with the Ista Calista virtual office web interface.
It handles authentication, session management, and data retrieval for utility consumption readings.

The client supports:
- Authentication with username/password
- Session management with automatic cookie handling
- Retrieval of historical consumption data
- Parsing of Excel-format reading data
- Handling of rate limits and server errors
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import io
import logging
from typing import Final, TypeVar
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import RequestException

from .const import DATA_URL, LOGIN_URL, USER_AGENT
from .excel_parser import ExcelParser
from .exception_classes import LoginError

_LOGGER = logging.getLogger(__name__)

# Type variable for device history dictionaries
DeviceDict = TypeVar("DeviceDict", bound=dict)

# Constants
MAX_RETRIES: Final = 5
RETRY_BACKOFF: Final = 1
RETRY_STATUS_CODES: Final = [408, 429, 502, 503, 504]
MAX_DAYS_PER_REQUEST: Final = 240
EXCEL_CONTENT_TYPE: Final = "application/vnd.ms-excel;charset=iso-8859-1"
DATE_FORMAT: Final = "%d/%m/%Y"


class VirtualApi:
    """Client for the Ista Calista virtual office API.

    This class handles all interactions with the Ista Calista web interface,
    including authentication, session management, and data retrieval.

    Attributes:
        username: The username for authentication
        password: The password for authentication
        session: The requests Session object for making HTTP requests
        cookies: Dictionary of session cookies

    Example:
        ```python
        api = VirtualApi("user@example.com", "password")
        api.login()
        history = api.get_devices_history(
            start=date(2024, 1, 1),
            end=date(2024, 2, 1)
        )
        ```
    """

    def __init__(
        self,
        username: str,
        password: str,
    ) -> None:
        """Initialize the API client.

        Args:
            username: The username for authentication
            password: The password for authentication
        """
        self.username: str = username
        self.password: str = password
        self.cookies: dict[str, str] = {}

        # Set up session with retry handling
        self.session = requests.Session()
        self.session.verify = True
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=RETRY_STATUS_CODES,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry_strategy))

    def _send_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        """Send an HTTP request with the session.

        Args:
            method: The HTTP method to use
            url: The URL to send the request to
            **kwargs: Additional arguments to pass to requests.request()

        Returns:
            The response from the server

        Raises:
            ValueError: If the session is not initialized
            RequestException: If the request fails
        """
        if self.session is None:
            raise ValueError("Session object is not initialized")

        try:
            response = self.session.request(method, url, **kwargs)
            _LOGGER.debug(
                "Performed %s request: %s [%s]:\n%s",
                method,
                url,
                response.status_code,
                response.text[:100],
            )
            response.raise_for_status()
            return response

        except RequestException as err:
            _LOGGER.error("Request failed: %s", err)
            raise

    def relogin(self) -> None:
        """Clear cookies and perform a fresh login."""
        self.cookies = {}
        self.login()

    def login(self) -> None:
        """Authenticate with the Ista Calista virtual office.

        This method performs the login process and stores the session cookies
        for subsequent requests.

        Raises:
            LoginError: If authentication fails
            RequestException: If the request fails
        """
        if self.cookies:
            _LOGGER.debug("Using existing cookies")
            return

        headers = {"User-Agent": USER_AGENT}
        data = {
            "metodo": "loginAbonado",
            "loginName": self.username,
            "password": self.password,
        }

        try:
            response = self._send_request("POST", LOGIN_URL, headers=headers, data=data)
            self._preload_reading_metadata()

            if response.headers.get("Content-Length") is not None:
                raise LoginError("Login failed - invalid credentials")

            self.cookies = response.cookies.get_dict()

        except RequestException as err:
            raise LoginError(f"Login request failed: {err}") from err

    def get_devices_history(
        self,
        start: date,
        end: date,
    ) -> dict:
        """Get historical consumption data for all devices.

        Args:
            start: Start date for the history period
            end: End date for the history period

        Returns:
            Dictionary mapping device serial numbers to device objects with history
        """
        current_year_file_buffer = self._get_readings(start, end)
        device_lists = []

        for current_year, file in current_year_file_buffer:
            parser = ExcelParser(file, current_year)
            devices = parser.get_devices_history()
            device_lists.append(devices)

        return self.merge_device_histories(device_lists)

    def merge_device_histories(self, device_lists: list[DeviceDict]) -> DeviceDict:
        """Merge device histories from multiple time periods.

        This method combines historical readings from different time periods
        into a single consolidated history for each device.

        Args:
            device_lists: List of dictionaries containing device histories

        Returns:
            Dictionary with merged device histories
        """
        merged_devices: DeviceDict = {}

        for device_list in device_lists:
            for serial_number, device in device_list.items():
                if serial_number not in merged_devices:
                    merged_devices[serial_number] = device
                else:
                    existing_device = merged_devices[serial_number]
                    for reading in device.history:
                        existing_device.add_reading(reading)

        return merged_devices

    def _preload_reading_metadata(self) -> None:
        """Preload reading metadata required for subsequent requests.

        The Ista Calista API requires this preliminary request before
        allowing download of reading data.

        Raises:
            RequestException: If the request fails
        """
        headers = {"User-Agent": USER_AGENT}
        params = {"metodo": "preCargaLecturasRadio"}

        self._send_request(
            "GET",
            DATA_URL,
            headers=headers,
            cookies=self.cookies,
            params=params,
        )

    def _get_readings_chunk(
        self,
        start: datetime,
        end: datetime,
        max_days: int = MAX_DAYS_PER_REQUEST,
    ) -> io.BytesIO:
        """Get readings for a specific date range chunk.

        Args:
            start: Start date for the chunk
            end: End date for the chunk
            max_days: Maximum number of days per request

        Returns:
            BytesIO object containing the Excel data

        Raises:
            ValueError: If the date range exceeds max_days
            RequestException: If the request fails
        """
        delta_days = (end - start).days
        if delta_days > max_days:
            raise ValueError(
                f"Date range exceeds maximum {max_days} days: {delta_days} days"
            )

        params = {
            "d-4360165-e": "2",  # 2=xlsx format
            "fechaHastaRadio": quote(end.strftime(DATE_FORMAT)),
            "metodo": "listadoLecturasRadio",
            "fechaDesdeRadio": quote(start.strftime(DATE_FORMAT)),
            "6578706f7274": "1",
        }

        headers = {"User-Agent": USER_AGENT}

        try:
            response = self._send_request(
                "GET",
                DATA_URL,
                headers=headers,
                cookies=self.cookies,
                params=params,
            )

            content_type = response.headers.get("Content-Type", "")
            if EXCEL_CONTENT_TYPE not in content_type:
                if "text/html" in content_type:
                    _LOGGER.debug("Session expired, attempting relogin")
                    self.relogin()
                    response = self._send_request(
                        "GET",
                        DATA_URL,
                        headers=headers,
                        cookies=self.cookies,
                        params=params,
                    )
                else:
                    raise RequestException(f"Unexpected content type: {content_type}")

            return io.BytesIO(response.content)

        except RequestException as err:
            _LOGGER.error("Failed to get readings chunk: %s", err)
            raise

    def _get_readings(
        self,
        start: datetime = date.today() - timedelta(days=30),
        end: datetime = date.today(),
        max_days: int = MAX_DAYS_PER_REQUEST,
    ) -> list[tuple[int, io.BytesIO]]:
        """Get all readings within a date range, splitting into chunks as needed.

        Args:
            start: Start date for readings
            end: End date for readings
            max_days: Maximum days per chunk request

        Returns:
            List of tuples containing (year, file_buffer) for each chunk
        """
        file_buffers = []
        current_start = start

        while current_start < end:
            current_end = min(current_start + timedelta(days=max_days), end)

            try:
                file_buffer = self._get_readings_chunk(current_start, current_end)
                file_buffers.append((current_end.year, file_buffer))
            except RequestException as err:
                _LOGGER.error(
                    "Failed to get readings for %s to %s: %s",
                    current_start,
                    current_end,
                    err,
                )
                raise

            current_start = current_end

        return file_buffers
