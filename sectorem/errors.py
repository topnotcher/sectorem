"""Sectorem exception hierarchy."""
from __future__ import annotations


class SectoremError(Exception):
    """Base exception for all sectorem errors."""


class NotAuthenticatedError(SectoremError):
    """Raised when an operation requires authentication but none is active."""


class AuthenticationError(SectoremError):
    """Raised when an authentication operation fails."""


class _ApiErrorMeta(type):
    """
    Metaclass for :class:`ApiError` that auto-registers subclasses by
    HTTP status code and dispatches construction to the appropriate
    subclass via ``__new__``.

    Subclasses with ``_CODE`` are matched exactly. Subclasses with
    ``_RANGE`` (a ``(low, high)`` inclusive tuple) serve as catch-alls
    for any status in that range without an exact match.
    """

    _CODE_MAP: dict[int, type] = {}
    _RANGE_MAP: list[tuple[range, type]] = []

    def __init__(cls, name: str, bases: tuple, namespace: dict, **kwargs) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        code = namespace.get("_CODE")
        if code is not None:
            _ApiErrorMeta._CODE_MAP[code] = cls
        code_range = namespace.get("_RANGE")
        if code_range is not None:
            _ApiErrorMeta._RANGE_MAP.append((range(code_range[0], code_range[1] + 1), cls))

    def __call__(cls, status: int, message: str, **kwargs):
        if cls is ApiError:
            target = _ApiErrorMeta._CODE_MAP.get(status)
            if target is None:
                for r, range_cls in _ApiErrorMeta._RANGE_MAP:
                    if status in r:
                        target = range_cls
                        break
            cls = target or ApiError
        return super().__call__(status, message, **kwargs)


class ApiError(SectoremError, metaclass=_ApiErrorMeta):
    """
    Raised when a Schwab API call returns an error response.

    Constructing ``ApiError(status, message)`` automatically returns
    the appropriate subclass when one is registered for *status*.

    :param status: HTTP status code.
    :param message: Human-readable error description.
    :param errors: Error list from Schwab.
    :param correlation_id: Schwab client correlation ID for the request, if available.
    """

    _CODE: int | None = None

    def __init__(self, status: int, message: str, *, errors: list | None = None, correlation_id: str | None = None) -> None:
        #: HTTP status code returned by the API.
        self.status = status
        #: Schwab correlation ID
        self.correlation_id = correlation_id
        #: List of error details returned by the API, if any.
        self.errors: list = errors if errors is not None else []

        super().__init__(f"Schwab API Error {status}: {message}")


class UnauthorizedError(ApiError):
    """Raised when the API returns HTTP 401 (invalid or insufficient token)."""
    _CODE = 401


class ForbiddenError(ApiError):
    """Raised when the API returns HTTP 403 (forbidden)."""
    _CODE = 403


class ResourceNotFoundError(ApiError):
    """Raised when the API returns HTTP 404 (resource not found)."""
    _CODE = 404


class RateLimitError(ApiError):
    """Raised when the API returns HTTP 429 (rate limited)."""
    _CODE = 429


class ServerError(ApiError):
    """Raised when the API returns an HTTP 5xx error."""
    _RANGE = (500, 599)


class ServiceUnavailableError(ServerError):
    """Raised when the API returns HTTP 503 (temporary/service unavailable)."""
    _CODE = 503


class StreamError(SectoremError):
    """Raised when the streaming connection encounters an error."""
