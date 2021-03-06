import subprocess
from functools import partial
from typing import List

import trio
import trio_asyncio
from hypercorn.config import Config
from hypercorn.trio import serve
from quart import request, websocket, jsonify
from quart_trio import QuartTrio
from trio import MemoryReceiveChannel
from twilio.twiml.voice_response import VoiceResponse, Play

from spins_halp_line.actions.conferences import (
    Conf_Twiml_Path,
    Conf_Status_Path,
    conferences,
    load_conferences
)
from spins_halp_line.actions.twilio import make_call
from spins_halp_line.constants import Root_Url
from spins_halp_line.events import event_websocket, send_event
from spins_halp_line.media.common import All_Resources
from spins_halp_line.media.common import (
    End_A, End_B, End_C, End_D, End_E,
    End_F, End_G, End_H, End_I, End_J
)
from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.player import Player
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from spins_halp_line.stories.story_objects import (
    Script,
    Snapshot,
    confused_response
)
from spins_halp_line.stories.tele_constants import (
    Key_path, Path_Clavae, Path_Karen
)
from spins_halp_line.stories.tele_story_objects import TelePlayer
from spins_halp_line.stories.tele_story_objects import TeleShard
from spins_halp_line.stories.telemarketopia import telemarketopia
from spins_halp_line.tasks import Trio_Task_Task_Object_Runner, GitUpdate, Task, add_task
from spins_halp_line.twil import t_resp, TwilRequest
from spins_halp_line.util import do_monkey_patches, get_logger

# todo: Notes on overall server structure:
# todo:
# todo: After getting this (mostly) working, I think there are a few structural
# todo: changes I'd make to the architecture.
# todo:
# todo: First, I'd have the tasking system more thoroughly integrated with the
# todo: rest of the structure of the server. Each task would be associated with
# todo: a script / room / action / player / etc. They would get recorded in some
# todo: ledger somewhere and could be audited. In general, storing logs in some
# todo: structure that could be retrieved later seems like a good idea as well.
# todo:
# todo: I also think that, in hindsight, Rooms don't make much sense. We rarely
# todo: have the room do anything complex and they actually complicate returning
# todo: multiple audio files because the room creates and returns the twilio response.
# todo: It would make more sense to keep the idea of 'Rooms' as a organizing principle,
# todo: but make all their functions a function of the Scene. Scenes would also just
# todo: have a sparse list of functions to call when a particular room is entered / left
# todo: / whatever. That would also simplify the state management for when a player
# todo: goes through a set of rooms (a 'tunnel'). The current system was designed
# todo: without background on how twilio works, but because we need to return an
# todo: arbitrary number of sound files / say commands before we reach the next 'gather,'
# todo: it's actually somewhat complex to decide how many 'Rooms' to go through for
# todo: a particular request.
# todo:
# todo: So I think a better model is to have a Script, which manages *all* of the
# todo: shared state and which Scene is associated with what phone number, and then
# todo: the various Scene objects, which change things for the player. For the
# todo: class-driven version of this you would inherit from Script and Scene for a
# todo: particular adventure. For a data-driven model, you'd pass a bunch of JSON
# todo: (or whatever) to a subclass with faculties to interpret it.
# todo:
# todo: Generally, I think this is actually just a story graph navigator and that
# todo: players are choosing which nodes to visit based on their states. I think
# todo: there's a lot of potential for other 'views' into the story graph where
# todo: players experience it as a MUD or a choose your own adventure book or
# todo: whatever.

Script.add_script(telemarketopia)

do_monkey_patches()

app = QuartTrio(__name__)
config = Config.from_toml("./hypercorn.toml")

commit_message = subprocess.run(['git', 'log', '-1', '--pretty=%B'], capture_output=True)
commit_message = commit_message.stdout.decode()

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
        <p>{commit_message}</p>
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
        event_text = await read_channel.receive()
        await websocket.send(event_text)


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
        if await script.request_made_by_active_player(req):
            response = await script.play(req)
            # await player.save()
            break

    # start a new game
    if not response:
        for script in Script.Active_Scripts:
            if await script.call_could_start_game(req):
                response = await script.play(req)
                # await player.save()
                break

    if not response:
        response = confused_response()

    # save any state changes we recorded
    # await req.player.save()

    return t_resp(response)


@app.route("/tipline/sms", methods=['GET', 'POST'])
async def handle_text():
    req = TwilRequest(request)
    await req.load()

    for script in Script.Active_Scripts:
        if await script.request_made_by_active_player(req):
            await script.process_text(req)
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
    return await get_ending_response([End_C, End_B])


