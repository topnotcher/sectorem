"""Base authenticated REST client for Schwab APIs."""

from __future__ import annotations

import json
import logging

import aiohttp
from aiohttp import ClientRequest, ClientResponse, ClientHandlerType, ClientSession
from typing import Any

from .auth import AuthProvider
from .errors import ApiError

log = logging.getLogger(__name__)


class PrettyFloat(float):
    """A float that displays with 4 decimal places."""

    def __repr__(self) -> str:
        return f"{self:.4f}"

    __str__ = __repr__


class RestClient:
    """
    Base HTTP client for Schwab API endpoints.

    Subclasses (e.g. ``TraderClient``, ``MarketDataClient``) add
    endpoint-specific methods on top.

    Each client owns its own :class:`aiohttp.ClientSession` that
    automatically injects the Bearer token into every request via
    the :class:`~sectorem.auth.AuthProvider`.

    :param auth: Auth provider supplying the access token.
    :param base_url: API base URL (e.g.
        ``https://api.schwabapi.com/trader/v1``).
    """

    def __init__(self, auth: AuthProvider, base_url: str) -> None:
        self._auth = auth
        self._base_url = base_url.rstrip("/")
        self._session: ClientSession | None = None

    async def _get_session(self) -> ClientSession:
        if self._session is None:
            self._session = ClientSession(middlewares=(self._auth_middleware,))
        return self._session

    async def _auth_middleware(self, req: ClientRequest, handler: ClientHandlerType) -> ClientResponse:
        req.headers["Authorization"] = f'Bearer {await self._auth.get_access_token()}'
        return await handler(req)

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict:
        """
        Make an authenticated request to the Schwab API.

        Builds the full URL from *base_url* and *path* and maps
        HTTP errors to exception types.

        :param method: HTTP method.
        :param path: URL path relative to the base URL.
        :param kwargs: Passed through to :meth:`aiohttp.ClientSession.request`.
        :returns: Parsed JSON response.
        :raises ApiError: On non-2xx responses.
        :raises RateLimitError: On HTTP 429.
        """
        url = f"{self._base_url}/{path.lstrip('/')}"
        session = await self._get_session()

        async with session.request(method, url, **kwargs) as resp:
            if resp.status >= 400:
                await self._api_error_from_resp(resp)

            if resp.content_type == "application/json":
                text = await resp.text()
                return json.loads(text, parse_float=PrettyFloat)
            else:
                return {}

    @staticmethod
    async def _api_error_from_resp(resp: aiohttp.ClientResponse) -> None:
        message = resp.reason
        errors = []
        if resp.content_type == "application/json":
            data = await resp.json()
            message = data.get("message", resp.reason or "Unknown error")
            errors = data.get("errors", [])

        correlation_id = resp.headers.get('Schwab-Client-CorrelID')

        if message is None:
            message = "Unknown error"

        raise ApiError(resp.status, message, errors=errors, correlation_id=correlation_id)

    async def get(self, path: str, **kwargs: Any) -> dict:
        """
        Make a GET request to the Schwab API.
        """
        return await self._request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> dict:
        """
        Make a POST request to the Schwab API.
        """
        return await self._request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> dict:
        """
        Make a PUT request to the Schwab API.
        """
        return await self._request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> dict:
        """
        Make a DELETE request to the Schwab API.
        """
        return await self._request("DELETE", path, **kwargs)
