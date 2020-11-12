import subprocess

from hypercorn.config import Config
from hypercorn.trio import serve
from quart_trio import QuartTrio
from quart import request, Response, url_for
import trio_asyncio
import trio
from functools import partial

from twilio.twiml.voice_response import VoiceResponse, Gather

app = QuartTrio(__name__)
config = Config.from_toml("./hypercorn.toml")
add_task, get_task = trio.open_memory_channel(50)

# hash = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True)
# hash = hash.stdout.decode()
message = subprocess.run(['git', 'log', '-1', '--pretty=%B'], capture_output=True)
message = message.stdout.decode()


@app.route('/')
async def hello():
    # server is up
    return message

#  _______       _ _ _         ______           _             _       _
# |__   __|     (_) (_)       |  ____|         | |           (_)     | |
#    | |_      ___| |_  ___   | |__   _ __   __| |_ __   ___  _ _ __ | |_ ___
#    | \ \ /\ / / | | |/ _ \  |  __| | '_ \ / _` | '_ \ / _ \| | '_ \| __/ __|
#    | |\ V  V /| | | | (_) | | |____| | | | (_| | |_) | (_) | | | | | |_\__ \
#    |_| \_/\_/ |_|_|_|\___/  |______|_| |_|\__,_| .__/ \___/|_|_| |_|\__|___/
#                                                | |
#                                                |_|

# much thanks to https://github.com/TwilioDevEd/ivr-phone-tree-python/blob/master/ivr_phone_tree_python/views.py

def twil(response):
    resp = Response(str(response))
    resp.headers['Content-Type'] = 'text/xml'
    return resp

@app.route("/tipline/start", methods=['GET', 'POST'])
async def main_number():
    print(f"Got call on main number: {request}")
    response = VoiceResponse()
    with response.gather( num_digits=1, action=url_for('game_tips'), method="POST") as g:
        g.say(message="This is doctor spins tip line!" +
                      "Please press 1 to do one thing" +
                      "Or press 2 to do another!.", loop=3)
    return twil(response)

@app.route('/tipline/tip', methods=['POST'])
async def game_tips():
    response = VoiceResponse()

    form = await request.form
    tip = form['Digits']
    response.say(f"You chose option {tip}")
    return twil(response)

#   _____ _ _     ______           _             _       _
#  / ____(_) |   |  ____|         | |           (_)     | |
# | |  __ _| |_  | |__   _ __   __| |_ __   ___  _ _ __ | |_ ___
# | | |_ | | __| |  __| | '_ \ / _` | '_ \ / _ \| | '_ \| __/ __|
# | |__| | | |_  | |____| | | | (_| | |_) | (_) | | | | | |_\__ \
#  \_____|_|\__| |______|_| |_|\__,_| .__/ \___/|_|_| |_|\__|___/
#                                   | |
#                                   |_|
#

# https://support.glitch.com/t/tutorial-how-to-auto-update-your-project-with-github/8124
@app.route("/git", methods=['POST'])
async def pull_git():
    if request.headers['x-github-event'] == "push":
        print("Git repo updateing, pulling changes")
        await add_task.send({"task": "pull"})
    return ""


#   _____                            ____        _ _            _
#  / ____|                          |  _ \      | | |          | |
# | (___   ___ _ ____   _____ _ __  | |_) | ___ | | | ___   ___| | _____
#  \___ \ / _ \ '__\ \ / / _ \ '__| |  _ < / _ \| | |/ _ \ / __| |/ / __|
#  ____) |  __/ |   \ V /  __/ |    | |_) | (_) | | | (_) | (__|   <\__ \
# |_____/ \___|_|    \_/ \___|_|    |____/ \___/|_|_|\___/ \___|_|\_\___/

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

