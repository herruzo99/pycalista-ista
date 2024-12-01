"""Exception Class."""  # numpydoc ignore=ES01,EX01

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


class ServerError(Exception): 

    def __str__(self) -> str:
        """Return a string representation of the error.."""
        return "Server error occurred during the request"


class LoginError(Exception): 

    def __str__(self) -> str:
        """Return a string representation of an authentication error."""
        return "An authentication error occurred during the request"


class ParserError(ServerError):

    def __str__(self) -> str:
        """Return a string representation of parser error."""
        return "Error occurred during parsing of the request response"
