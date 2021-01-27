import subprocess
import json
from typing import List

from hypercorn.config import Config
from hypercorn.trio import serve
from quart_trio import QuartTrio
from quart import request, websocket, jsonify
import trio_asyncio
import trio
from functools import partial

from trio import MemoryReceiveChannel
from twilio.twiml.voice_response import VoiceResponse, Play

from spins_halp_line.tasks import Trio_Task_Task_Object_Runner, GitUpdate, Task, add_task
from spins_halp_line.twil import t_resp, TwilRequest
from spins_halp_line.util import do_monkey_patches, get_logger
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from spins_halp_line.media.common import All_Resources
from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.stories.story_objects import (
    Script,
    confused_response
)
from spins_halp_line.media.common import (
    End_A, End_B, End_C, End_D, End_E, End_F, End_G, End_H, End_I, End_J
)
from spins_halp_line.stories.telemarketopia import telemarketopia
from spins_halp_line.stories.tele_story_objects import TeleShard
from spins_halp_line.events import event_websocket, send_event
from spins_halp_line.player import Player
from spins_halp_line.actions.conferences import (
    Conf_Twiml_Path,
    Conf_Status_Path,
    conferences,
    load_conferences
)
from spins_halp_line.debug import Snapshot

Script.add_script(telemarketopia)

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
            ss = Snapshot(script, req.player)
            response = await script.play(req, ss)
            break

    # start a new game
    if not response:
        for script in Script.Active_Scripts:
            if await script.call_could_start_game(req):
                ss = Snapshot(script, req.player)
                response = await script.play(req, ss)
                break

    if not response:
        response = confused_response()

    # save any state changes we recorded
    await req.player.save()

    return t_resp(response)

@app.route("/tipline/sms", methods=['GET', 'POST'])
async def handle_text():
    req = TwilRequest(request)
    await req.load()

    for script in Script.Active_Scripts:
        if await script.player_playing(req):
            ss = Snapshot(script, req.player)
            await script.process_text(req, ss)
            break

    return t_resp("")


#   _____ _ _                            _____
#  / ____| (_)                          |  __ \
# | |    | |_ _ __ ___   __ ___  _____  | |__) |___  ___ _ __   ___  _ __  ___  ___  ___
# | |    | | | '_ ` _ \ / _` \ \/ / _ \ |  _  // _ \/ __| '_ \ / _ \| '_ \/ __|/ _ \/ __|
# | |____| | | | | | | | (_| |>  <  __/ | | \ \  __/\__ \ |_) | (_) | | | \__ \  __/\__ \
#  \_____|_|_|_| |_| |_|\__,_/_/\_\___| |_|  \_\___||___/ .__/ \___/|_| |_|___/\___||___/
#                                                       | |
#                                                       |_|

async def get_ending_response(endings: List[RSResource]):
    response = VoiceResponse()

    for e in endings:
        p = Play(url=e.url, loop=1)
        response.append(p)

    return t_resp(response)

@app.route("/climax/1/1", methods=['GET', 'POST'])
async def ending_11():
    return get_ending_response([End_C, End_B])

@app.route("/climax/1/2", methods=['GET', 'POST'])
async def ending_12():
    return get_ending_response([End_F, End_F, End_B])

@app.route("/climax/1/3", methods=['GET', 'POST'])
async def ending_13():
    return get_ending_response([End_A, End_E, End_F])

@app.route("/climax/2/1", methods=['GET', 'POST'])
async def ending_21():
    return get_ending_response([End_C, End_D])

@app.route("/climax/2/2", methods=['GET', 'POST'])
async def ending_22():
    return get_ending_response([End_D, End_D, End_G])

@app.route("/climax/2/3", methods=['GET', 'POST'])
async def ending_23():
    return get_ending_response([End_A, End_F, End_E, End_D])

@app.route("/climax/3/1", methods=['GET', 'POST'])
async def ending_31():
    return get_ending_response([End_C, End_A])

@app.route("/climax/3/2", methods=['GET', 'POST'])
async def ending_32():
    return get_ending_response([End_A, End_E, End_F])

@app.route("/climax/3/3", methods=['GET', 'POST'])
async def ending_33():
    return get_ending_response([End_H])

# final climax responses
@app.route("/finalclimax/right", methods=['GET', 'POST'])
async def final_final_right():
    return get_ending_response([End_J])

@app.route("/finalclimax/wrong", methods=['GET', 'POST'])
async def final_final_wrong():
    return get_ending_response([End_I])

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
    req = TwilRequest(request)
    await req.load()

    # normalize format
    num1: str = PhoneNumber(req.data['num1']).e164
    num2: str = PhoneNumber(req.data['num2']).e164

    from spins_halp_line.stories.telemarketopia_conferences import ConfStartFirst, StoryInfo

    # update shared state
    shard: TeleShard = telemarketopia.state_manager.shard
    shard.append('clavae_in_conf', num1)
    shard.append('clavae_players', num1)
    shard.append('karen_in_conf', num2)
    shard.append('karen_players', num2)
    await telemarketopia.integrate_shard(shard)

    # start process
    await add_task.send(
        ConfStartFirst(StoryInfo(num1, num2, telemarketopia.state_manager.shard))
    )

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

@app.route("/debug/snapshot/<snap_num>", methods=['POST'])
async def load_snapshot(snap_num):
    snap = Snapshot.get_snapshot(snap_num)
    if snap:
        await snap.restore()

    return ""

@app.route("/debug/snapshot", methods=['POST'])
async def load_snapshot_from_body():
    req = TwilRequest(request)
    await req.load()
    snap = Snapshot.from_json(req.data.get('snapshot'))
    if snap:
        await snap.restore()

    return ""

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
