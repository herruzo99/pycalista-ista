"""Custom exceptions for the PyCalistaIsta package.

This module defines the custom exceptions used throughout the package
for handling various error conditions that may occur during API
interactions and data processing.

Exceptions:
    ServerError: Base exception for server-related errors
    LoginError: Exception for authentication failures
    ParserError: Exception for data parsing errors
"""

from __future__ import annotations


class ServerError(Exception):
    """Base exception for server-related errors.

    This exception is raised when there are issues communicating with
    the Ista Calista server or when unexpected server responses are received.
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Optional error message. If not provided, a default message is used.
        """
        self.message = message or "Server error occurred during the request"
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return a string representation of the error.

        Returns:
            The error message.
        """
        return self.message


class LoginError(ServerError):
    """Exception for authentication failures.

    This exception is raised when authentication with the Ista Calista
    server fails, either due to invalid credentials or server issues.
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Optional error message. If not provided, a default message is used.
        """
        super().__init__(
            message or "An authentication error occurred during the request"
        )


class ParserError(ServerError):
    """Exception for data parsing errors.

    This exception is raised when there are issues parsing the data
    received from the Ista Calista server, typically with Excel files.
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Optional error message. If not provided, a default message is used.
        """
        super().__init__(
            message or "Error occurred during parsing of the request response"
        )
