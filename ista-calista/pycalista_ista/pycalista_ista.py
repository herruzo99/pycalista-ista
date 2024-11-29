# numpydoc ignore=EX01,GL06,GL07
"""Unofficial python library for the ista Calista API.

This module provides a Python client for interacting with the ista Calista API.

Classes
-------
PyCalistaIsta
    A Python client for interacting with the ista Calista API.
"""

from __future__ import annotations

from http import HTTPStatus
import logging
import time
from typing import Any, cast
import warnings

import requests

from .exception_classes import LoginError, ParserError, ServerError, deprecated
#from .helper_object_de import CustomRaw
from .virtual_api import VirtualApi
from .types import AccountResponse, ConsumptionsResponse, ConsumptionUnitDetailsResponse, GetTokenResponse

_LOGGER = logging.getLogger(__name__)


class PyCalistaIsta:  # numpydoc ignore=PR01
    """
    A Python client for interacting with the ista Calista API.

    This class provides methods to authenticate and interact with the ista Calista API.

    Attributes
    ----------
    _account : AccountResponse
        The account information.
    _uuid : str
        The UUID of the consumption unit.
    _header : dict[str, str]
        The headers used in HTTP requests.
    _start_timer : float
        The start time for tracking elapsed time.

    Examples
    --------
    Initialize the client and log in:

    >>> client = PyCalistaIsta(email="user@example.com", password="password")
    >>> client.login()
    """

    _start_timer: float = 0.0

    def __init__(
        self,
        email: str,
        password: str,
    ) -> None:  # numpydoc ignore=ES01,EX01
        """Initialize the PyCalistaIsta client.

        Parameters
        ----------
        email : str
            The email address used to log in to the ista Calista API.
        password : str
            The password used to log in to the ista Calista API.
        """
        self._email: str = email.strip()
        self._password: str = password

        self.virtual_api = VirtualApi(
            username=self._email,
            password=self._password,
        )

        self.session: requests.Session = self.virtual_api.session

    def _is_connected(self) -> bool:  # numpydoc ignore=ES01,EX01
        """
        Check if the client is connected by verifying the presence of an access token.

        Returns
        -------
        bool
            True if the client has a valid access token, False otherwise.
        """
        return bool(self.virtual_api.cookies)

    def get_account(self) -> AccountResponse | None:  # numpydoc ignore=ES01,EX01
        """
        Retrieve the account information.

        Returns the `_account` attribute if it exists, otherwise returns None.

        Returns
        -------
        AccountResponse | None
            Account information if available, otherwise None.
        """
        return getattr(self, "email", None)

    def get_version(self) -> str:  # numpydoc ignore=EX01,ES01
        """
        Get the version of the PyCalistaIsta client.

        Returns
        -------
        str
            The version number of the PyCalistaIsta client.
        """
        return VERSION

    def get_sensors_data(self):
        return self.virtual_api.get_sensors_data()

    def login(self, force_login: bool = False, debug: bool = False, **kwargs) -> str | None:  # numpydoc ignore=ES01,EX01,PR01,PR02
        """
        Perform the login process if not already connected or forced.

        Parameters
        ----------
        force_login : bool, optional
            If True, forces a fresh login attempt even if already connected. Default is False.

        Returns
        -------
        str or None
            The access token if login is successful, None otherwise.

        Raises
        ------
        LoginError
            If the login process fails due to an error.
        ServerError
            If a server error occurs during login attempts.
        InternalServerError
            If an internal server error occurs during login attempts.
        Exception
            For any other unexpected errors during the login process.

        """

        if not self._is_connected() or force_login:
            try:
                self.virtual_api.login()
            except (LoginError) as exc:
                raise LoginError(
                    "Login failed due to an authorization failure, please verify your email and password"
                ) from exc
            except ServerError as exc:
                raise ServerError("Login failed due to a request exception, please try again later") from exc

        return True

    # pylint: disable=too-many-branches,too-many-statements
    def consum_raw(  # noqa: C901
        self,
        select_year: list[int] | None = None,
        select_month: list[int] | None = None,
        filter_none: bool = True,
        obj_uuid: str | None = None,
    ) -> dict[str, Any] | ConsumptionsResponse:  # noqa: C901

        return{}
        # return CustomRaw.from_dict(
        #     {
        #         "consum_types": consum_types,
        #         "combined_data": None,  # combined_data,
        #         "total_additional_values": total_additional_values,
        #         "total_additional_custom_values": total_additional_custom_values,
        #         "last_value": last_value,
        #         "last_custom_value": last_custom_value,
        #         "last_costs": last_costs,
        #         "all_dates": None,  # all_dates,
        #         "sum_by_year": sum_by_year,
        #         "last_year_compared_consumption": last_year_compared_consumption,
        #     }
        # ).to_dict()

