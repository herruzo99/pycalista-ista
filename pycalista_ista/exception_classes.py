"""Custom exceptions for the PyCalistaIsta package.

Defines custom exceptions for handling various error conditions during
API interactions and data processing with the Ista Calista service.
"""

from __future__ import annotations


class IstaApiError(Exception):
    """Base exception for PyCalistaIsta errors.

    Indicates a general issue related to the Ista Calista API interaction.
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the base API error.

        Args:
            message: Optional error message. Uses a default if not provided.
        """
        super().__init__(message or "An unspecified error occurred with the Ista Calista API")


class IstaConnectionError(IstaApiError):
    """Exception for network or connection issues.

    Raised when there are problems connecting to the Ista Calista server,
    such as network errors, timeouts, or DNS issues.
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the connection error.

        Args:
            message: Optional error message. Uses a default if not provided.
        """
        super().__init__(message or "Could not connect to the Ista Calista server")


class IstaLoginError(IstaApiError):
    """Exception for authentication failures.

    Raised when login to the Ista Calista server fails, due to invalid
    credentials, expired sessions, or server-side authentication issues.
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the login error.

        Args:
            message: Optional error message. Uses a default if not provided.
        """
        super().__init__(message or "Authentication failed with the Ista Calista server")


class IstaParserError(IstaApiError):
    """Exception for data parsing errors.

    Raised when there are issues parsing the data received from the
    Ista Calista server, typically problems with the Excel file format or content.
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the parser error.

        Args:
            message: Optional error message. Uses a default if not provided.
        """
        super().__init__(message or "Failed to parse data received from Ista Calista")

