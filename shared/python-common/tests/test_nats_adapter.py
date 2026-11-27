import asyncio

import pytest
from nats.errors import TimeoutError as NatsTimeout
from nats.js.client import FetchTimeoutError

from baolsec_common.messaging.nats_adapter import NatsSubscription


class FakeSubscription:
    def __init__(self, error):
        self.error = error

    async def fetch(self, batch, timeout):
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        asyncio.TimeoutError(),
        NatsTimeout(),
        FetchTimeoutError(),
    ],
)
async def test_fetch_returns_empty_list_on_timeout(error):
    subscription = NatsSubscription(FakeSubscription(error))

    result = await subscription.fetch(batch=100, timeout=1)

    assert result == []


async def test_fetch_propagates_unexpected_errors():
    error = RuntimeError("erreur inattendue")
    subscription = NatsSubscription(FakeSubscription(error))

    with pytest.raises(RuntimeError, match="erreur inattendue"):
        await subscription.fetch(batch=100, timeout=1)
