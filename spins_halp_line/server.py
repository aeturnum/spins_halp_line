from hypercorn.config import Config
from hypercorn.trio import serve
from quart_trio import QuartTrio
from quart import request
import trio_asyncio
import trio
from functools import partial

from twilio.twiml.voice_response import VoiceResponse

app = QuartTrio(__name__)
config = Config.from_toml("./hypercorn.toml")
add_task, get_task = trio.open_memory_channel(50)

@app.route('/')
async def hello():
    return 'hello'

# https://support.glitch.com/t/tutorial-how-to-auto-update-your-project-with-github/8124
@app.route("/git", methods=['POST'])
async def pull_git():
    if request.headers['x-github-event'] == "push":
        print("Git repo updateing, pulling changes")
        await add_task.send({"task": "pull"})
    return ""

@app.route("/main", methods=['GET', 'POST'])
async def main_number():
    resp = VoiceResponse()

    # Read a message aloud to the caller
    resp.say("hello world!", voice='alice')

    return str(resp)


async def work_queue():
    async for task in get_task:
        print(f"got task: {task}")
        try:
            if task['task'] =='pull':
                result = await trio.run_process("./pull_git.sh", shell=True)
                print(result)
        except Exception as e:
            print(f"Task got exception: {e}")
            pass


async def async_layer():
    async with trio_asyncio.open_loop() as loop:
        async with trio.open_nursery() as nurse:
            # start our own
            nurse.start_soon(partial(serve, app, config))
            nurse.start_soon(work_queue)
            # nurse.start_soon(QuartTrio.run_task, *[app, "127.0.0.1", 5000, True])

trio_asyncio.run(async_layer)

