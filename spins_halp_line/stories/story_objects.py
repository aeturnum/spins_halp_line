from typing import List, Optional, Dict, Union, Tuple
from dataclasses import dataclass

from twilio.twiml.voice_response import VoiceResponse

from spins_halp_line.util import Logger
from spins_halp_line.twil import TwilRequest
from spins_halp_line.constants import (
    Script_Any_Number
)
from spins_halp_line.player import SceneInfo, ScriptInfo, RoomInfo
from spins_halp_line.events import send_event


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


class RoomContext(dict):

    def __init__(self, script_state: ScriptInfo, scene_state: SceneInfo, room_state: RoomInfo):
        # fill with our info
        super(RoomContext, self).__init__(room_state.data)

        self.script = script_state.data
        self.scene = scene_state.data
        self.choices = room_state.choices
        self._start_state = room_state.state
        self.state = room_state.state
        self.state_is_new = room_state.fresh_state
        self._ended = scene_state.ended_early

    def _pass_back_changes(
            self,
            script_state: ScriptInfo,
            scene_state: SceneInfo,
            room_state: RoomInfo,
            spoil_state: bool = True):
        script_state.data = self.script
        scene_state.data = self.scene

        # record if this room ended the scene early
        scene_state.ended_early = self._ended
        # don't copy choices back
        # also don't copy state_is_new back

        # If spoil state is false, then we don't want to change the freshness yet
        if spoil_state:
            if self._start_state == self.state:
                # no state change
                room_state.fresh_state = False
            else:
                # state change!
                room_state.state = self.state
                room_state.fresh_state = True

        for k, v in self.items():
            room_state.data[k] = v

        return script_state, scene_state, room_state

    def end_scene(self):
        self._ended = True

    def __str__(self):
        fresh = "_"
        if self.state_is_new:
            fresh = "F"
        return f"RoomCtx[{self.state}|{fresh}]"

class Room(Logger):
    Name = "Base room"
    # REMEMBER
    # We cannot store things in the room object because the room object is *shared between players*
    # so one player would change the other room and the other would see it.
    # Everything has to be done by passing around per-player state


    # Must add choice to room state outside of this
    async def new_player_choice(self, choice: str, context: RoomContext):
        pass

    async def action(self, context: RoomContext):
        raise ValueError("Cannot use base class of Room")

    def __eq__(self, other):
        if not isinstance(other, Room):
            return False

        return other.Name == self.Name

    def __hash__(self):
        # todo: WARNING - this makes all copies of a room equivalent to another
        # todo: This should be *fine* for now, but it means that we MUST only use
        # todo: rooms in the _room_index of a scene, and never use a room in the
        # todo: choices array. Otherwise we will lose any state in the rooms.
        return self.Name.__hash__()

    def __str__(self):
        return f'Room[{self.Name}]'

    def __repr__(self):
        return str(self)


