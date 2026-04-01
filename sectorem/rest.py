"""Base authenticated REST client for Schwab APIs."""

from __future__ import annotations

import logging
from typing import Any

from .auth import AuthProvider
from .errors import ApiError, RateLimitError

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
            if resp.status == 429:
                body = await resp.text()
                raise RateLimitError(resp.status, "Rate limited", response_body=body)
            if resp.status >= 400:
                body = await resp.text()
                raise ApiError(resp.status, resp.reason or "Unknown error", response_body=body)
            if resp.content_type == "application/json":
                return await resp.json()
            else:
                return {}

    async def _get(self, path: str, **kwargs: Any) -> dict:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs: Any) -> dict:
        return await self._request("POST", path, **kwargs)

    async def _put(self, path: str, **kwargs: Any) -> dict:
        return await self._request("PUT", path, **kwargs)

    async def _delete(self, path: str, **kwargs: Any) -> dict:
        return await self._request("DELETE", path, **kwargs)
