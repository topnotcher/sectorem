"""Acceptance test — verify the full SchwabClient stack against the live API."""

import asyncio
import os

from sectorem import SchwabClient, FileTokenStore


async def main():
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
            print(f"  {acct['accountNumber']} -> {acct['hashValue']}")

        if accounts:
            hash_value = accounts[0]["hashValue"]

            print(f"\n--- Account Detail ({accounts[0]['accountNumber']}) ---")
            detail = await client.trader.get_account(hash_value, fields=["positions"])
            print(f"  Type: {detail['securitiesAccount']['type']}")

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
