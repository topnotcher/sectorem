Design Philosophy
=================

Sectorem is intended to be an an **abstraction layer** over the Schwab API, not
merely a wrapper. The goal is to hide the mess (Schwab API) behind a
predictable Python interface.

Typed Over Raw
--------------

API responses are parsed into objects such as frozen dataclasses and enums. A
position comes back as an :class:`~sectorem.trader.types.EquityPosition` or
:class:`~sectorem.trader.types.OptionPosition`, not a nested ``dict``. Option
instruments expose ``strike``, ``expiration``, and ``right`` as proper Python
types (``float``, ``date``, ``OptionRight``), extracted from the OCC symbol
since the API doesn't provide them as separate fields.

Async-only
----------

Sectorem is async from top to bottom, built on :mod:`aiohttp`. There
is no synchronous fallback. It's async first, and async only.

Flexible Authentication
-----------------------

The auth layer is split into an abstract :class:`~sectorem.auth.manager.AuthProvider`
interface and a concrete :class:`~sectorem.auth.manager.Authenticator`
implementation. The ``Authenticator`` runs the full OAuth2 flow with a
local callback server, automatic token refresh, and proactive
re-authorization before the refresh token expires.

But you don't have to use it. If you're running sectorem in a
distributed system where one process handles login and others just need
tokens, implement your own ``AuthProvider`` that reads tokens from Redis,
a database, or wherever they live. The rest of the library doesn't care
where the token came from.

Similarly, the callback server is pluggable. The default
:func:`~sectorem.auth.server.localhost_server` spins up a local HTTPS server
with a bundled self-signed certificate, but you can swap in your own
:class:`~sectorem.auth.server.CallbackServer` implementation if you need the
OAuth redirect to hit an existing web server.

Composition Over Monolith
-------------------------

:class:`~sectorem.client.SchwabClient` is a convenience container. It lazily
creates a :class:`~sectorem.trader.client.TraderClient` and
:class:`~sectorem.market.client.MarketDataClient`, each of which can also be
instaiated and used independely. independently. Account-level operations live
on the :class:`~sectorem.trader.client.Account` object returned by
:meth:`~sectorem.trader.client.TraderClient.get_account`, keeping the top-level
client focused on discovery and wiring. 
