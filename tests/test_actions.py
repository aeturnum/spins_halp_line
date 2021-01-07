import pytest
import trio_asyncio

from spins_halp_line.actions import twilio

@pytest.mark.trio
async def test_text():
    async with trio_asyncio.open_loop() as loop:
        await twilio.send_sms("+12513192351", "+14156864014", "test")
