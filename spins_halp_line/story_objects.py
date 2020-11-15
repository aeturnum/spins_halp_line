from typing import List, Optional
from dataclasses import dataclass

from twilio.twiml.voice_response import VoiceResponse

from spins_halp_line.util import Logger
from spins_halp_line.twil import TwilRequest
from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)
from spins_halp_line.player import SceneInfo, ScriptInfo


# This file contains the three-tiered structure for managing phone-based experiences
# That structure is as follows:
# *Rooms*
# Rooms are units of functionality that return a single twilio XML document. They respond
# to a single REST request. They can handle an entire phone call, or they can handle a single
# element of a multi-request interaction like a phone tree.
# *Scenes*
# Scenes contain one or more rooms. With the simplest structure, a scene contains a room and the
# two are interchangible. Otherwise, Scenes contain helpers to select the appropriate room (i.e.
# they take a dictionary to specify internal structure.
# Scenes also have names and will manage state associated with each player. A player (a phone#) will
# have a scenes key that contains any information about any scene. Thus scene names must be unique for
# a given script.
# *Script*
# The script determines how the scenes are connected and what scenes a player has access to at any given
# time. They will ensure that players don't get knocked off course by calling the wrong number.


#           _         _                  _     ____                    _____ _
#     /\   | |       | |                | |   |  _ \                  / ____| |
#    /  \  | |__  ___| |_ _ __ __ _  ___| |_  | |_) | __ _ ___  ___  | |    | | __ _ ___ ___  ___  ___
#   / /\ \ | '_ \/ __| __| '__/ _` |/ __| __| |  _ < / _` / __|/ _ \ | |    | |/ _` / __/ __|/ _ \/ __|
#  / ____ \| |_) \__ \ |_| | | (_| | (__| |_  | |_) | (_| \__ \  __/ | |____| | (_| \__ \__ \  __/\__ \
# /_/    \_\_.__/|___/\__|_|  \__,_|\___|\__| |____/ \__,_|___/\___|  \_____|_|\__,_|___/___/\___||___/
#


class Room(Logger):
    Name = "Base room"

    async def action(self, request: TwilRequest, script_data: dict, scene_data: dict):
        raise ValueError("Cannot use base class of Room")

    def __str__(self):
        return f'Room[{self.Name}]'


class Scene(Logger):
    Name = "Base scene"
    Rooms: List[Room] = []

    # todo: add code to select rooms based on request qualities (i.e. digits)

    # def __init__(self):
    # super(Scene, self).__init__()
    #     # because Name and Rooms are class variables this is basically static
    #     self._room_index = {}
    #     for r in self.Rooms:
    #         name = r.Name
    #         if name in self._room_index:
    #             raise ValueError(f'Duplicate room name "{name}" in {self.Name}!')
    #
    #         self._room_index[name] = r

    def done(self, script_state: ScriptInfo):
        scene_state = script_state.scene(self.Name)

        return self._next_room(scene_state) is None

    async def play(self, request: TwilRequest, script_state: ScriptInfo):
        self.d(f'play({request}, {script_state})')
        scene_state = script_state.scene(self.Name)
        self.d(f'play({request}, {script_state}): {scene_state}')

        room = self._next_room(scene_state)

        twilio_action = await room.action(request, script_state.data, scene_state.data)

        scene_state.rooms_visited.append(room.Name)
        scene_state.prev_room = self.Rooms.index(room)

        return twilio_action

    def _next_room(self, state: SceneInfo):
        # Here we need to either get rooms sequentially or we need to respect structure
        # We could do something like this:
        # [a, b, c] = a -> b -> c
        # {a : {1: b, 2: c}} -> a - player chooses 2 > b

        # base case
        room = None
        if state.prev_room is None:
            room = self.Rooms[0]
        elif state.prev_room + 1 < len(self.Rooms):
            room = self.Rooms[state.prev_room + 1]

        self.d(f'_next_room({state}) -> {room}')
        return room

    def __str__(self):
        return f'Scene[{self.Name}]'


@dataclass
class SceneSet:
    scenes: List[Scene]
    next_state: str


class Script(Logger):
    # todo: maybe switch to static approach like with scenes
    # We should also name scripts so we can have multiple scenarios we're testing and comparing.
    # That way we can save progress on a per-script basis
    Active_Scripts = []

    def __init__(self, name, structure: dict):
        super(Script, self).__init__()
        self.name = name
        # structure format:
        # Current_State: {
        #    phone# : SceneSet
        # }
        self.structure = structure

    # Methods for dealing with making the basic structure

    @classmethod
    def add_script(cls, script):
        cls.Active_Scripts.append(script)

    # methods where work happens

    # return true if player is going t
    async def player_playing(self, request: TwilRequest):
        self.d(f"Checking {request}...")
        await request.load()  # load player
        script_info: ScriptInfo = request.player.script(self.name)
        scene_set = self._get_scene_set(script_info, request.num_called)
        playing = self._find_scene(script_info, scene_set) is not None
        self.d(f"{request} is playing?: {playing}")
        return playing

    async def player_eligable(self, request: TwilRequest):
        await request.load()  # load player
        return True

    async def play(self, request: TwilRequest):
        self.d(f'play({request})')
        script_info: ScriptInfo = request.player.script(self.name)
        self.d(f'play({request}) - {script_info}')
        scene_set = self._get_scene_set(script_info, request.num_called)

        scene = self._find_scene(script_info, scene_set)

        result = await scene.play(request, script_info)

        if scene.done(script_info):
            self.d(f'play({request}) - scene is done')
            script_info.scene_path.append(scene.Name)
            next_scene = self._find_scene(script_info, scene_set)
            if next_scene is None:
                self.d(f'play({request}) - scene set is done!')
                # scene set is done, need to switch state
                script_info.state = scene_set.next_state

        return result

    def _find_scene(self, script_info: ScriptInfo, scene_set: SceneSet):
        our_scene = None
        for scene in scene_set.scenes:
            if not scene.done(script_info):
                our_scene = scene
        self.d(f'_find_scene(script_info, {scene_set}) -> {our_scene}')
        return our_scene

    def _get_scene_set(self, info: ScriptInfo, number_called: str) -> Optional[SceneSet]:
        self.d(f'_get_scene_set(info, {number_called})')
        if info.state == Script_End_State:
            self.d(f'_get_scene_set(info, {number_called}): Treating end state as start state for restart')
            # allow players to restart
            info.state = Script_New_State

        current_structure = self.structure.get(info.state)

        if number_called in current_structure:
            self.d(f'_get_scene_set(info, {number_called}): Specific number matched')
            return current_structure.get(number_called)
        elif Script_Any_Number in current_structure:
            self.d(f'_get_scene_set(info, {number_called}): Matching wildcard')
            return current_structure.get(Script_Any_Number)

        return None

    def __str__(self):
        return f'Script[{self.name}]'

#  _____
# |  __ \
# | |__) |___   ___  _ __ ___  ___
# |  _  // _ \ / _ \| '_ ` _ \/ __|
# | | \ \ (_) | (_) | | | | | \__ \
# |_|  \_\___/ \___/|_| |_| |_|___/
#


class TestIntro(Room):
    Name = "Tip List"

    async def action(self, request: TwilRequest, script_state: ScriptInfo, scene_state: SceneInfo):
        self.d("")
        response = VoiceResponse()
        with response.gather(num_digits=1, method="POST") as g:
            g.say(message="This is doctor spins tip line!" +
                          "Please press 1 to do one thing" +
                          "Or press 2 to do another!.", loop=3)

        return response


class TestTip(Room):
    Name = "Tip Read Back"

    async def action(self, request: TwilRequest, script_state: ScriptInfo, scene_state: SceneInfo):
        self.d("")
        response = VoiceResponse()
        response.say(f"You chose option {request.digits}")
        return response


#   _____
#  / ____|
# | (___   ___ ___ _ __   ___  ___
#  \___ \ / __/ _ \ '_ \ / _ \/ __|
#  ____) | (_|  __/ | | |  __/\__ \
# |_____/ \___\___|_| |_|\___||___/

class TestScene(Scene):
    Name = "Test scene"
    Rooms = [TestIntro(), TestTip()]


#   _____           _       _
#  / ____|         (_)     | |
# | (___   ___ _ __ _ _ __ | |_ ___
#  \___ \ / __| '__| | '_ \| __/ __|
#  ____) | (__| |  | | |_) | |_\__ \
# |_____/ \___|_|  |_| .__/ \__|___/
#                    | |
#                    |_|

testing = Script(
    "testing",
    {
        Script_New_State: {
            Script_Any_Number: SceneSet([TestScene()], Script_End_State)
        }
    }
)

Script.add_script(testing)

#  ______ _              _   _____
# |  ____(_)            | | |  __ \
# | |__   ___  _____  __| | | |__) |___  ___ _ __   ___  _ __  ___  ___  ___
# |  __| | \ \/ / _ \/ _` | |  _  // _ \/ __| '_ \ / _ \| '_ \/ __|/ _ \/ __|
# | |    | |>  <  __/ (_| | | | \ \  __/\__ \ |_) | (_) | | | \__ \  __/\__ \
# |_|    |_/_/\_\___|\__,_| |_|  \_\___||___/ .__/ \___/|_| |_|___/\___||___/
#                                           | |
#                                           |_|


def confused_response():
    response = VoiceResponse()
    response.say("We're not quite sure where you are, sorry!")
    return response
