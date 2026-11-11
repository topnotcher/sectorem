"""Tests for the streaming client."""

from __future__ import annotations

import asyncio
import gc
import logging
from unittest.mock import AsyncMock

import pytest

from sectorem.stream.client import StreamClient, _Handle, _WireState


def make_client() -> StreamClient:
    return StreamClient(
        AsyncMock(), url="wss://example.com", customer_id="c", correl_id="r", channel="N9", function_id="F",
    )


class TestUnsubscribeShutdown:
    @pytest.mark.asyncio
    async def test_failed_unsubs_does_not_leak_unretrieved_exception(self, caplog):
        client = make_client()
        handle = _Handle(service="ACCT_ACTIVITY", keys="k", fields=(0,), callback=lambda e: None)
        client._handles.add(handle)
        client._wire["ACCT_ACTIVITY"] = _WireState(keys={"k"}, fields={0})

        # Removing the last handle enqueues an UNSUBS nobody awaits; then the
        # connection goes away before any response arrives.
        client._handles.remove(handle)
        client._sync_unsubscribe("ACCT_ACTIVITY")
        client._fail_pending("Connection lost")
        await asyncio.sleep(0)  # let done callbacks run

        with caplog.at_level(logging.ERROR, logger="asyncio"):
            del client
            gc.collect()
            await asyncio.sleep(0)

        assert "never retrieved" not in caplog.text


class TestSendCommandLogging:
    @pytest.mark.asyncio
    async def test_login_is_logged_without_the_token_or_ids(self, caplog):
        client = StreamClient(
            AsyncMock(), url="wss://example.com", customer_id="customer-1234", correl_id="correl-5678",
            channel="N9", function_id="APIAPP",
        )
        ws = AsyncMock()
        cmd = client._make_command("ADMIN", "LOGIN", {
            "Authorization": "access-token-abcd", "SchwabClientChannel": "N9", "SchwabClientFunctionId": "APIAPP",
        })

        with caplog.at_level(logging.DEBUG, logger="sectorem.stream"):
            await client._send_command(ws, cmd)

        assert "Sending ADMIN LOGIN (request 0)" in caplog.text
        assert "'Authorization': '<masked>'" in caplog.text
        for secret in ("access-token-abcd", "customer-1234", "correl-5678"):
            assert secret not in caplog.text
        sent = ws.send_json.call_args.args[0]["requests"][0]
        assert sent["parameters"]["Authorization"] == "access-token-abcd"
        assert (sent["SchwabClientCustomerId"], sent["SchwabClientCorrelId"]) == ("customer-1234", "correl-5678")
