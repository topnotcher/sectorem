"""Sectorem — async Python client for the Charles Schwab API."""

from .auth import AuthProvider, Authenticator, TokenStore
from .auth.token import FileTokenStore, Token
from .client import SchwabClient
from .errors import (
    ApiError,
    AuthenticationError,
    ForbiddenError,
    InvalidApiResponseError,
    NotAuthenticatedError,
    RateLimitError,
    ResourceNotFoundError,
    SectoremError,
    ServerError,
    ServiceUnavailableError,
    StreamError,
    UnauthorizedError,
)
from .market import MarketDataClient
from .rest import RestClient
from .stream import StreamClient, Subscription
from .trader import TraderClient

__all__ = [
    "ApiError",
    "AuthenticationError",
    "AuthProvider",
    "Authenticator",
    "FileTokenStore",
    "ForbiddenError",
    "InvalidApiResponseError",
    "MarketDataClient",
    "NotAuthenticatedError",
    "RateLimitError",
    "ResourceNotFoundError",
    "RestClient",
    "SchwabClient",
    "SectoremError",
    "ServerError",
    "ServiceUnavailableError",
    "StreamClient",
    "StreamError",
    "Subscription",
    "Token",
    "TokenStore",
    "TraderClient",
    "UnauthorizedError",
]