class Scene(Logger):
    Name = "Base scene"
    Start: List[Room] = []
    Choices: Dict[Room, Dict[str, Union[Room, List[Room]]]] = {}

    # todo: Think about how to perform actions on rooms (i.e. if a room routes back on itself, how
    # todo: do we note that?) Right now we use the digit to route but can't tell the room.

    # todo: add a way for rooms to know about the digit that was just pressed

    def __init__(self):
        super(Scene, self).__init__()
        # because Name and Rooms are class variables this is basically static
        # We use the room index so we can use room names as indexes that we save to redis
        self._room_index: Dict[str, Room] = {}
        for r in self.Start:
            self._add_to_index(r)
        for r, choice_info in self.Choices.items():
            self._add_to_index(r)

            for _, room_choice in choice_info.items():
                self._add_to_index(room_choice)

    def _add_to_index(self, room_list: Union[Room, List[Room]]):
        if not isinstance(room_list, list):
            room_list = [room_list]

        for room in room_list:
            if room.Name not in self._room_index:
                self._room_index[room.Name] = room

    def done(self, info: ScriptInfo) -> bool:
        done = False
        self.d(f"done?")

        # todo: consider giving scenes an end state as opposed to just running out of paths
        our_info = info.scene(self.Name)
        # we are not done if our scene info doesn't even exist yet
        if our_info:
            if our_info.ended_early:
                done = True
                self.d(f"done! - ended early {done}")
            # if the room_queue has rooms we are not done and can return
            elif not our_info.room_queue:
                # since we have no rooms in queue we continue...
                prev_room = self._name_to_room(our_info.prev_room)
                if not prev_room:
                    # no queue and no previous room
                    # this should be impossible, but we'd be in an end state anyway
                    done = True
                    self.d(f"done! - no previous room {done}")
                else:
                    # we are done if there are no choices associated with this
                    done = self.Choices.get(prev_room) is None
                    self.d(f"done? choices: {self.Choices} room: {prev_room}")
                    self.d(f"done? choices: {self.Choices.get(prev_room)} {done}")
            else:
                self.d(f"not done - have rooms in queue {done}")
        else:
            self.d(f"not done - we have not run the scene yet! {done}")

        return done

    async def play(self, request: TwilRequest, script_state: ScriptInfo):
        self.d(f'play({request}, {script_state})')
        scene_state = self._get_state(script_state)
        self.d(f'play({request}, {script_state}): {scene_state}')
        self.d(f"play({request}): state.rooms_visited: {scene_state.rooms_visited}")

        # tell the room what happened last time
        script_state, scene_state = await self._notify_last_room_of_choice(request, script_state, scene_state)

        # handles either finishing the tunnel we are in or
        # picking a room based on choices.
        room_queue = self._get_queue(request, scene_state)
        self.d(f"room queue: {room_queue}")

        # remove first member of the room_queue and get the room it references
        room = self._name_to_room(room_queue.pop(0))

        # get room state
        room_state = scene_state.room_state(room.Name)
        self.d(f"room state: {room_state}")
        # make whole context object
        context = RoomContext(script_state, scene_state, room_state)

        await send_event(f"{request.player} entering {room}!")
        twilio_action = await room.action(context)

        # post room updates
        # I am now paranoid about state not getting written and am done fucking around
        script_state, scene_state, room_state = context._pass_back_changes(
            script_state,
            scene_state,
            room_state,
            spoil_state=True # the room state stops being fresh now
        )

        scene_state.rooms_visited.append(room.Name)
        self.d(f"play({request}): state.rooms_visited: {scene_state.rooms_visited}")
        # update room queue
        scene_state.room_queue = room_queue

        # more paranoia about failures to write
        scene_state.room_states[room.Name] = room_state
        script_state.scene_states[self.Name] = scene_state

        return twilio_action

    def _get_state(self, info: ScriptInfo) -> SceneInfo:
        scene_state = info.scene(self.Name)
        if not scene_state:
            self.d(f"Creating new state")
            # init state
            scene_state = info.add_scene(self.Name)
            scene_state.room_queue = self._item_to_room_name_list(self.Start)

        return scene_state

    def _name_to_room(self, room_name: str) -> Optional[Room]:
        return self._room_index.get(room_name, None)

    async def _notify_last_room_of_choice(
            self,
            request: TwilRequest,
            script_state: ScriptInfo,
            our_info: SceneInfo) -> Tuple[ScriptInfo, SceneInfo]:
        # check that there's a previous room
        if our_info.prev_room and request.digits:
            player_choice = str(request.digits)
            prev_room = self._name_to_room(our_info.prev_room)
            room_state = our_info.room_state(prev_room.Name)

            # room)state.choice will NOT have the new choice in it
            context = RoomContext(script_state, our_info, room_state)
            await prev_room.new_player_choice(player_choice, context)

            script_state, our_info, room_state = context._pass_back_changes(script_state, our_info, room_state)
            room_state.choices.append(player_choice)
            # more paranoia
            our_info.room_states[prev_room.Name] = room_state

        return script_state, our_info


    def _get_queue(self, request: TwilRequest, our_info: SceneInfo) -> List[str]:
        self.d(f"_get_queue()")
        if our_info.has_rooms_in_queue:
            self.d(f"Returning existing queue: {our_info.room_queue}")
            # already strings, from a previous call
            return our_info.room_queue

        # no existing queue
        queue = []
        # need to turn the previous room into a room object:
        prev_room = self._name_to_room(our_info.prev_room)
        self.d(f"_get_queue() previous room: {prev_room}")
        if prev_room is not None and prev_room in self.Choices:
            # check if the player has a choice to make
            number_entered = str(request.digits)
            room_choices = self.Choices.get(prev_room)  # dictionary of choice to room
            self.d(f"_get_queue() choices: {room_choices}")
            # todo: standardize digits as a string?
            if number_entered in room_choices:
                queue = room_choices[number_entered]
                self.d(f"Choice #{number_entered}: {queue}")
            elif '*' in room_choices:  # default
                queue = room_choices['*']
                self.d(f"Choice *: {queue}")

        # todo: add a default option that tells the user we didn't understand their choice and
        # todo: replays the previous room

        return self._item_to_room_name_list(queue)

    @staticmethod
    def _item_to_room_name_list(obj) -> List[str]:
        # make into one item list if not a list
        if not isinstance(obj, list):
            obj = [obj]

        # transform to strings for serializing
        return [item.Name if isinstance(item, Room) else item for item in obj]

    def __str__(self):
        return f'Scene[{self.Name}]'


# contains one scene and the state for the script after that scene
@dataclass
class SceneAndState:
    scene: Scene
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

        await request.load()  # load player
        playing = False

        script_info = request.player.script(self.name)
        if script_info:
            playing = not script_info.is_complete

        self.d(f"Is {request} playing? -> {playing}")
        return playing

    async def call_could_start_game(self, request: TwilRequest):
        await request.load()  # load player

        # check by seeing if this a new player, with a new ScriptInfo, calling this number,
        # would get a scene
        scene_state = self._get_scene_state(ScriptInfo(), request.num_called)

        self.d(f"Can {request} start a new game? -> {scene_state is not None}")
        return scene_state is not None

    async def play(self, request: TwilRequest):
        self.d(f'play({request})')

        script_info: ScriptInfo = request.player.script(self.name)
        if script_info is None or script_info.is_complete:
            self.d(f'play({request}): Previous script completed or we need a new one.')
            script_info = ScriptInfo()  # fresh!
            request.player.set_script(self.name, script_info)

        self.d(f'play({request}) - {script_info}')

        scene_state = self._get_scene_state(script_info, request.num_called)

        scene = scene_state.scene

        result = await scene.play(request, script_info)

        if scene.done(script_info):
            self.d(f'play({request}) - scene is done. Script state: {script_info.state} -> {scene_state.next_state}')
            script_info.scene_history.append(scene.Name)
            script_info.state = scene_state.next_state

        request.player.set_script(self.name, script_info)  # should not be needed

        return result

    def _get_scene_state(self, info: ScriptInfo, number_called: str) -> Optional[SceneAndState]:
        self.d(f'_get_scene_set(info, {number_called})')
        current_structure = self.structure.get(info.state, {})

        if number_called in current_structure:
            self.d(f'_get_scene_set(info, {number_called}): Specific number matched')
            return current_structure.get(number_called)
        elif Script_Any_Number in current_structure:
            self.d(f'_get_scene_set(info, {number_called}): Matching wildcard')
            return current_structure.get(Script_Any_Number)

        return None

    def __str__(self):
        return f'Script[{self.name}]'

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
