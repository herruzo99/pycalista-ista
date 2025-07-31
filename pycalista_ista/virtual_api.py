"""API client for Ista Calista virtual office (Async).

This module provides an async client for interacting with the Ista Calista
virtual office web interface using aiohttp. It handles authentication,
session management, and data retrieval for utility consumption readings.
"""

from __future__ import annotations

import asyncio
import io
import logging
from datetime import date, timedelta
from typing import Any, Final, TypeVar
from urllib.parse import quote

import aiohttp
from aiohttp import ClientError, ClientResponseError, ClientSession
from yarl import URL

from .const import DATA_URL, LOGIN_URL, USER_AGENT
from .excel_parser import ExcelParser
from .exception_classes import (
    IstaApiError,
    IstaConnectionError,
    IstaLoginError,
    IstaParserError,
)
from .models import Device

_LOGGER = logging.getLogger(__name__)
# Type variable for device history dictionaries
DeviceDict = TypeVar("DeviceDict", bound=dict[str, Device])

# Constants
MAX_RETRIES: Final = 2
RETRY_BACKOFF: Final = 2
RETRY_STATUS_CODES: Final = {408, 429, 502, 503, 504}
MAX_DAYS_PER_REQUEST: Final = 240
EXCEL_CONTENT_TYPE: Final = "application/vnd.ms-excel;charset=iso-8859-1"
DATE_FORMAT: Final = "%d/%m/%Y"
REQUEST_TIMEOUT: Final = 30  # seconds


