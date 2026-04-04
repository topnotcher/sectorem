Market Data API
===============

The :class:`~sectorem.market.client.MarketDataClient` wraps the Schwab Market
Data API. As with the Trader API, the inherited REST methods are available for
endpoints that aren't wrapped yet::

    # Wrapped
    quotes = await client.market.get_quotes(["AAPL", "MSFT"])

    # Unwrapped endpoint
    movers = await client.market.get("movers/SPX", params={"direction": "up"})

.. autoclass:: sectorem.market.client.MarketDataClient
   :members:
   :inherited-members:
