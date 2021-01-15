import subprocess
import json

from hypercorn.config import Config
from hypercorn.trio import serve
from quart_trio import QuartTrio
from quart import request, websocket, jsonify
import trio_asyncio
import trio
from functools import partial

from trio import MemoryReceiveChannel

from spins_halp_line.tasks import Trio_Task_Task_Object_Runner, GitUpdate, Task, add_task
from spins_halp_line.twil import t_resp, TwilRequest
from spins_halp_line.util import do_monkey_patches, get_logger
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from spins_halp_line.media.common import All_Resources
from spins_halp_line.stories.story_objects import Script, confused_response
from spins_halp_line.stories.shipwreck_adventure import adventure
from spins_halp_line.stories.telemarketopia import telemarketopia
from spins_halp_line.events import event_websocket, send_event
from spins_halp_line.player import Player
from spins_halp_line.actions.conferences import (
    Conf_Twiml_Path,
    Conf_Status_Path,
    TwilConference,
    new_conference,
    conferences,
    load_conferences
)

Script.add_script(adventure)

do_monkey_patches()

app = QuartTrio(__name__)
config = Config.from_toml("./hypercorn.toml")

message = subprocess.run(['git', 'log', '-1', '--pretty=%B'], capture_output=True)
message = message.stdout.decode()

log = get_logger()


@app.route('/')
async def hello():
    await send_event(f"returning home page!")
    # server is up
    return f"""
    <head>
        <script src="https://cdn.jsdelivr.net/npm/umbrellajs"></script>
    </head>
    <body>
        <p>{message}</p>
        <div id="events"></div>
        <script>
            this.socket = new WebSocket(`wss://${{document.domain}}/events/ws`)

            this.socket.addEventListener("message", (event) => {{
                u('#events').append(`<pre>${{event.data}}</pre>`)
            }})

        </script>
    </body>
    """

@app.websocket('/events/ws')
@event_websocket
async def events(read_channel: MemoryReceiveChannel):
    while True:
        message = await read_channel.receive()
        await websocket.send(message)

# ascii text generated by: https://www.kammerl.de/ascii/AsciiSignature.php ("big" font)
#  _______       _ _ _         ______           _             _       _
# |__   __|     (_) (_)       |  ____|         | |           (_)     | |
#    | |_      ___| |_  ___   | |__   _ __   __| |_ __   ___  _ _ __ | |_ ___
#    | \ \ /\ / / | | |/ _ \  |  __| | '_ \ / _` | '_ \ / _ \| | '_ \| __/ __|
#    | |\ V  V /| | | | (_) | | |____| | | | (_| | |_) | (_) | | | | | |_\__ \
#    |_| \_/\_/ |_|_|_|\___/  |______|_| |_|\__,_| .__/ \___/|_|_| |_|\__|___/
#                                                | |
#                                                |_|


# much thanks to https://github.com/TwilioDevEd/ivr-phone-tree-python/blob/master/ivr_phone_tree_python/views.py
@app.route("/tipline/start", methods=['GET', 'POST'])
async def main_number():
    req = TwilRequest(request)
    response = None

    await req.load()

    # players already in a game
    # todo: improve this system
    for script in Script.Active_Scripts:
        if await script.player_playing(req):
            response = await script.play(req)
            break

    # start a new game
    if not response:
        for script in Script.Active_Scripts:
            if await script.call_could_start_game(req):
                response = await script.play(req)
                break

    if not response:
        response = confused_response()

    # save any state changes we recorded
    await req.player.save()

    return t_resp(response)

#   _____             __                                _____      _ _ _                _
#  / ____|           / _|                              / ____|    | | | |              | |
# | |     ___  _ __ | |_ ___ _ __ ___ _ __   ___ ___  | |     __ _| | | |__   __ _  ___| | _____
# | |    / _ \| '_ \|  _/ _ \ '__/ _ \ '_ \ / __/ _ \ | |    / _` | | | '_ \ / _` |/ __| |/ / __|
# | |___| (_) | | | | ||  __/ | |  __/ | | | (_|  __/ | |___| (_| | | | |_) | (_| | (__|   <\__ \
#  \_____\___/|_| |_|_| \___|_|  \___|_| |_|\___\___|  \_____\__,_|_|_|_.__/ \__,_|\___|_|\_\___/
#

# This is POST be default and can be set to get but who cares, do both
@app.route(Conf_Twiml_Path, methods=["GET", "POST"])
async def get_conf_connection_twil(c_number):
    req = TwilRequest(request)
    await req.load()

    confs = conferences()

    for conf in confs:
        if conf == c_number:
            return t_resp(await conf.twiml_xml(req.num_called))

@app.route(Conf_Status_Path, methods=["GET", "POST"])
async def conf_status_update(c_number):
    req = TwilRequest(request)
    await req.load()

    confs = conferences()

    for conf in confs:
        if conf == c_number:
            await conf.handle_conf_event(req.data)
    # just 200-ok them
    return ""



#
#  _____       _                       _               ______           _             _       _
# |  __ \     | |                     (_)             |  ____|         | |           (_)     | |
# | |  | | ___| |__  _   _  __ _  __ _ _ _ __   __ _  | |__   _ __   __| |_ __   ___  _ _ __ | |_ ___
# | |  | |/ _ \ '_ \| | | |/ _` |/ _` | | '_ \ / _` | |  __| | '_ \ / _` | '_ \ / _ \| | '_ \| __/ __|
# | |__| |  __/ |_) | |_| | (_| | (_| | | | | | (_| | | |____| | | | (_| | |_) | (_) | | | | | |_\__ \
# |_____/ \___|_.__/ \__,_|\__, |\__, |_|_| |_|\__, | |______|_| |_|\__,_| .__/ \___/|_|_| |_|\__|___/
#                           __/ | __/ |         __/ |                    | |
#                          |___/ |___/         |___/                     |_|
@app.route("/debug/conf", methods=["POST"])
async def debug_conf_call():
    from spins_halp_line.media.common import Shazbot, Look_At_You_Hacker
    req = TwilRequest(request)
    await req.load()

    num1 = PhoneNumber(req.data['num1'])
    num2 = PhoneNumber(req.data['num2'])
    from_num = Global_Number_Library.random()

    conf = await new_conference()
    await conf.add_participant(from_num, num1, play_first=Look_At_You_Hacker)
    await conf.add_participant(from_num, num2, play_first=Shazbot)

    return ""


@app.route("/debug", methods=["GET"])
async def debug_interface():
    return f"""
        <head>
            <link rel="stylesheet" type="text/css" href="/css/jsonview.bundle.css">
            <link rel="stylesheet" type="text/css" href="/css/main.css">
            <script src="/js/jsonview.bundle.js"></script>
            <script src="/js/umbrella.min.js"></script>
        </head>
        <body>
            <main class="wrapper">
                <div class="left">
                    <table id="players">
                    </table>
                </div>
                <div class="right" id="json"></div>
            </main>
        <script src="/js/debug.js"></script>
        </body>
        """

@app.route("/debug/players", methods=['GET'])
async def list_players():
    return jsonify(await Player.get_all_json())

@app.route("/debug/players/<p_num>", methods=['DELETE'])
async def delete_player(p_num):
    return str(await Player.reset(Player.from_number(p_num)))
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
        await add_task.send(GitUpdate())
    return ""


#   _____                            ____        _ _            _
#  / ____|                          |  _ \      | | |          | |
# | (___   ___ _ ____   _____ _ __  | |_) | ___ | | | ___   ___| | _____
#  \___ \ / _ \ '__\ \ / / _ \ '__| |  _ < / _ \| | |/ _ \ / __| |/ / __|
#  ____) |  __/ |   \ V /  __/ |    | |_) | (_) | | | (_) | (__|   <\__ \
# |_____/ \___|_|    \_/ \___|_|    |____/ \___/|_|_|\___/ \___|_|\_\___/


# Helper class to do any async loading that needed before we start accepting connections
class ServerLoad(Task):
    _re_raise_exceptions = True # crash proper when we crash

    def __init__(self, nursry: trio.Nursery, serve_function):
        super(ServerLoad, self).__init__()

        self._nurse = nursry
        self._serve = serve_function

    async def execute(self):
        self.d("Server Startup Beginning")

        self.d("Loading Global Number Library")
        await Global_Number_Library.load()
        self.d("Server Loading Finished")

        self.d("Loading Shared Media Files")
        for resource in All_Resources:
            await resource.load()
        self.d("Done Loading Shared Media Files")

        self.d("Loading ongoing Conferences from redis!")
        await load_conferences()
        self.d("Conferences loaded!")

        self.d("Loading script state from redis!")
        # in theory we should use the script index but we don't have the time for that
        await telemarketopia.load_state()
        self.d("State loaded!")

        self.d("Starting Web Server")
        self._nurse.start_soon(self._serve)


async def async_layer():
    async with trio_asyncio.open_loop():
        async with trio.open_nursery() as nurse:
            # start our own
            # do any server loading needed
            await add_task.send(ServerLoad(nurse, partial(serve, app, config)))
            nurse.start_soon(Trio_Task_Task_Object_Runner)


trio_asyncio.run(async_layer)
