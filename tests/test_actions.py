import pytest
import trio_asyncio

import spins_halp_line.actions.conferences
from spins_halp_line.actions import twilio
from spins_halp_line.actions import twilio
from spins_halp_line.media.common import Conference_Hold_Music
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library


@pytest.mark.trio
async def test_text():
    async with trio_asyncio.open_loop() as loop:
        await twilio.send_sms(
            PhoneNumber("+15102567675"),
            PhoneNumber("+14156864014"),
            "test",
            "https://profspins.free.resourcespace.com/filestore/profspins/1/0/0/2_e2dc8a9cb060268/1002_b37689743a1edeb.png"
        )

@pytest.mark.trio
async def test_conf():
    await Conference_Hold_Music.load()
    assert "mp3" in Conference_Hold_Music.url

@pytest.mark.trio
async def test_audio():
    conf = await spins_halp_line.actions.conferences.new_conference()
    print(conf.twiml_xml(PhoneNumber("+14156864014")))

@pytest.mark.trio
async def test_number_index():
    await Global_Number_Library.load()

    print(Global_Number_Library.random())
