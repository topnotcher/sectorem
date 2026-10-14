Schwab API Notes
================

A field guide to the Schwab Trader and Market Data APIs as they actually
behave, as opposed to how they are documented. Everything here was found the
hard way while building sectorem, against live API traffic and compared to
thinkorswim (ToS). Where the official docs are silent, wrong, or
self-contradictory, this is the record so you don't have to rediscover it.

Treat the streaming section in particular as empirical: Schwab barely
acknowledges the streaming API exists, and the most detailed reference in
circulation is a third-party document of unknown provenance.

Balances
--------

The account endpoint returns three balance blocks -- ``initialBalances``,
``currentBalances``, and ``projectedBalances`` -- whose field sets overlap but
are inconsistent and do not match the documented schemas.

- ``stockBuyingPower`` and ``isInCall`` appear **only** in
  ``projectedBalances``; ``sma`` appears only in current. The three blocks are
  effectively snapshots taken at different times rather than a clean
  initial/current/projected split: during the after-hours session, current and
  projected carried identical ("current") values, and net liquidating value
  differed between blocks when it should not have.
- ``optionBuyingPower`` is sometimes absent entirely despite being documented.
  ``availableFundsNonMarginableTrade`` happened to match it, but that
  equivalence should not be assumed to hold in general.
- ``marginBalance`` was reported as ``0`` by the API while ToS showed it equal
  to the cash balance.
- API figures are consistently *close* to ToS but rarely exact, partly because
  the blocks come from different moments in time.

Because of all this, sectorem does not expose the raw three-block structure. It
merges the fields missing from ``currentBalances`` out of ``projectedBalances``
(the overlap is identical), presents a single ToS-aligned view, and raises on
genuinely missing fields rather than silently defaulting them. See
:doc:`design`.

Account metadata lives in user preferences
-------------------------------------------

Account nickname, account ``type`` (``BROKERAGE`` -- not to be confused with
the cash/margin distinction), account color, and the primary-account flag come
from the user preferences endpoint, not the accounts API. User preferences also
carry ``streamerInfo`` (socket URL and the client customer/correlation/channel
identifiers needed to open a stream). Most endpoints are per-account; user
preferences, "list accounts", account numbers, and -- surprisingly -- "get
orders" are not.

Positions and instruments
--------------------------

The instrument schemas do not match what the API actually returns.

- The docs show five position instrument schemas but eight asset types (eleven
  once the order and transaction APIs are included). Some schemas carry no
  ``assetType`` field at all.
- Undocumented schemas and enum values appear in practice: ``COLLECTIVE_INVESTMENT``
  positions are returned even though that schema is not listed for positions,
  and the instrument type ``EXCHANGE_TRADED_FUND`` appears in no documented
  schema. Expect asset types the docs do not mention.
- For options, the position ``symbol`` is the OCC contract string (for example
  ``SMCI  270115P00008000``). The underlying is provided separately, but only
  ``putCall`` has a dedicated field; strike and expiration must be parsed out of
  the OCC symbol (``SYMBOL YYMMDD{P,C}SSSSSSSS``, where the final eight digits
  are strike times 1000). sectorem does this parsing so callers get
  :class:`~sectorem.trader.types.OptionPosition` with proper ``strike``,
  ``expiration``, and ``right``.
- The order API's instrument object requires fields such as ``description`` and
  ``netChange`` that have no business being required, and its instrument schema
  does not match the ``OrderLeg`` schema.

Numeric precision
-----------------

Floating-point values arrive with precision artifacts from Schwab's side --
for example ``-346.709999999999`` for what is plainly ``-346.71``. The noise
originates upstream, so parsing into :class:`~decimal.Decimal` would only
faithfully preserve Schwab's imprecision rather than fix it. sectorem uses
``float`` and leaves rounding to display formatting.

Errors
------

The error envelope differs between APIs:

- The Trader API returns ``{"message": ..., "errors": [strings]}`` with a
  correlation id in the response headers.
- The Market Data API returns a JSON:API-style
  ``{"errors": [{"id", "status", "title", "detail", "source"}]}`` array with no
  top-level message.

A ``401`` does not necessarily mean a bad token: it is also returned when there
are no accounts the caller is permitted to view or trade through the
application. The Trader API distinguishes ``500`` (server error) from ``503``
(temporary); the Market Data API only defines ``401``.

Authentication
--------------

- Schwab permits an ``http://127.0.0.1`` OAuth callback; localhost is
  special-cased, where any other redirect must be HTTPS. The callback port does
  not need separate registration beyond the registered redirect URI.
- Refresh tokens expire a hard seven days after issue. Distinguish carefully
  between "access token expired, refresh still valid" and "refresh expired" --
  they are handled differently.

Streaming
---------

The streaming API is almost entirely reverse-engineered. The behaviors below
were confirmed against live connections.

- Fields are identified by single-digit **numeric keys**, interleaved with
  other content in the same object rather than grouped into an array. A
  bidirectional name/number mapping layer is required; sectorem keeps it inside
  the stream client so callers never see raw numeric fields.
- Fields are **global per service, not per key**. Once anything is subscribed
  for a service, an ``ADD`` command's fields do not apply only to the key being
  added, and ``VIEW`` changes the field view for the entire service. There is
  no per-key field selection.
- ``ACCT_ACTIVITY`` requires field ``0`` in the subscription. Omit it and the
  ``ADD`` is rejected; you cannot subscribe to account activity with an empty
  field list.
- Field ``0`` is contradictory. The docs call field 0 the symbol, yet responses
  contain no field 0 (the symbol is the message key), and subscribing with only
  ``0`` still returns fields 1, 2, and 3 -- so ``0`` behaves like "all fields"
  for at least some services. This is not fully pinned down.
- ``VIEW`` succeeds only when it includes field ``0`` (it sets the view
  globally); a ``VIEW`` without ``0`` was seen to fail with code 25
  (``FAILED_COMMAND_VIEW``), though not consistently.
- **EXTO orders generate no streaming account-activity events.** Plain ``EXT``
  orders do. EXTO orders are not routed, so any order workflow needs a polling
  fallback and cannot rely on streaming alone. Whether an unfilled EXTO that
  later routes then emits events is unconfirmed.
- The message sequence number resets at the start of every connection, so the
  documented advice to deduplicate by sequence number after a reconnect does
  not work -- every reconnect looks like a stream of duplicates.
- Schwab sends application-level heartbeats even though the WebSocket protocol
  provides its own ping/pong, likely to confirm connectivity through its
  internal infrastructure.
- Account-activity payloads are deeply nested and contain JSON-encoded strings
  inside the JSON, with the header duplicated and an order nested within an
  order. They expose data unavailable from REST (such as ``AccountState``) and
  still reference TD Ameritrade internals. In practice only ``message_type``,
  ``account_number``, and ``SchwabOrderID`` are needed from order events.

Order submission
----------------

Submitting an order returns ``HTTP 201`` with an empty body and a ``Location``
header pointing at ``GET /accounts/{accountNumber}/orders/{orderId}``; this is
mutually exclusive with a JSON response body. Follow the ``Location`` to
retrieve the created order. The ``orderId`` in that path is an integer.

Prior art
---------

``schwabdev`` and ``schwab-py`` (the successor to ``tda-api``) are existing
Schwab clients. Neither matched sectorem's goals -- async-first, cleanly
abstracted, pluggable authentication, and parsed objects rather than raw JSON --
which is why sectorem exists.
