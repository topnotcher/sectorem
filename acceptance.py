"""Acceptance test — verify the full SchwabClient stack against the live API."""

import asyncio
import os
import logging

from sectorem import SchwabClient, FileTokenStore


async def main():
    logging.basicConfig(level=logging.DEBUG)

    app_key = os.environ["SCHWAB_APP_KEY"]
    app_secret = os.environ["SCHWAB_APP_SECRET"]
    token_path = os.environ.get("SCHWAB_TOKEN_PATH", "~/.sectorem/token.json")

    async with SchwabClient(
        app_key=app_key,
        app_secret=app_secret,
        token_store=FileTokenStore(token_path),
    ) as client:
        print("Authenticated.")

        print("\n--- Account Numbers ---")
        accounts = await client.trader.get_account_numbers()
        for acct in accounts:
            print(f"{acct}")

        for account in await client.trader.get_accounts():
            print(f"\n--- Account Positions ({account.nickname} {account.account_number}) ---")
            positions = await account.get_positions()
            for position in positions:
                print(position)


            print(f"\n--- Account Balances ({account.nickname} {account.account_number}) ---")
            print(await account.get_balances())

        print("\n--- Quotes ---")
        quotes = await client.market.get_quotes(["AAPL", "MSFT", "SPY"])
        for symbol, data in quotes.items():
            quote = data.get("quote", {})
            print(f"  {symbol}: last={quote.get('lastPrice')} bid={quote.get('bidPrice')} ask={quote.get('askPrice')}")

        print("\n--- User Preferences ---")
        prefs = await client.trader.get_user_preferences()
        streamer_info = prefs.get("streamerInfo", [])
        if streamer_info:
            print(f"  Streamer URL: {streamer_info[0].get('streamerSocketUrl', 'N/A')}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
