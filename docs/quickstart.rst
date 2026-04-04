Quick Start
===========

Install
-------

.. code-block:: bash

   pip install git+https://github.com/topnotcher/sectorem.git

Or clone and install locally:

.. code-block:: bash

   git clone https://github.com/topnotcher/sectorem.git
   pip install -e sectorem/

Setup
-----

You need a Schwab developer account and an application registered at
`developer.schwab.com <https://developer.schwab.com>`_. From your app
dashboard, grab the **App Key** and **Secret**.

Basic usage
-----------

::

    import asyncio
    from sectorem import SchwabClient, FileTokenStore

    async def main():
        async with SchwabClient(
            app_key="YOUR_APP_KEY",
            app_secret="YOUR_APP_SECRET",
            token_store=FileTokenStore("~/.sectorem/token.json"),
        ) as client:
            # List accounts
            accounts = await client.trader.get_accounts()

            # Get positions for each account
            for acct in accounts:
                positions = await acct.get_positions()
                for pos in positions:
                    print(f"{pos.instrument.symbol}: {pos.quantity} @ {pos.market_value}")

    asyncio.run(main())

On first run, the :class:`~sectorem.auth.manager.Authenticator` prints an
authorization URL to stdout. Open it in a browser, log in to Schwab,
and the callback server captures the redirect automatically. The token
is saved to ``~/.sectorem/token.json`` and reused on subsequent runs —
you won't need to log in again until the refresh token expires (7 days).

Custom authenticator
--------------------

:class:`~sectorem.client.SchwabClient` builds an
:class:`~sectorem.auth.manager.Authenticator` internally, but you can
instantiate one yourself for more control — custom callback server,
login prompt, or token refresh timing::

    from sectorem.auth import Authenticator
    from sectorem import FileTokenStore, SchwabClient

    auth = Authenticator(
        app_key="YOUR_APP_KEY",
        app_secret="YOUR_APP_SECRET",
        token_store=FileTokenStore("~/.sectorem/token.json"),
        server_factory=my_server_factory,
        login_prompt=my_prompt,
        reauth_threshold=timedelta(days=2),
    )

    async with SchwabClient(auth=auth) as client:
        ...

See :doc:`auth` for the full authentication architecture — custom
auth providers, callback servers, and token lifecycle details.
