from quart import websocket
from quart_trio import QuartTrio
import trio_asyncio
import trio

app = QuartTrio(__name__)

@app.route('/')
async def hello():
    return 'hello'

@app.websocket('/ws')
async def ws():
    while True:
        await websocket.send('hello')

async def async_layer():
    async with trio_asyncio.open_loop() as loop:
        async with trio.open_nursery() as nurse:
            # start our own
            nurse.start_soon(QuartTrio.run_task, *[app, "127.0.0.1", 5000, True])

trio_asyncio.run(async_layer)

# QuartTrio.run_task("127.0.0.1", 5000, True)