@app.route("/climax/1/2", methods=['GET', 'POST'])
async def ending_12():
    return await get_ending_response([End_F, End_E, End_B])


@app.route("/climax/1/3", methods=['GET', 'POST'])
async def ending_13():
    return await get_ending_response([End_A, End_E, End_F])


@app.route("/climax/2/1", methods=['GET', 'POST'])
async def ending_21():
    return await get_ending_response([End_C, End_D])


@app.route("/climax/2/2", methods=['GET', 'POST'])
async def ending_22():
    return await get_ending_response([End_F, End_D, End_G])


@app.route("/climax/2/3", methods=['GET', 'POST'])
async def ending_23():
    return await get_ending_response([End_A, End_F, End_E, End_D])


@app.route("/climax/3/1", methods=['GET', 'POST'])
async def ending_31():
    return await get_ending_response([End_C, End_A])


@app.route("/climax/3/2", methods=['GET', 'POST'])
async def ending_32():
    return await get_ending_response([End_A, End_E, End_F])


@app.route("/climax/3/3", methods=['GET', 'POST'])
async def ending_33():
    return await get_ending_response([End_H])


# final climax responses
@app.route("/finalclimax/right", methods=['GET', 'POST'])
async def final_final_right():
    return await get_ending_response([End_J])


@app.route("/finalclimax/wrong", methods=['GET', 'POST'])
async def final_final_wrong():
    return await get_ending_response([End_I])


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

    clavae = TelePlayer(num1)
    karen = TelePlayer(num2)

    await clavae.load()
    await karen.load()

    await telemarketopia.start_game_for_player(clavae, {Key_path: Path_Clavae})
    await telemarketopia.start_game_for_player(karen, {Key_path: Path_Karen})

    await clavae.save()
    await karen.save()
    # update shared state
    shard: TeleShard = telemarketopia.state_manager.shard
    # If this is debugging an already existing conference, they'll
    if num1 not in shard.clavae_waiting_for_conf or num2 not in shard.karen_waiting_for_conf:
        shard.append('clavae_waiting_for_conf', num1)
        shard.append('karen_waiting_for_conf', num2)

    # kick off actual conference
    await telemarketopia.integrate_shard(shard)

    return ""


@app.route("/debug/start", methods=["POST"])
async def debug_start_game():
    req = TwilRequest(request)
    await req.load()

    # normalize format
    num: str = PhoneNumber(req.data['number']).e164

    info = {}
    if 'path' in req.data:
        info[Key_path] = req.data['path']

    if 'state' in req.data:
        info['state'] = req.data['state']

    p = TelePlayer(num)

    await p.load()

    await telemarketopia.start_game_for_player(p, info)

    await p.save()
    # update shared state

    return ""


@app.route("/debug/trigger-climax", methods=["POST"])
async def trigger_climax():
    req = TwilRequest(request)
    await req.load()

    num = PhoneNumber(req.data['number'])
    c_choice = str(req.data.get('c_choice', 1))
    k_choice = str(req.data.get('k_choice', 1))

    await make_call(
        num,
        Global_Number_Library.random(),
        '/'.join([Root_Url, 'climax', c_choice, k_choice])
    )

    return ""


@app.route("/debug/reduce", methods=["POST", "GET"])
async def trigger_reduce():
    await telemarketopia.integrate_shard(telemarketopia.state_manager.shard)

    return ""


@app.route("/debug/nuke", methods=["POST"])
async def reset_state():
    # todo: make this work for all scripts
    req = TwilRequest(request)
    await req.load()

    # normalize format
    code = req.data['code']
    result = {
        'games': {},
        'players': {}
    }
    result['games'][telemarketopia.name] = telemarketopia.state_manager.dict
    if code == '2501':
        await telemarketopia.reset()

    for p in await Player.get_all_players():
        await p.load()
        result['players'][p.number.e164] = p.data
        if code == '2501':
            await p.reset(p)

    return jsonify(result)


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
        await snap.restore(telemarketopia)

    return ""


@app.route("/debug/snapshot", methods=['POST'])
async def load_snapshot_from_body():
    req = TwilRequest(request)
    await req.load()
    snap = Snapshot.from_json(req.data.get('snapshot'))
    if snap:
        await snap.restore(telemarketopia)

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
    _re_raise_exceptions = True  # crash proper when we crash

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
