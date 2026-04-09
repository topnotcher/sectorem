Streaming API
=============

The :class:`~sectorem.stream.StreamClient` connects to Schwab's WebSocket
streaming API for real-time market data and account activity. It manages the
connection lifecycle, automatic reconnection, and subscription tracking.

The streaming client is available via :attr:`~sectorem.client.SchwabClient.stream`
after calling :meth:`~sectorem.client.SchwabClient.start`::

    async with SchwabClient(...) as client:
        sub = await client.stream.subscribe(
            StreamService.LEVELONE_EQUITIES, on_quote,
            keys="AAPL,MSFT",
            fields=[EquityField.BID_PRICE, EquityField.ASK_PRICE, EquityField.LAST_PRICE],
        )

        # ... later
        await sub.cancel()

Each subscription returns a :class:`~sectorem.stream.Subscription` handle
that can be cancelled independently. The connection is opened lazily on the
first subscription and closed when the last one is cancelled.

Schwab's streaming API uses numeric field identifiers in both requests and
responses. The streaming client handles this translation automatically:
subscribe with named fields from the service's enum (e.g.
:attr:`~sectorem.stream.fields.EquityField.BID_PRICE`), and callbacks receive
data with those same names as keys rather than raw numbers.

Client
------

.. autoclass:: sectorem.stream.StreamClient
   :members:

.. autoclass:: sectorem.stream.Subscription
   :members:

Services and Fields
-------------------

.. automodule:: sectorem.stream.fields
   :members:
   :undoc-members:
