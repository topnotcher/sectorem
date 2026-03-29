# sectorem

Async Python client for the Charles Schwab Trader API.

## Status

Early development. Auth module is in progress; trading client is not yet
implemented.

## Design

- **Async-first** — built on `aiohttp`, no sync wrappers.
- **Pluggable auth** — token storage, callback server, and login prompt
  are all swappable interfaces.
- **Clean abstractions** — typed models for orders, positions, and
  accounts rather than raw JSON.

## Installation

From source (development):

```bash
pip install -e ".[dev]"
```

## Auth Architecture

The `Authenticator` manages the full OAuth2 lifecycle as a state machine:

- **Token storage** — `TokenStore` ABC with a built-in `FileTokenStore`.
  Implement your own for Vault, database, etc.
- **Callback server** — `CallbackServer` ABC with a built-in aiohttp
  implementation.  Pass your own if you already run a web server.
- **Login prompt** — any async callable that presents a URL to the user
  (open a browser, print to stdout, send a Slack message, etc.).
- **Proactive re-auth** — prompts for re-authorization before the
  7-day refresh token expires (configurable threshold).
