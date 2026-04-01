"""Base authenticated REST client for Schwab APIs."""

from __future__ import annotations

import logging
import aiohttp
from typing import Any

from .auth import AuthProvider
from .errors import ApiError

log = logging.getLogger(__name__)


class RestClient:
    """
    Base HTTP client for Schwab API endpoints.

    Subclasses (e.g. ``TraderClient``, ``MarketDataClient``) add
    endpoint-specific methods on top.

    Authentication and session management are delegated to the
    :class:`~sectorem.auth.AuthProvider`: the session returned by
    :meth:`~sectorem.auth.AuthProvider.get_authenticated_session`
    automatically injects the Bearer token into every request.

    :param auth: Auth provider supplying the authenticated session.
    :param base_url: API base URL (e.g.
        ``https://api.schwabapi.com/trader/v1``).
    """

    def __init__(self, auth: AuthProvider, base_url: str) -> None:
        self._auth = auth
        self._base_url = base_url.rstrip("/")

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
        session = self._auth.get_authenticated_session()

        async with session.request(method, url, **kwargs) as resp:
            if resp.status >= 400:
                await self._api_error_from_resp(resp)

            if resp.content_type == "application/json":
                return await resp.json()
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

    async def _get(self, path: str, **kwargs: Any) -> dict:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs: Any) -> dict:
        return await self._request("POST", path, **kwargs)

    async def _put(self, path: str, **kwargs: Any) -> dict:
        return await self._request("PUT", path, **kwargs)

    async def _delete(self, path: str, **kwargs: Any) -> dict:
        return await self._request("DELETE", path, **kwargs)