class VirtualApi:
    """Async client for the Ista Calista virtual office API.

    Handles interactions with the Ista Calista web interface using aiohttp.

    Attributes:
        username: The username for authentication.
        password: The password for authentication.
        session: The aiohttp ClientSession for making HTTP requests.
        _close_session: Flag indicating if the session was created internally.
    """

    def __init__(
        self,
        username: str,
        password: str,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize the async API client.

        Args:
            username: The username for authentication.
            password: The password for authentication.
            session: An optional external aiohttp ClientSession.
                     If None, a new session is created internally.
        """
        self.username: str = username
        self.password: str = password
        self._close_session: bool = session is None
        self.session: ClientSession = session or aiohttp.ClientSession(
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        )
        self._login_lock = asyncio.Lock()  # Prevent concurrent login attempts

    async def close(self) -> None:
        """Close the underlying aiohttp session if created internally."""
        if self._close_session and self.session and not self.session.closed:
            await self.session.close()

    async def _send_request(
        self,
        method: str,
        url: str | URL,
        retry_attempts: int = MAX_RETRIES,
        relogin: bool = True,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Send an HTTP request with the session, including retry logic.

        Args:
            method: The HTTP method (e.g., "GET", "POST").
            url: The URL to send the request to.
            retry_attempts: Number of retry attempts left.
            **kwargs: Additional arguments for session.request().

        Returns:
            The aiohttp ClientResponse.

        Raises:
            IstaConnectionError: If the request fails after retries.
            IstaLoginError: If a request fails due to expired session after relogin attempt.
        """
        _LOGGER.debug(
            "Sending request: Method=%s, URL=%s, Retries left=%d, Params/Data=%s",
            method,
            url,
            retry_attempts,
            kwargs.get("params") or kwargs.get("data"),
        )

        if self.session is None or self.session.closed:
            _LOGGER.error("Cannot send request, session is closed.")
            raise IstaConnectionError("Session is closed")

        try:
            response = await self.session.request(method, url, **kwargs)
            response_text_snippet = (await response.text())[:250].replace("\n", "")
            _LOGGER.debug(
                "Received response: Status=%s, Content-Type=%s, URL=%s, Snippet=%s",
                response.status,
                response.headers.get("Content-Type"),
                response.url,
                response_text_snippet,
            )

            # Check for potential session expiry/redirect to login page
            # This check might need adjustment based on actual redirect behavior
            if response.status == 200:
                # Heuristic: If we get HTML back on an API call, it might be the login page
                response_text = await response.text()
                if (
                    "GestionOficinaVirtual.do" in response_text
                    and 'type="password"' in response_text
                    and relogin
                ):  # Check if it looks like the login page
                    _LOGGER.info(
                        "Request to %s returned a login page. Session may have expired. Attempting relogin.",
                        url,
                    )
                    if await self.relogin():  # Attempt relogin
                        # Retry the original request *once* after successful relogin
                        _LOGGER.debug(
                            "Relogin successful, retrying original request to %s", url
                        )
                        response = await self.session.request(method, url, **kwargs)
                        _LOGGER.debug(
                            "Retry request after relogin returned status: %s",
                            response.status,
                        )
                    else:
                        # Relogin failed, raise specific error
                        _LOGGER.error("Relogin failed. Unable to complete request.")
                        raise IstaLoginError("Relogin failed, cannot complete request.")

            # Raise exception for non-success status codes after potential relogin
            response.raise_for_status()
            return response

        except ClientResponseError as err:
            if err.status in RETRY_STATUS_CODES and retry_attempts > 0:
                wait_time = RETRY_BACKOFF * (MAX_RETRIES - retry_attempts + 1)
                _LOGGER.warning(
                    "Request failed with recoverable status %s, retrying in %ds... (%d attempts left)",
                    err.status,
                    wait_time,
                    retry_attempts,
                )
                await asyncio.sleep(wait_time)
                # Decrement retry counter for the recursive call
                return await self._send_request(
                    method, url, retry_attempts - 1, relogin=relogin, **kwargs
                )
            _LOGGER.error(
                "Request failed with unrecoverable status %s for URL %s: %s",
                err.status,
                url,
                err.message,
            )
            raise IstaConnectionError(
                f"Request failed: {err.status} {err.message}"
            ) from err
        except (ClientError, asyncio.TimeoutError) as err:
            if retry_attempts > 0:
                wait_time = RETRY_BACKOFF * (MAX_RETRIES - retry_attempts + 1)
                _LOGGER.warning(
                    "Request failed with %s, retrying in %ds... (%d attempts left)",
                    type(err).__name__,
                    wait_time,
                    retry_attempts,
                )
                await asyncio.sleep(wait_time)
                return await self._send_request(
                    method, url, retry_attempts - 1, relogin=relogin, **kwargs
                )

            _LOGGER.error(
                "Request to %s failed after all retries due to %s: %s",
                url,
                type(err).__name__,
                err,
            )
            raise IstaConnectionError(f"Request failed after retries: {err}") from err

    async def relogin(self) -> bool:
        """Perform a fresh login, clearing old session state if necessary.

        Returns:
            True if login was successful, False otherwise.
        """
        _LOGGER.info("Attempting relogin for user %s", self.username)
        # Clear cookies specific to this domain if needed, or rely on session handling
        # self.session.cookie_jar.clear_domain('oficina.ista.es') # Example if needed
        return await self.login()

    async def login(self) -> bool:
        """Authenticate with the Ista Calista virtual office asynchronously.

        Uses a lock to prevent concurrent login attempts.

        Returns:
            True if login successful, False otherwise.

        Raises:
            IstaLoginError: If authentication fails.
            IstaConnectionError: If the request fails.
        """
        async with self._login_lock:
            # Check if already logged in (e.g., check for a specific cookie)
            # This check depends on how Ista manages sessions. Example:
            # if any(cookie.key == 'JSESSIONID' for cookie in self.session.cookie_jar):
            #     _LOGGER.debug("Already logged in (session cookie found).")
            #     # Optionally verify session validity here if possible
            #     return True

            _LOGGER.info("Attempting to log in user: %s", self.username)
            data = {
                "metodo": "loginAbonado",
                "loginName": self.username,
                "password": self.password,
            }

            try:
                response = await self._send_request(
                    "POST", LOGIN_URL, data=data, relogin=False
                )

                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) > 0:
                    response_text = await response.text()
                    _LOGGER.warning(
                        "Login failed for %s. Server returned status 200 but with content (length: %s), "
                        "which indicates invalid credentials. Response snippet: %s",
                        self.username,
                        content_length,
                        response_text[:250].replace("\n", ""),
                    )
                    raise IstaLoginError(
                        "Login failed - invalid credentials or server error"
                    )

                _LOGGER.info("Login successful for %s.", self.username)
                # Preload metadata needed for data downloads
                await self._preload_reading_metadata()
                return True

            except IstaConnectionError as err:
                _LOGGER.error(
                    "Connection error during login for %s: %s", self.username, err
                )
                raise
            except IstaLoginError:  # Re-raise specific login errors
                raise
            except Exception:
                _LOGGER.exception(
                    "An unexpected error occurred during login for %s", self.username
                )
                raise

    async def _preload_reading_metadata(self) -> None:
        """Preload reading metadata required for subsequent requests (async).

        Raises:
            IstaConnectionError: If the request fails.
            IstaLoginError: If session expired and relogin failed.
        """
        _LOGGER.debug("Preloading reading metadata for Excel export.")
        params = {"metodo": "preCargaLecturasRadio"}
        try:
            await self._send_request("GET", DATA_URL, params=params)
            _LOGGER.debug("Successfully preloaded reading metadata.")
        except (IstaConnectionError, IstaLoginError) as err:
            _LOGGER.error("Failed to preload reading metadata: %s", err)
            raise
        except Exception:
            _LOGGER.exception("An unexpected error occurred while preloading metadata.")
            raise

    async def _get_readings_chunk(
        self,
        start: date,
        end: date,
        max_days: int = MAX_DAYS_PER_REQUEST,
    ) -> io.BytesIO:
        """Get readings for a specific date range chunk asynchronously.

        Args:
            start: Start date for the chunk.
            end: End date for the chunk.
            max_days: Maximum number of days per request.

        Returns:
            BytesIO object containing the Excel data.

        Raises:
            ValueError: If the date range exceeds max_days.
            IstaConnectionError: If the request fails.
            IstaLoginError: If session expired and relogin failed.
            IstaApiError: For unexpected errors.
        """
        delta_days = (end - start).days
        if delta_days >= max_days:  # Use >= to be safe
            _LOGGER.error(
                "Date range (%d days) exceeds maximum of %d days.",
                delta_days,
                max_days,
            )
            raise ValueError(
                f"Date range exceeds maximum {max_days} days: {delta_days} days"
            )
        if delta_days < 0:
            _LOGGER.error("Start date (%s) is after end date (%s).", start, end)
            raise ValueError("Start date must be before end date")

        _LOGGER.debug(
            "Fetching readings chunk for date range: %s to %s",
            start.isoformat(),
            end.isoformat(),
        )

        params = {
            "d-4360165-e": "2",  # 2=xlsx format
            "fechaHastaRadio": quote(end.strftime(DATE_FORMAT)),
            "metodo": "listadoLecturasRadio",
            "fechaDesdeRadio": quote(start.strftime(DATE_FORMAT)),
            "6578706f7274": "1",  # Export flag
        }

        try:
            response = await self._send_request("GET", DATA_URL, params=params)

            content_type = response.headers.get("Content-Type", "")
            if EXCEL_CONTENT_TYPE not in content_type:
                # This case is now more likely to be handled by the relogin logic
                # in _send_request, but we keep a specific check as a safeguard.
                response_text = await response.text()
                _LOGGER.error(
                    "Expected Excel file but received content type '%s'. This may indicate a session or API issue. Response snippet: %s",
                    content_type,
                    response_text[:250].replace("\n", ""),
                )
                if (
                    "text/html" in content_type
                    and "GestionOficinaVirtual.do" in response_text
                ):
                    raise IstaLoginError(
                        "Received login page instead of Excel file, session likely expired and relogin failed."
                    )
                raise IstaApiError(
                    f"Received unexpected content type '{content_type}' instead of Excel file."
                )

            # Read response content into BytesIO
            content = await response.read()
            _LOGGER.debug(
                "Successfully downloaded Excel data chunk of size %d bytes.",
                len(content),
            )
            return io.BytesIO(content)

        except (IstaConnectionError, IstaLoginError, IstaApiError) as err:
            _LOGGER.error(
                "Failed to download readings chunk from %s to %s: %s", start, end, err
            )
            raise  # Re-raise the caught exception
        except Exception:
            _LOGGER.exception(
                "An unexpected error occurred while downloading readings chunk from %s to %s",
                start,
                end,
            )
            raise

    async def _get_readings(
        self,
        start: date,
        end: date,
        max_days: int = MAX_DAYS_PER_REQUEST,
    ) -> list[tuple[int, io.BytesIO]]:
        """Get all readings within a date range, splitting into chunks asynchronously.

        Args:
            start: Start date for readings.
            end: End date for readings.
            max_days: Maximum days per chunk request.

        Returns:
            List of tuples containing (year, file_buffer) for each chunk.

        Raises:
            ValueError: If start date is after end date.
            IstaConnectionError: If any chunk request fails.
            IstaLoginError: If session expired and relogin failed.
            IstaApiError: For unexpected errors.
        """
        if start > end:
            raise ValueError("Start date must be before or equal to end date")

        file_buffers: list[tuple[int, io.BytesIO]] = []
        current_start = start

        _LOGGER.debug(
            "Starting to fetch all readings from %s to %s in chunks of max %d days.",
            start.isoformat(),
            end.isoformat(),
            max_days,
        )

        while current_start <= end:
            current_end = min(current_start + timedelta(days=max_days - 1), end)

            _LOGGER.info(
                "Requesting data chunk for period: %s to %s",
                current_start.isoformat(),
                current_end.isoformat(),
            )

            try:
                # Fetch the chunk asynchronously
                file_buffer = await self._get_readings_chunk(current_start, current_end)
                # Store the buffer along with the *end* year for the parser context
                file_buffers.append((current_end.year, file_buffer))
            except (
                IstaConnectionError,
                IstaLoginError,
                IstaApiError,
                ValueError,
            ) as err:
                _LOGGER.error(
                    "Aborting history fetch. Failed to get readings for chunk %s to %s: %s",
                    current_start.isoformat(),
                    current_end.isoformat(),
                    err,
                )
                raise  # Propagate the error to stop the process

            # Move to the next day after the current chunk's end date
            current_start = current_end + timedelta(days=1)

        _LOGGER.info("Successfully retrieved %d data chunk(s).", len(file_buffers))
        return file_buffers

    async def get_devices_history(
        self,
        start: date,
        end: date,
    ) -> dict[str, Device]:
        """Get historical consumption data for all devices asynchronously.

        Args:
            start: Start date for the history period.
            end: End date for the history period.

        Returns:
            Dictionary mapping device serial numbers to device objects with history.

        Raises:
            ValueError: If start date is after end date.
            IstaConnectionError: If data retrieval fails.
            IstaLoginError: If session expired and relogin failed.
            IstaParserError: If Excel parsing fails.
            IstaApiError: For unexpected errors.
        """
        _LOGGER.info(
            "Getting full device history from %s to %s",
            start.isoformat(),
            end.isoformat(),
        )
        if start > end:
            raise ValueError("Start date must be before end date")

        try:
            # Get list of (year, file_buffer) tuples asynchronously
            current_year_file_buffers = await self._get_readings(start, end)

            if not current_year_file_buffers:
                _LOGGER.warning(
                    "No data files were retrieved from Ista for the period %s to %s. This can be normal if there are no new readings.",
                    start.isoformat(),
                    end.isoformat(),
                )
                return {}  # Return empty dict if no files were fetched

            device_lists: list[DeviceDict] = []
            loop = asyncio.get_running_loop()

            # Process parsing in executor as pandas/xlrd are synchronous
            _LOGGER.debug(
                "Creating %d parsing tasks to run in executor.",
                len(current_year_file_buffers),
            )
            tasks = []
            for current_year, file_buffer in current_year_file_buffers:
                parser = ExcelParser(file_buffer, current_year)
                # Run synchronous parser in executor thread
                tasks.append(loop.run_in_executor(None, parser.get_devices_history))

            # Wait for all parsing tasks to complete
            parsed_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for parsing errors
            for i, result in enumerate(parsed_results):
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "An error occurred during the parsing of an Excel file (chunk %d).",
                        i + 1,
                        exc_info=result,
                    )
                    # Raise the first encountered parser error
                    raise IstaParserError(
                        "Failed to parse one or more Excel files"
                    ) from result
                if isinstance(result, dict):
                    device_lists.append(result)
                else:
                    _LOGGER.error(
                        "Unexpected result of type '%s' returned from parser task.",
                        type(result),
                    )
                    raise IstaParserError("Unexpected result during parsing.")

            _LOGGER.debug(
                "All %d parsing tasks completed. Proceeding to merge results.",
                len(parsed_results),
            )
            # Merge the results from different files/chunks
            merged_devices = self.merge_device_histories(device_lists)
            _LOGGER.info(
                "Successfully merged history, resulting in %d unique devices.",
                len(merged_devices),
            )
            return merged_devices

        except (
            IstaConnectionError,
            IstaLoginError,
            IstaParserError,
            IstaApiError,
            ValueError,
        ) as err:
            _LOGGER.error(
                "Failed to get complete device history: %s", err, exc_info=True
            )
            raise  # Re-raise the specific error
        except Exception:
            _LOGGER.exception("An unexpected error occurred in get_devices_history.")
            raise

    def merge_device_histories(self, device_lists: list[DeviceDict]) -> DeviceDict:
        """Merge device histories from multiple time periods.

        This method combines historical readings from different time periods
        into a single consolidated history for each device. It also handles
        interpolation for missing readings.

        Args:
            device_lists: List of dictionaries containing device histories.

        Returns:
            Dictionary with merged and interpolated device histories.
        """
        merged_devices: DeviceDict = {}
        _LOGGER.debug("Merging %d list(s) of parsed devices.", len(device_lists))

        for i, device_list in enumerate(device_lists):
            _LOGGER.debug(
                "Processing device list #%d with %d devices.", i + 1, len(device_list)
            )
            for serial_number, device in device_list.items():
                if not isinstance(device, Device):
                    _LOGGER.warning(
                        "Skipping invalid item in device list (not a Device object): %s",
                        device,
                    )
                    continue

                if serial_number not in merged_devices:
                    # Create a new instance of the correct device type
                    _LOGGER.debug(
                        "Discovered new device SN %s. Creating entry in merged list.",
                        serial_number,
                    )
                    merged_devices[serial_number] = device.__class__(
                        serial_number=device.serial_number, location=device.location
                    )

                existing_device = merged_devices[serial_number]
                # Add readings, ensuring no duplicates based on date
                existing_dates = {r.date for r in existing_device.history}
                new_readings_count = 0
                for reading in device.history:
                    if reading.date not in existing_dates:
                        existing_device.add_reading(reading)
                        existing_dates.add(reading.date)
                        new_readings_count += 1
                if new_readings_count > 0:
                    _LOGGER.debug(
                        "Added %d new unique readings to device SN %s.",
                        new_readings_count,
                        serial_number,
                    )

        # Interpolate and trim final merged devices
        _LOGGER.debug(
            "Finished merging. Now interpolating and trimming %d devices.",
            len(merged_devices),
        )
        final_devices: DeviceDict = {}
        for serial_number, device in merged_devices.items():
            try:
                final_devices[serial_number] = (
                    self._interpolate_and_trim_device_reading(device)
                )
            except Exception as e:
                _LOGGER.error(
                    "Failed to interpolate readings for device %s. It will be excluded from the final results. Error: %s",
                    serial_number,
                    e,
                    exc_info=True,
                )

        _LOGGER.debug(
            "Finished merging and interpolation, resulting in %d final devices.",
            len(final_devices),
        )
        return final_devices

    def _interpolate_and_trim_device_reading(self, device: Device) -> Device:
        """Creates a new device with linear interpolation of missing readings and
        trimming of last missing readings, applying special rules.

        Args:
            device (Device): Device to fix

        Returns:
            Device: Fixed device of the same type.

        Raises:
            ValueError: If device type is unknown or interpolation fails.
        """
        _LOGGER.debug(
            "Interpolating and trimming readings for device SN %s.",
            device.serial_number,
        )
        try:
            fixed_device = device.__class__(device.serial_number, device.location)
        except TypeError as e:
            raise ValueError(
                f"Could not instantiate device class {device.__class__.__name__}"
            ) from e

        sorted_readings = sorted(device.history, key=lambda r: r.date)
        valid_readings = [
            r for r in sorted_readings if r.reading is not None and r.reading >= 0
        ]

        if len(valid_readings) < 2:
            _LOGGER.debug(
                "Device SN %s has fewer than 2 valid readings (%d). Skipping interpolation.",
                device.serial_number,
                len(valid_readings),
            )
            for reading in valid_readings:
                fixed_device.add_reading(reading)
            return fixed_device

        first_valid_date = valid_readings[0].date
        last_valid_date = valid_readings[-1].date
        filtered_readings = [
            r for r in sorted_readings if first_valid_date <= r.date <= last_valid_date
        ]

        valid_reading_pairs = []
        for i in range(len(valid_readings) - 1):
            valid_reading_pairs.append((valid_readings[i], valid_readings[i + 1]))

        interpolated_count = 0
        for start_reading, end_reading in valid_reading_pairs:
            if (
                not fixed_device.history
                or fixed_device.history[-1].date != start_reading.date
            ):
                fixed_device.add_reading(start_reading)

            to_interpolate = [
                r
                for r in filtered_readings
                if start_reading.date < r.date < end_reading.date
                and (r.reading is None or r.reading < 0)
            ]

            if to_interpolate:
                _LOGGER.debug(
                    "Found %d readings to interpolate for SN %s between %s and %s.",
                    len(to_interpolate),
                    device.serial_number,
                    start_reading.date.isoformat(),
                    end_reading.date.isoformat(),
                )
                start_val = start_reading.reading
                end_val = end_reading.reading

                if end_val < start_val:
                    _LOGGER.info(
                        "Detected a meter reset for device SN %s (from %.2f to %.2f). "
                        "Interpolating %d missing values as 0.",
                        device.serial_number,
                        start_val,
                        end_val,
                        len(to_interpolate),
                    )
                    for r in sorted(to_interpolate, key=lambda x: x.date):
                        fixed_device.add_reading_value(0, r.date)
                        interpolated_count += 1
                    continue  # Move to the next pair of valid readings

                start_date_ts = start_reading.date.timestamp()
                end_date_ts = end_reading.date.timestamp()

                time_span = end_date_ts - start_date_ts
                value_span = end_val - start_val

                if time_span == 0:
                    _LOGGER.warning(
                        "Cannot interpolate for SN %s, found identical timestamps for different readings: %s",
                        device.serial_number,
                        start_reading.date,
                    )
                    continue

                for r in sorted(to_interpolate, key=lambda x: x.date):
                    elapsed_time = r.date.timestamp() - start_date_ts
                    fraction = elapsed_time / time_span

                    interpolated_value = round(start_val + (value_span * fraction), 4)

                    final_value = max(start_val, min(end_val, interpolated_value))

                    fixed_device.add_reading_value(final_value, r.date)
                    interpolated_count += 1

        if (
            not fixed_device.history
            or fixed_device.history[-1].date != valid_readings[-1].date
        ):
            fixed_device.add_reading(valid_readings[-1])

        _LOGGER.debug(
            "Interpolation complete for device SN %s. Total interpolated points: %d. Final reading count: %d",
            device.serial_number,
            interpolated_count,
            len(fixed_device.history),
        )
        return fixed_device
