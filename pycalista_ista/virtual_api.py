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
MAX_RETRIES: Final = 0
RETRY_BACKOFF: Final = 1
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
        _LOGGER.debug("Sending %s request to %s, kwargs: %s", method, url, kwargs)

        if self.session is None or self.session.closed:
            raise IstaConnectionError("Session is closed")

        try:
            response = await self.session.request(method, url, **kwargs)
            text = await response.text()
            _LOGGER.debug(
                "Received response %s from %s: %s",
                response.status,
                url,
                text[:200], # Log beginning of response text
            )

            if response.status == 200 and "text/html" in response.headers.get(
                "Content-Type", ""
            ):
                if await self.relogin(): # Attempt relogin
                    # Retry the original request *once* after successful relogin
                    _LOGGER.debug("Relogin successful, retrying original request to %s", url)
                    response = await self.session.request(method, url, **kwargs)
                    _LOGGER.debug("Retry response status: %s", response.status)
                else:
                    # Relogin failed, raise specific error
                    raise IstaLoginError("Relogin failed, cannot complete request.")
            # Raise exception for non-success status codes after potential relogin
            response.raise_for_status()
            return response

        except ClientResponseError as err:
            if err.status in RETRY_STATUS_CODES and retry_attempts > 0:
                wait_time = RETRY_BACKOFF * (MAX_RETRIES - retry_attempts + 1)
                _LOGGER.warning(
                    "Request failed with status %s, retrying in %ds (%d attempts left)",
                    err.status,
                    wait_time,
                    retry_attempts - 1,
                )
                await asyncio.sleep(wait_time)
                # Decrement retry counter for the recursive call
                return await self._send_request(method, url, retry_attempts - 1, **kwargs)
            _LOGGER.error(
                "Request failed with status %s after retries or for unrecoverable status: %s",
                err.status,
                err.message,
            )
            raise IstaConnectionError(
                f"Request failed: {err.status} {err.message}"
            ) from err
        except ClientError as err:
            # Handle other client errors (e.g., connection refused, timeout)
            if retry_attempts > 0:
                wait_time = RETRY_BACKOFF * (MAX_RETRIES - retry_attempts + 1)
                _LOGGER.warning(
                    "Request failed with client error %s, retrying in %ds (%d attempts left)",
                    err.__class__.__name__,
                    wait_time,
                    retry_attempts - 1,
                )
                await asyncio.sleep(wait_time)
                # Decrement retry counter for the recursive call
                return await self._send_request(method, url, retry_attempts - 1, **kwargs)
            _LOGGER.error("Request failed with client error after retries: %s", err)
            raise IstaConnectionError(f"Request failed: {err}") from err
        except asyncio.TimeoutError as err:
             # Handle timeout errors specifically
            if retry_attempts > 0:
                wait_time = RETRY_BACKOFF * (MAX_RETRIES - retry_attempts + 1)
                _LOGGER.warning(
                    "Request timed out, retrying in %ds (%d attempts left)",
                    wait_time,
                    retry_attempts - 1,
                )
                await asyncio.sleep(wait_time)
                # Decrement retry counter for the recursive call
                return await self._send_request(method, url, retry_attempts - 1, **kwargs)
            _LOGGER.error("Request timed out after retries")
            raise IstaConnectionError("Request timed out") from err


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

            _LOGGER.info("Attempting login for user %s", self.username)
            data = {
                "metodo": "loginAbonado",
                "loginName": self.username,
                "password": self.password,
            }

            try:
                response = await self._send_request("POST", LOGIN_URL, data=data)

                # Check for indicators of login failure. Ista returns 200 OK but with
                # content length > 0 on failure, unlike success which has no body.
                # Check content length or analyze response content if necessary.
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    _LOGGER.warning("Login failed for %s (Content-Length > 0)", self.username)
                    raise IstaLoginError("Login failed - invalid credentials or server error")

                _LOGGER.info("Login successful for %s", self.username)
                # Preload metadata needed for data downloads
                await self._preload_reading_metadata()
                return True

            except (ClientError, asyncio.TimeoutError) as err:
                _LOGGER.error("Login request failed for %s: %s", self.username, err)
                raise IstaConnectionError(f"Login request failed: {err}") from err
            except IstaLoginError: # Re-raise specific login errors
                raise
    
    async def _preload_reading_metadata(self) -> None:
        """Preload reading metadata required for subsequent requests (async).

        Raises:
            IstaConnectionError: If the request fails.
            IstaLoginError: If session expired and relogin failed.
        """
        _LOGGER.debug("Preloading reading metadata")
        params = {"metodo": "preCargaLecturasRadio"}
        try:
            await self._send_request("GET", DATA_URL, params=params)
            _LOGGER.debug("Metadata preloaded successfully")
        except (ClientError, asyncio.TimeoutError, IstaConnectionError) as err:
            _LOGGER.error("Failed to preload metadata: %s", err)
            # Let the specific exception type bubble up


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
        if delta_days > max_days:
            raise ValueError(
                f"Date range exceeds maximum {max_days} days: {delta_days} days"
            )
        if delta_days < 0:
             raise ValueError("Start date must be before end date")

        _LOGGER.debug("Fetching readings chunk from %s to %s", start, end)

        params = {
            "d-4360165-e": "2",  # 2=xlsx format
            "fechaHastaRadio": quote(end.strftime(DATE_FORMAT)),
            "metodo": "listadoLecturasRadio",
            "fechaDesdeRadio": quote(start.strftime(DATE_FORMAT)),
            "6578706f7274": "1", # Export flag
        }

        try:
            response = await self._send_request("GET", DATA_URL, params=params)

            content_type = response.headers.get("Content-Type", "")
            if EXCEL_CONTENT_TYPE not in content_type:
                # Check if it's an HTML response indicating potential session expiry
                if "text/html" in content_type:
                    # This was already handled inside _send_request with a relogin attempt.
                    # If we reach here, the relogin likely failed or the page isn't the login page.
                    text = await response.text()
                    _LOGGER.error(
                        "Received unexpected HTML content instead of Excel after potential relogin attempt. Content: %s",
                        text[:500] # Log beginning of unexpected content
                    )
                    raise IstaApiError(f"Received unexpected HTML content instead of Excel for {start} to {end}.")

                # Handle other unexpected content types
                _LOGGER.error(
                    "Unexpected content type received: %s. Expected '%s'.",
                    content_type, EXCEL_CONTENT_TYPE
                )
                raise IstaApiError(f"Unexpected content type: {content_type}")

            # Read response content into BytesIO
            content = await response.read()
            return io.BytesIO(content)

        except (ClientError, asyncio.TimeoutError, IstaConnectionError, IstaLoginError, IstaApiError) as err:
            _LOGGER.error("Failed to get readings chunk from %s to %s: %s", start, end, err)
            raise # Re-raise the caught exception


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

        while current_start <= end:
            # Calculate end date for the current chunk
            # Ensure we don't exceed the overall end date
            current_end = min(current_start + timedelta(days=max_days -1), end) # -1 because timedelta includes start day

            _LOGGER.info("Requesting data chunk: %s to %s", current_start, current_end)

            try:
                # Fetch the chunk asynchronously
                file_buffer = await self._get_readings_chunk(current_start, current_end, max_days)
                # Store the buffer along with the *end* year for the parser context
                file_buffers.append((current_end.year, file_buffer))
            except (IstaConnectionError, IstaLoginError, IstaApiError, ValueError) as err:
                _LOGGER.error(
                    "Failed to get readings for chunk %s to %s: %s",
                    current_start,
                    current_end,
                    err,
                )
                raise # Propagate the error to stop the process

            # Move to the next day after the current chunk's end date
            current_start = current_end + timedelta(days=1)

        _LOGGER.info("Successfully retrieved %d data chunks.", len(file_buffers))
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
        _LOGGER.info("Getting device history from %s to %s", start, end)
        if start > end:
            raise ValueError("Start date must be before end date")

        try:
            # Get list of (year, file_buffer) tuples asynchronously
            current_year_file_buffers = await self._get_readings(start, end)

            if not current_year_file_buffers:
                 _LOGGER.warning("No data files retrieved from Ista for the period %s to %s", start, end)
                 return {} # Return empty dict if no files were fetched

            device_lists: list[DeviceDict] = []
            loop = asyncio.get_running_loop()

            # Process parsing in executor as pandas/xlrd are synchronous
            tasks = []
            for current_year, file_buffer in current_year_file_buffers:
                parser = ExcelParser(file_buffer, current_year)
                # Run synchronous parser in executor thread
                tasks.append(loop.run_in_executor(None, parser.get_devices_history))

            # Wait for all parsing tasks to complete
            parsed_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for parsing errors
            for result in parsed_results:
                if isinstance(result, Exception):
                    _LOGGER.error("Error during Excel parsing: %s", result)
                    # Raise the first encountered parser error
                    raise IstaParserError("Failed to parse one or more Excel files") from result
                if isinstance(result, dict):
                     device_lists.append(result)
                else:
                    # Should not happen if gather returns correctly
                    _LOGGER.error("Unexpected result type from parser task: %s", type(result))
                    raise IstaParserError("Unexpected result during parsing.")


            # Merge the results from different files/chunks
            merged_devices = self.merge_device_histories(device_lists)
            _LOGGER.info("Successfully merged history for %d devices", len(merged_devices))
            return merged_devices

        except (IstaConnectionError, IstaLoginError, IstaParserError, IstaApiError, ValueError) as err:
            _LOGGER.error("Failed to get complete device history: %s", err)
            raise # Re-raise the specific error


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
        _LOGGER.debug("Merging %d device lists", len(device_lists))

        for device_list in device_lists:
            for serial_number, device in device_list.items():
                if not isinstance(device, Device):
                    _LOGGER.warning("Skipping invalid item in device list: %s", device)
                    continue

                if serial_number not in merged_devices:
                    # Create a new instance of the correct device type
                    merged_devices[serial_number] = device.__class__(
                        serial_number=device.serial_number,
                        location=device.location
                    )

                existing_device = merged_devices[serial_number]
                # Add readings, ensuring no duplicates based on date
                existing_dates = {r.date for r in existing_device.history}
                for reading in device.history:
                    if reading.date not in existing_dates:
                        existing_device.add_reading(reading)
                        existing_dates.add(reading.date)

        # Interpolate and trim final merged devices
        final_devices: DeviceDict = {}
        for serial_number, device in merged_devices.items():
            try:
                final_devices[serial_number] = self._interpolate_and_trim_device_reading(device)
            except Exception as e:
                _LOGGER.error("Error interpolating device %s: %s", serial_number, e, exc_info=True)
                # Optionally, decide whether to include the non-interpolated device or skip it
                # For now, we'll skip it to avoid potentially corrupted data
                _LOGGER.warning("Skipping device %s due to interpolation error.", serial_number)


        _LOGGER.debug("Finished merging histories into %d final devices", len(final_devices))
        return final_devices


    def _interpolate_and_trim_device_reading(self, device: Device) -> Device:
        """Creates a new device with linear interpolation of missing readings and
        trimming of last missing readings.

        Args:
            device (Device): Device to fix

        Returns:
            Device: Fixed device of the same type.

        Raises:
            ValueError: If device type is unknown or interpolation fails.
        """
        _LOGGER.debug("Interpolating and trimming readings for device %s", device.serial_number)
        # Create a new device instance of the same type
        try:
            fixed_device = device.__class__(device.serial_number, device.location)
        except TypeError as e:
             raise ValueError(f"Could not instantiate device class {device.__class__.__name__}") from e

        # Step 1: Sort readings by date
        sorted_readings = sorted(device.history, key=lambda r: r.date)

        # Step 2: Identify valid readings (non-null and non-negative values)
        valid_readings = [r for r in sorted_readings if r.reading is not None and r.reading >= 0]

        # If there are fewer than 2 valid readings, we can't interpolate
        if len(valid_readings) < 2:
            _LOGGER.debug("Less than 2 valid readings for %s, skipping interpolation.", device.serial_number)
            # Just copy the valid readings as-is
            for reading in valid_readings:
                fixed_device.add_reading(reading)
            return fixed_device

        # Step 3: Find the first and last valid reading date
        first_valid_date = valid_readings[0].date
        last_valid_date = valid_readings[-1].date

        # Step 4: Filter readings to only include those between first and last valid date
        filtered_readings = [r for r in sorted_readings
                            if first_valid_date <= r.date <= last_valid_date]

        # Step 5: Create pairs of consecutive valid readings for interpolation
        valid_reading_pairs = []
        for i in range(len(valid_readings) - 1):
            start_reading = valid_readings[i]
            end_reading = valid_readings[i + 1]
            valid_reading_pairs.append((start_reading, end_reading))

        # Step 6: Process each pair of valid readings
        interpolated_count = 0
        for start_reading, end_reading in valid_reading_pairs:
            # Add the start reading (avoid duplicates if it was the end of previous pair)
            if not fixed_device.history or fixed_device.history[-1].date != start_reading.date:
                 fixed_device.add_reading(start_reading)

            # Find readings that need interpolation between this pair
            to_interpolate = [r for r in filtered_readings
                            if start_reading.date < r.date < end_reading.date
                            and (r.reading is None or r.reading < 0)] # Interpolate None or negative

            if to_interpolate:
                # Calculate interpolation parameters
                start_date_ts = start_reading.date.timestamp()
                end_date_ts = end_reading.date.timestamp()
                start_val = start_reading.reading
                end_val = end_reading.reading

                time_span = end_date_ts - start_date_ts
                value_span = end_val - start_val

                # Avoid division by zero if timestamps are identical (shouldn't happen with < check)
                if time_span == 0:
                    _LOGGER.warning("Skipping interpolation for %s between identical timestamps: %s",
                                    device.serial_number, start_reading.date)
                    continue

                # Interpolate each missing reading
                for r in sorted(to_interpolate, key=lambda x: x.date):
                    elapsed_time = r.date.timestamp() - start_date_ts
                    fraction = elapsed_time / time_span
                    interpolated_value = round(start_val + (value_span * fraction), 2)
                    fixed_device.add_reading_value(interpolated_value, r.date)
                    interpolated_count += 1

        # Add the final valid reading (avoid duplicates)
        if not fixed_device.history or fixed_device.history[-1].date != valid_readings[-1].date:
            fixed_device.add_reading(valid_readings[-1])

        _LOGGER.debug("Interpolated %d readings for device %s", interpolated_count, device.serial_number)
        return fixed_device

