from __future__ import annotations

from datetime import date, datetime, timedelta
import io
import logging
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter, Retry

from .excel_parser import ExcelParser

_LOGGER = logging.getLogger(__name__)


class VirtualApi:  # numpydoc ignore=ES01,EX01,PR01
    """Attributes

    ----------
    username : str
        Username for authentication.
    password : str
        Password for authentication.
    """

    session: requests.Session
    cookies: dict[str, any]
    form_action: str

    def __init__(
        self,
        username: str,
        password: str,
    ) -> None:  # numpydoc ignore=ES01,EX01
        """Initialize the object with username and password.

        Parameters
        ----------
        username : str
            Username for authentication.
        password : str
            Password for authentication.
        logger : logging.Logger, optional
            Logger object for logging messages, by default None.

        """
        self.username: str = username
        self.password: str = password

        self.cookies = {}
        self.session = requests.Session()

        self.session.verify = True
        retries = Retry(
            total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 408]
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def _send_request(
        self, method, url, **kwargs
    ) -> requests.Response:  # numpydoc ignore=ES01,EX01
        """Send an HTTP request using the session object.

        Parameters
        ----------
        method : str
            HTTP method for the request (e.g., 'GET', 'POST', 'PUT', 'DELETE').
        url : str
            URL to send the request to.
        **kwargs : dict
            Additional keyword arguments to pass to `session.request`.

        Returns
        -------
        requests.Response
            Response object returned by the HTTP request.

        Raises
        ------
        ValueError
            If `self.session` is not initialized (i.e., is `None`).

        """
        if self.session is None:
            raise ValueError("Session object is not initialized.")

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

    def relogin(self) -> None:
        self.cookies = {}
        self.login()

    def login(self) -> None:
        """Log in to ista Calista."""
        url = "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do"
        ua = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"

        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://oficina.ista.es",
            "Connection": "keep-alive",
            "Referer": "https://oficina.ista.es/GesCon/GestionOficinaVirtual.do?metodo=logOutAbonado",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0",
        }
        data = {
            "metodo": "loginAbonado",
            "loginName": self.username,
            "password": self.password,
        }
        if not self.cookies:
            response = self._send_request("POST", url, headers=headers, data=data)

            self.cookies = response.cookies.get_dict()

        else:
            _LOGGER.debug("Cookies already found.")

    def get_devices_history(self, start: date, end: date):
        current_year__file_buffer = self._get_readings(start, end)
        device_lists = []
        for current_year, file in current_year__file_buffer:
            parser = ExcelParser(file, current_year)
            devices = parser.get_devices_history()

            device_lists.append(devices)

        return self.merge_device_histories(device_lists)

    def merge_device_histories(self, device_lists: list[dict]) -> dict:
        """Merges the histories of devices from multiple lists. Each list is a dictionary.
        
        Parameters
        ----------
            device_lists (List[dict]):
                A list of dictionaries containing Device objects.

        Returns:
            dict: A merged dictionary with device serial numbers as keys and
                Device objects with consolidated histories.

        """
        merged_devices = {}

        for device_list in device_lists:
            for serial_number, device in device_list.items():
                if serial_number not in merged_devices:
                    # If the device is not in merged_devices, add it
                    merged_devices[serial_number] = device
                else:
                    # If the device already exists, merge histories
                    existing_device = merged_devices[serial_number]
                    for reading in device.history:
                        # Add each reading from the current device history to the existing device
                        existing_device.add_reading(reading)

        return merged_devices

    def _get_readings_chunk(self, start: datetime, end: datetime, max_days=240):
        """Helper function that makes the API request for a given date range chunk."""
        # Check if the date range exceeds the allowed max days
        delta_days = (end - start).days
        if delta_days > max_days:
            raise ValueError(
                f"Date range exceeds the maximum allowed {max_days} days: {delta_days} days"
            )

        url = "https://oficina.ista.es/GesCon/GestionFincas.do"

        query_params = {
            "idFinca": "31257",
            "d-4360165-e": "2",
            "fechaHastaRadio": quote(end.strftime("%d/%m/%Y")),
            "validacion": "true",
            "idAbonado": "",
            "metodo": "listadoLecturasRadio",
            "fechaDesdeRadio": quote(start.strftime("%d/%m/%Y")),
            "6578706f7274": "1",
        }

        ua = "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0"

        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Connection": "keep-alive",
            "Referer": "https://oficina.ista.es/GesCon/GestionFincas.do",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Priority": "u=0, i",
        }

        response = self._send_request(
            "GET", url, headers=headers, cookies=self.cookies, params=query_params
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "application/vnd.ms-excel;charset=iso-8859-1" not in content_type:
            if "text/html" in content_type:
                _LOGGER.error("Expired cookies, relogin")
                self.relogin()  # Renew cookies
                response = self._send_request(
                    "GET",
                    url,
                    headers=headers,
                    cookies=self.cookies,
                    params=query_params,
                )
                response.raise_for_status()
            else:
                _LOGGER.error(f"Unexpected Error. Content-Type: {content_type}")
                response.raise_for_status()

        return io.BytesIO(response.content)

    def _get_readings(
        self,
        start: datetime = date.today() - timedelta(days=30),
        end: datetime = date.today(),
        max_days=240,
    ):
        """Aggregates readings by calling the helper function in chunks."""
        all_file_buffers = []  # To store the file buffers from each chunk request

        # Split the date range into chunks of max_days
        current_start = start
        while current_start < end:
            current_end = min(
                current_start + timedelta(days=max_days), end
            )  # Ensure the chunk doesn't exceed the end date

            # Get the file buffer for the current chunk
            file_buffer = self._get_readings_chunk(current_start, current_end)
            all_file_buffers.append((current_end.year, file_buffer))

            # Move to the next chunk
            current_start = current_end

        return all_file_buffers
