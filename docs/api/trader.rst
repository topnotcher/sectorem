Trader API
==========

Client
------

The :class:`~sectorem.trader.client.TraderClient` wraps the Schwab Trader API.
Higher-level methods like :meth:`~sectorem.trader.client.TraderClient.get_account`
handle account hash resolution automatically. For endpoints that aren't wrapped
yet, the inherited REST methods (``get``, ``post``, ``put``, ``delete``) are
available directly — they take a path relative to the Trader API base URL and
return parsed JSON::

    # Wrapped
    account = await client.trader.get_account("123")

    # Unwrapped endpoint — use the REST methods directly
    orders = await client.trader.get("orders", params={"maxResults": "10"})

.. autoclass:: sectorem.trader.client.TraderClient
   :members:
   :inherited-members:

.. autoclass:: sectorem.trader.client.Account
   :members:

Types
-----

.. automodule:: sectorem.trader.types
   :members:
   :undoc-members:

Constants
---------

.. automodule:: sectorem.trader.constants
   :members:
   :undoc-members:
