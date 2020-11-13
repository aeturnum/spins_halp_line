import subprocess
import logging
from typing import Union, Optional, IO

import hypercorn.logging as hyplog
from hypercorn.config import Config
from hypercorn.trio import serve
from quart_trio import QuartTrio
from quart import request, Response, url_for
import trio_asyncio
import trio
from functools import partial

from twilio.twiml.voice_response import VoiceResponse, Gather

from spins_halp_line.tasks import work_queue, GitUpdate


# modified version of create logger
def our_create_logger(
    name: str,
    target: Union[logging.Logger, str, None],
    level: Optional[str],
    sys_default: IO,
    *,
    propagate: bool = True,
) -> Optional[logging.Logger]:
    if isinstance(target, logging.Logger):
        return target

    if target:
        logger = logging.getLogger(name)
        logger.handlers = [
            logging.StreamHandler(sys_default) if target == "-" else logging.FileHandler(target)
        ]
        logger.propagate = propagate
        formatter = logging.Formatter(
            "[%(levelname)s] %(message)s",
            "",
        )
        logger.handlers[0].setFormatter(formatter)
        if level is not None:
            logger.setLevel(logging.getLevelName(level.upper()))
        return logger
    else:
        return None

# who needs config options with python
hyplog._create_logger = our_create_logger


app = QuartTrio(__name__)
config = Config.from_toml("./hypercorn.toml")
add_task, get_task = trio.open_memory_channel(50)

message = subprocess.run(['git', 'log', '-1', '--pretty=%B'], capture_output=True)
message = message.stdout.decode()

async def pretty_print_request(r, label = ""):
    s = []
    content_type = r.headers.get("Content-Type", None)

    if label:
        s.append(f"{label}:")
    s.append(f"{r.method} {r.url}")
    s.append("Headers:")
    for header, value in r.headers.items():
        s.append(f'  {header}: {value}')

    if r.args:
        s.append("Args:")
        for arg, value in r.args.items():
            s.append(f'{arg}: {value}')

    if content_type:
        if 'x-www-form-urlencoded' in content_type:
            form = await r.form
            s.append("Form:")
            for arg, value in form.items():
                s.append(f'{arg}: {value}')
        if 'json' in content_type:
            json = await r.get_json()
            s.append("JSON:")
            for arg, value in json.items():
                s.append(f'{arg}: {value}')

    print("\n".join(s))

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
    await pretty_print_request(request, "/tipline/start")
    response = VoiceResponse()
    with response.gather( num_digits=1, action=url_for('game_tips'), method="POST") as g:
        g.say(message="This is doctor spins tip line!" +
                      "Please press 1 to do one thing" +
                      "Or press 2 to do another!.", loop=3)
    return twil(response)

@app.route('/tipline/tip', methods=['POST'])
async def game_tips():
    await pretty_print_request(request, "/tipline/tip")
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
        await add_task.send(GitUpdate())
    return ""


#   _____                            ____        _ _            _
#  / ____|                          |  _ \      | | |          | |
# | (___   ___ _ ____   _____ _ __  | |_) | ___ | | | ___   ___| | _____
#  \___ \ / _ \ '__\ \ / / _ \ '__| |  _ < / _ \| | |/ _ \ / __| |/ / __|
#  ____) |  __/ |   \ V /  __/ |    | |_) | (_) | | | (_) | (__|   <\__ \
# |_____/ \___|_|    \_/ \___|_|    |____/ \___/|_|_|\___/ \___|_|\_\___/

async def async_layer():
    async with trio_asyncio.open_loop() as loop:
        async with trio.open_nursery() as nurse:
            # start our own
            nurse.start_soon(partial(serve, app, config))
            nurse.start_soon(work_queue, get_task)
            # nurse.start_soon(QuartTrio.run_task, *[app, "127.0.0.1", 5000, True])

trio_asyncio.run(async_layer)

