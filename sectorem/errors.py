"""Sectorem exception hierarchy."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .trader.constants import OrderStatus
    from .trader.types import OrderResult


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


class InvalidApiResponseError(SectoremError):
    """Raised when an API response is missing expected fields or is otherwise malformed."""


class StreamError(SectoremError):
    """Raised when the streaming connection encounters an error."""


class OrderError(SectoremError):
    """
    Base for errors about the progress of a submitted order.

    Raised by :meth:`~sectorem.trader.order.OrderHandle.wait` and
    :meth:`~sectorem.trader.order.OrderHandle.cancel`. ``result`` carries the
    order as last read from the API, including any partial fills; see the
    subclasses for whether it is final.

    :param result: The order's last known state.
    :param message: Human-readable description.
    """

    def __init__(self, result: OrderResult, message: str) -> None:
        #: The order as last read from the API.
        self.result = result
        super().__init__(message)

    @property
    def order_id(self) -> int:
        """The Schwab order ID."""
        return self.result.order_id

    @property
    def status(self) -> OrderStatus:
        """The order status when the error was raised."""
        return self.result.status


class OrderNotFilledError(OrderError):
    """
    Raised when an awaited order reaches a terminal state other than ``FILLED``.

    The order is no longer working, so ``result`` is final. "Not filled" means
    not completely filled: a day order that partially filled before expiring
    raises this with a non-zero ``result.filled_quantity``.
    """

    def __init__(self, result: OrderResult) -> None:
        super().__init__(
            result, f"Order {result.order_id} is {result.status.value}; it will not fill{_fill_summary(result)}",
        )


class OrderTimeoutError(OrderError, TimeoutError):
    """
    Raised when waiting on an order exceeds the caller's timeout.

    The order is still working, so ``result`` is only a snapshot: more can fill
    between the last read and whatever the caller does next.

    :param result: The order as last read before the timeout.
    :param timeout: The timeout that elapsed, in seconds.
    """

    def __init__(self, result: OrderResult, timeout: float) -> None:
        #: The timeout that elapsed, in seconds.
        self.timeout = timeout
        super().__init__(
            result,
            f"Order {result.order_id} is still {result.status.value} after {timeout:g}s{_fill_summary(result)}",
        )


def _fill_summary(result: OrderResult) -> str:
    if result.filled_quantity:
        return f" ({result.filled_quantity:g} of {result.quantity:g} filled)"
    return ""
