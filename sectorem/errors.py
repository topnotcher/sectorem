"""Sectorem exception hierarchy."""


class SectoremError(Exception):
    """Base exception for all sectorem errors."""


class NotAuthenticatedError(SectoremError):
    """Raised when an operation requires authentication but none is active."""


class AuthenticationError(SectoremError):
    """Raised when an authentication operation fails."""


class ApiError(SectoremError):
    """
    Raised when a Schwab API call returns an error response.

    :param status: HTTP status code.
    :param message: Human-readable error description.
    :param response_body: Raw response body, if available.
    """

    def __init__(self, status: int, message: str, *, response_body: str = "") -> None:
        self.status = status
        self.response_body = response_body
        super().__init__(f"Schwab API {status}: {message}")


class RateLimitError(ApiError):
    """Raised when the API returns HTTP 429 (rate limited)."""


class StreamError(SectoremError):
    """Raised when the streaming connection encounters an error."""
