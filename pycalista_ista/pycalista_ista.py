# numpydoc ignore=EX01,GL06,GL07
"""Unofficial python library for the ista Calista API.

This module provides a Python client for interacting with the ista Calista API.

Classes
-------
PyCalistaIsta
    A Python client for interacting with the ista Calista API.
"""

from __future__ import annotations

from datetime import date, timedelta
import logging

from .virtual_api import VirtualApi

_LOGGER = logging.getLogger(__name__)


class PyCalistaIsta: 
    def __init__(
        self,
        email: str,
        password: str,
    ) -> None:  

        self._email: str = email.strip()
        self._password: str = password

        self.virtual_api = VirtualApi(
            username=self._email,
            password=self._password,
        )

    def get_account(self) -> dict:  # numpydoc ignore=ES01,EX01
        return getattr(self, "email", None)

    def get_version(self) -> str:  # numpydoc ignore=EX01,ES01
        return "0.0.1"

    def get_devices_history(self, start=date.today() - timedelta(days=30),  end=date.today()):
        return self.virtual_api.get_devices_history(start, end)

    def login(
        self, force_login: bool = False, debug: bool = False, **kwargs
    ) -> str | None:  # numpydoc ignore=ES01,EX01,PR01,PR02

        self.virtual_api.login()
        
        return True
