import pytest
import trio_asyncio

# With thanks to the trio-asyncio testing code
# https://github.com/python-trio/trio-asyncio/blob/master/tests/conftest.py

@pytest.fixture
async def loop():
    async with trio_asyncio.open_loop() as loop:
        try:
            yield loop
        finally:
            await loop.stop().wait()