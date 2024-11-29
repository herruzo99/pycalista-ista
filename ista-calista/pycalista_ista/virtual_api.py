
from __future__ import annotations

import html
import logging
import re
from typing import Any, cast
import urllib.parse

import requests
from requests.adapters import HTTPAdapter, Retry

from .types import GetTokenResponse
_LOGGER = logging.getLogger(__name__)
import time
import re
import io
from .excel_parser import ExcelParser
import json
class VirtualApi:  # numpydoc ignore=ES01,EX01,PR01
    """
    Attributes
    ----------
    username : str
        Username for authentication.
    password : str
        Password for authentication.

    """

    session: requests.Session
    cookies: dict(str)
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
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504, 408])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))


    def _send_request(self, method, url, **kwargs) -> requests.Response:  # numpydoc ignore=ES01,EX01
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
        try:
            response = self.session.request(method, url, **kwargs)
            _LOGGER.info("Performed %s request: %s [%s]:\n%s", method, url, response.status_code, response.text[:100])
            response.raise_for_status()
        except requests.RequestException as e:
            raise RequestException from e

        return response

    def login(self) -> None:  # numpydoc ignore=ES01,EX01
        """Log in to ista Calista.
        """
        url = 'https://oficina.ista.es/GesCon/GestionOficinaVirtual.do'
        ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0'

        headers= {'User-Agent': ua,
                  'Accept':  'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                  'Accept-Language': 'es-ES,es;q=0.5',
                  'Accept-Encoding': 'gzip, deflate, br, zstd',
                  'Content-Type': 'application/x-www-form-urlencoded',
                  'Origin': 'https://oficina.ista.es',
                  'Connection': 'keep-alive',
                  'Referer': 'https://oficina.ista.es/GesCon/GestionOficinaVirtual.do?metodo=logOutAbonado',
                  'Upgrade-Insecure-Requests': '1',
                  'Sec-Fetch-Dest': 'document',
                  'Sec-Fetch-Mode': 'navigate',
                  'Sec-Fetch-Site': 'same-origin',
                  'Sec-Fetch-User': '?1',
                  'Priority': 'u=0'
                    }
        data={
            'metodo': 'loginAbonado',
            'loginName': self.username,
            'password': self.password
        }
        if not self.cookies:
            response = self._send_request('POST', url, headers=headers, data=data)

            self.cookies = response.cookies.get_dict()

        else:
            _LOGGER.info('Cookies already found.')

    def get_sensors_data(self):
        file_buffer = self._get_readings()
        parser = ExcelParser(file_buffer)
        devices = parser.get_last_data_by_n_serie()
        _LOGGER.info(json.dumps(devices))
        return devices


    def _get_readings(self):
        url = 'https://oficina.ista.es/GesCon/GestionLecturasBusqueda.do?metodo=buscarLecturas'
        ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0'

        headers= {'User-Agent': ua,
                  'Accept':  'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                  'Accept-Language': 'es-ES,es;q=0.5',
                  'Accept-Encoding': 'gzip, deflate, br, zstd',
                  'Content-Type': 'application/x-www-form-urlencoded',
                  'Connection': 'keep-alive',
                  'Referer': 'https://oficina.ista.es/GesCon/GestionOficinaVirtual.do',
                  'Upgrade-Insecure-Requests': '1',
                  'Sec-Fetch-Dest': 'document',
                  'Sec-Fetch-Mode': 'navigate',
                  'Sec-Fetch-Site': 'same-origin',
                  'Sec-Fetch-User': '?1',
                  'Priority': 'u=0'
                    }

        response = self._send_request('GET', url, headers=headers, cookies=self.cookies)


        time.sleep(1)

        url = 'https://oficina.ista.es/GesCon/GestionLecturas.do?d-148657-e=2&metodo=listadoLecturas&metodo=buscarLecturas&6578706f7274=1'
        ua = 'Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0'

        headers= {'User-Agent': ua,
                  'Accept':  'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                  'Accept-Language': 'es-ES,es;q=0.5',
                  'Accept-Encoding': 'gzip, deflate, br, zstd',
                  'Content-Type': 'application/x-www-form-urlencoded',
                  'Connection': 'keep-alive',
                  'Referer': 'Referer: https://oficina.ista.es/GesCon/GestionLecturasBusqueda.do?metodo=buscarLecturas',
                  'Upgrade-Insecure-Requests': '1',
                  'Sec-Fetch-Dest': 'document',
                  'Sec-Fetch-Mode': 'navigate',
                  'Sec-Fetch-Site': 'same-origin',
                  'Sec-Fetch-User': '?1',
                  'Priority': 'u=0'
                    }

        response = self._send_request('GET', url, headers=headers, cookies=self.cookies)
        response.raise_for_status()
        file_buffer = io.BytesIO(response.content)
        return file_buffer
