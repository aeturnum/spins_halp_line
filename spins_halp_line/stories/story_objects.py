from typing import List, Optional, Dict, Union, Tuple, Callable, Any
from dataclasses import dataclass, field, asdict
import json
import traceback

from twilio.twiml.voice_response import VoiceResponse
import trio

from spins_halp_line.util import Logger, Snapshot, LockManager
from spins_halp_line.resources.numbers import PhoneNumber
from spins_halp_line.twil import TwilRequest
from spins_halp_line.player import Player
from spins_halp_line.tasks import Task, add_task
from spins_halp_line.resources.redis import new_redis
from spins_halp_line.constants import (
    Script_Any_Number,
    Script_Ignore_Change
)
from spins_halp_line.player import SceneInfo, ScriptInfo, RoomInfo
from spins_halp_line.events import send_event
from spins_halp_line.errors import StoryNavigationException
from spins_halp_line.actions.errors import error_sms


@dataclass
class Change:
    # (out of date) format
    # {
    #   'to': <key of the state that is getting the addition>
    #   'value': <for lists, this is a new list to extend the old one with; for dicts it is a single value>
    #   'key': <if changing a dict this is the key>
    # }
    From: str = None
    To: str = None
    Value: Any = None
    # todo: add dict support
    # Key: str = None
    At_Front: bool = False

    def _remove(self, field: Union[List, dict], val):
        if isinstance(field, list):
            for v in val:
                field.remove(v)
        else:
            raise ValueError(f"Cannot remove value from non-list: {type(field)}")

        return field

    def apply(self, target: Any):

        to = getattr(target, self.To, None)
        frm = None
        if self.From:
            frm = getattr(target, self.From, None)
            if frm is None:
                print(f"Could not apply {self} - {self.From} does not exist")
                return

        if to is None:
            print(f"Could not apply {self} - {self.To} does not exist")
            return

        if frm:
            frm = self._remove(frm, self.Value)
            setattr(target, self.From, frm)

        if isinstance(to, list):
            # todo: figure out if we want this
            for v in self.Value:
                if v not in to:
                    to.append(v)
        else:
            print(f'Target value is {type(to)}, only lists supported')
            return
        # elif isinstance(to, dict):
        #     to[Change.Key] = Change.Value

        setattr(target, self.To, to)

    def set_value(self, val):
        self.Value = []
        if isinstance(val, list):
            self.Value.extend(val)
        else:
            self.Value.append(val)

    def set_from(self, name, target):
        print(f'Change.set_from({name}, {target})')
        frm = getattr(target, name, [])
        print(f'Change.set_from({name}, {target}) -> {frm}')
        print(f'Change.set_from({name}, {target}) -> Value:{self.Value}')
        if not all([v in frm for v in self.Value]):
            raise ValueError(f'Could not set from to {name} - value not in source {target}.{name} = {frm}')

        self.From = name

    def __repr__(self):
        return str(self)

    def __str__(self):
        s = f'Ch['
        if self.From:
            s += f'{self.From}->'
        s += f'{self.To}]'
        # if self.Key
        #     s += f'[{self.Key}]'
        s += f' = {self.Value}'

        return s

class Shard:
    def __init__(self):
        super(Shard, self).__init__()
        super(Shard, self).__setattr__('_parent', None)
        super(Shard, self).__setattr__('_changes', [])
        # self._changes: List[Change] = []
        # check setting of variables here


    def set_parent(self, parent):
        self._parent = parent

    def __setattr__(self, key, value):
        if self._parent is not None and key not in {'_parent', '_changes'}:
            raise ValueError("Not allowed to change attributes!")

        return super(Shard, self).__setattr__(key, value)

    def _check_to(self, to):
        sentinal = 'sentinal_to-value'
        val = getattr(self, to, sentinal)
        if val == sentinal:
            raise ValueError(f"It seems like {self} does not contain {to}")

    def append(self, to, value, to_front=False):
        self._check_to(to)
        change = Change(To=to, At_Front=to_front)
        change.set_value(value)

        # if isinstance(change_target, dict):
        #     change.Key = key
        #     change.Value = value

        self._changes.append(change)

    def move(self, frm, to, value, to_front=False):
        self._check_to(to)
        change = Change(To=to, At_Front=to_front)
        change.set_value(value)
        change.set_from(frm, self)

        # if isinstance(change_target, dict):
        #     change.Key = key
        #     change.Value = value

        self._changes.append(change)

    async def queue_state_update(self):
        await self._parent.integrate_shard(self)

    async def integrate(self):
        # this works because python just doesn't care about circular references
        if self._changes:
            await self._parent.integrate(self._changes)
            self._changes = []


class RoomContext(dict):

    def __init__(self,
                 player: Player,
                 shard: Shard,
                 script_state: ScriptInfo,
                 scene_state: SceneInfo,
                 room_state: Union[RoomInfo, dict]):
        # fill with our info
        self_data = {}
        if isinstance(room_state, RoomInfo):
            self_data = room_state.data
        elif isinstance(room_state, dict):
            self_data = room_state

        super(RoomContext, self).__init__(self_data)

        self.player = player
        self.shard = shard
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
            room_state: Union[RoomInfo, dict],
            spoil_state: bool = True):
        # In theory we should not need to pass the shard back here
        # because its structure prevents any objects being replaced
        # and so all of its references will be appropriate.
        # We need to pass everything else back because the room could do something like:
        # context.script = {}
        # which would be a new dictionary; the old script_state.data would not be replaced
        # unless we did it here

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

        if isinstance(room_state, RoomInfo):
            room_state.data.update(self)
        elif isinstance(room_state, dict):
            room_state.update(self)

        return script_state, scene_state, room_state

    def end_scene(self):
        self._ended = True

    def __str__(self):
        fresh = "_"
        if self.state_is_new:
            fresh = "F"
        return f"RoomCtx[{self.state}|{fresh}]"

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


# todo: setup a system for getting a twilio callback and ending sessions cleanly.
# todo: this probably involves a mode where we replay the last room with no number
# todo: entered and also gracefully end calls.


#           _         _                  _     ____                    _____ _
#     /\   | |       | |                | |   |  _ \                  / ____| |
#    /  \  | |__  ___| |_ _ __ __ _  ___| |_  | |_) | __ _ ___  ___  | |    | | __ _ ___ ___  ___  ___
#   / /\ \ | '_ \/ __| __| '__/ _` |/ __| __| |  _ < / _` / __|/ _ \ | |    | |/ _` / __/ __|/ _ \/ __|
#  / ____ \| |_) \__ \ |_| | | (_| | (__| |_  | |_) | (_| \__ \  __/ | |____| | (_| \__ \__ \  __/\__ \
# /_/    \_\_.__/|___/\__|_|  \__,_|\___|\__| |____/ \__,_|___/\___|  \_____|_|\__,_|___/___/\___||___/
#

class TextHandler(Logger):
    Name = "Base Text Handler"

    # Must add choice to room state outside of this
    async def new_text(self, text_request: TwilRequest, shard: Shard, script_info: ScriptInfo):
        return script_info

    # load any resources that we need
    async def load(self):
        pass

    def __eq__(self, other):
        if not isinstance(other, TextHandler):
            return False

        return other.Name == self.Name

    def __hash__(self):
        # todo: WARNING - this makes all copies of a room equivalent to another
        # todo: This should be *fine* for now, but it means that we MUST only use
        # todo: rooms in the _room_index of a scene, and never use a room in the
        # todo: choices array. Otherwise we will lose any state in the rooms.
        return self.Name.__hash__()

    def __str__(self):
        return f'TextHandler[{self.Name}]'

    def __repr__(self):
        return str(self)


class Room(Logger):
    Name = "Base room"
    # REMEMBER
    # We cannot store things in the room object because the room object is *shared between players*
    # so one player would change the other room and the other would see it.
    # Everything has to be done by passing around per-player state

    # Must add choice to room state outside of this
    async def new_player_choice(self, choice: str, context: RoomContext):
        pass

    # load any resources that we need
    async def load(self):
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
        self._index_rooms()

    def _index_rooms(self):
        self._room_index: Dict[str, Room] = {}
        for r in self.Start:
            self._add_to_index(r)
        for r, choice_info in self.Choices.items():
            self._add_to_index(r)

            for _, room_choice in choice_info.items():
                self._add_to_index(room_choice)

    async def load(self):
        for room in self._room_index.values():
            print(f'loading {room}')
            await room.load()

    def _add_to_index(self, room_list: Union[Room, List[Room]]):
        if not isinstance(room_list, list):
            room_list = [room_list]

        for room in room_list:
            if room.Name not in self._room_index:
                print(f"Adding room to index: {room}")
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
                    done = self.choices_for_room(prev_room) is None
                    self.d(f"done? {done}")
            else:
                self.d(f"not done - have rooms in queue {done}")
        else:
            self.d(f"not done - we have not run the scene yet! {done}")

        return done

    def choices_for_room(self, room):
        choices = self.Choices.get(room, None)
        self.d(f"Choices_for_room({room}) -> {choices}")
        return choices

    async def play(self, shard: Shard, request: TwilRequest, script_state: ScriptInfo):
        self.d(f'play({request}, {script_state})')
        scene_state = self._get_state(script_state)
        self.d(f'play({request}, {script_state}): {scene_state}')
        self.d(f"play({request}): state.rooms_visited: {scene_state.rooms_visited}")

        # tell the room what happened last time
        script_state, scene_state = await self._notify_last_room_of_choice(
            request,
            shard,
            script_state,
            scene_state
        )

        # handles either finishing the tunnel we are in or
        # picking a room based on choices.
        room_queue = self._get_queue(request, script_state, scene_state)
        self.d(f"room queue: {room_queue}")

        # remove first member of the room_queue and get the room it references

        try:
            room = room_queue[0]
            room = self._name_to_room(room)
            # if that worked...
            room_queue.pop(0)
        except IndexError:
            self.e(f"Tried to pop from empty room queue! Replying last room")
            room = self._name_to_room(scene_state.prev_room)

        # except Exception as e:
        #     raise StoryNavigationException("Could not get next room", e)

        # get room state
        room_state = scene_state.room_state(room.Name)
        self.d(f"room state: {room_state}")
        # make whole context object
        context = RoomContext(request.player, shard, script_state, scene_state, room_state)

        await send_event(f"{request.player} entering {room}!")
        try:
            twilio_action = await room.action(context)
        except Exception as e:
            raise StoryNavigationException("Failed while trying to take room action", e)

        # backup
        script_state_snap = Snapshot(script_state)
        try:
            # post room updates
            # I am now paranoid about state not getting written and am done fucking around
            script_state, scene_state, room_state = context._pass_back_changes(
                script_state,
                scene_state,
                room_state,
                spoil_state=True  # the room state stops being fresh now
            )

            scene_state.rooms_visited.append(room.Name)
            self.d(f"play({request}): state.rooms_visited: {scene_state.rooms_visited}")
            # update room queue
            scene_state.room_queue = room_queue

            # more paranoia about failures to write
            scene_state.room_states[room.Name] = room_state
            script_state.scene_states[self.Name] = scene_state
        except Exception as e:
            script_state_snap.restore()  # undo any changes, though we generally won't save anything
            raise StoryNavigationException("Failed while trying to save state", e)

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
        return self._room_index[room_name]

    async def _notify_last_room_of_choice(
            self,
            request: TwilRequest,
            shard: Shard,
            script_state: ScriptInfo,
            our_info: SceneInfo) -> Tuple[ScriptInfo, SceneInfo]:
        # check that there's a previous room
        if our_info.prev_room and request.digits:
            player_choice = str(request.digits)
            prev_room = self._name_to_room(our_info.prev_room)
            room_state = our_info.room_state(prev_room.Name)

            # room)state.choice will NOT have the new choice in it
            context = RoomContext(request.player, shard, script_state, our_info, room_state)
            await prev_room.new_player_choice(player_choice, context)

            script_state, our_info, room_state = context._pass_back_changes(script_state, our_info, room_state)
            room_state.choices.append(player_choice)
            # more paranoia
            our_info.room_states[prev_room.Name] = room_state

        return script_state, our_info

    def _get_queue(self, request: TwilRequest, script_state: ScriptInfo, our_info: SceneInfo) -> List[str]:
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
        if self.choices_for_room(prev_room) is not None:
            number = str(request.digits)
            queue = self._get_choice_for_request(number, prev_room, script_state)

        # todo: add a default option that tells the user we didn't understand their choice and
        # todo: replays the previous room
        return self._item_to_room_name_list(queue)

    def _get_choice_for_request(self, number: str, room: Room, script_state: ScriptInfo):
        room_choices = self.Choices.get(room)  # dictionary of choice to room
        self.d(f"_get_queue() choices: {room_choices}")
        # todo: standardize digits as a string?
        queue = None
        if number in room_choices:
            queue = room_choices[number]
            self.d(f"Choice #{number}: {queue}")
        elif '*' in room_choices:  # default
            queue = room_choices['*']
            self.d(f"Choice *: {queue}")

        return queue

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


# todo: Probably, eventually, we want to re-write this whole system to be a single immutable data structure
# todo: that we pass around everywhere and is updated by changes in other threads. We'd also want to add
# todo: code to enforce players only existing in a single 'location' and a single 'stage'.
# todo:
# todo: We'd probably want to do this using a layer of classes. An item being tracked by the state will be
# todo: called a Node in the text below (in our current system a Node would be a phone number string).
# todo:
# todo: The general class has 'Categories' and 'Stages':
# todo: 	- A Category has a set of valid values. Each Node is associated with one of the valid values.
# todo: 	  Each Node *must* be in each category exactly once.
# todo: 	- A Stage is a 'place' for a Node to be. There can be any number of Stages, but each Node can
# todo: 	  be in only one Stage at a time.
# todo:
# todo: Then we'd have a CategorizedStageState where Stages can have Categories - this would represent the
# todo: path'd structure we have.
# todo: 	- So Stages and Categories would be defined as before
# todo: 	- But some (not all) Categories would apply to Nodes and Stages
# todo: 	- So the 'Path' Category would apply to stages and we'd implicitly have duplicate stages for
# todo: 	  each value of the 'Path' Category

# script
#   \- state <-save on request / loaded on load-> redis
#   	\- shard <-things added-> code
# 	    |	\- integrate() -> send back to state if there are changes
#    	\- reducer -> async task, run on end of request, that can remove items, state is locked while it runs

@dataclass
class ScriptState:
    pass


class StateShard(ScriptState, Shard):
    def __init__(self, *args, **kwargs):
        Shard.__init__(self)
        ScriptState.__init__(self, *args, **kwargs)


class ScriptStateManager(Logger):

    def __init__(self):
        super(ScriptStateManager, self).__init__()
        self._key = None
        self._state = self._make_new_state()
        self._version = 0
        self._generation = 0
        # self._state.update(initial_state)
        self._lock = trio.Lock()

    def _make_new_state(self, base: dict = None) -> ScriptState:
        if base is None:
            base = {}
        return ScriptState()

    def _make_shard(self) -> StateShard:
        d = self._state_dict
        d.pop('version', None)  # remove version
        d.pop('generation', None)  # remove version
        ss = StateShard(**d)
        ss.set_parent(self)
        return ss

    def set_key(self, key):
        self._key = key

    # This is a callback used by shards to 'ship' their changes back to the script state
    async def integrate(self, changes: List[Change]):
        self.d(f'Integrating: {changes}')
        if changes == []:
            return

        async with LockManager(self._lock):
            await self.sync_redis(True)
            for change in changes:
                change.apply(self._state)

            await self.save_to_redis(True)

    async def integrate_shard(self, shard: Shard):
        await add_task.send(AfterRequestActions(shard, self))

    # primaraly used for debugging to overwrite old versions
    async def set_new_generation(self):
        async with LockManager(self._lock):
            # save whatever our state is
            our_state = self._state_dict
            # get latest version, then lock so our generation is up to date
            await self.sync_redis(True)
            # make sure we will, at worst, collide with another parallel process
            latest_generation = self._generation
            self._state = self._make_new_state(our_state)
            # this version will override any other
            self._generation = latest_generation + 1

            # save this version to redis
            await self.save_to_redis(True)

    async def reset(self):
        self._state = self._make_new_state(None)

    @property
    def version(self):
        return self._version

    @property
    def shard(self):
        return self._make_shard()

    @property
    def _state_dict(self) -> dict:
        d = asdict(self._state)
        d['version'] = self._version
        d['generation'] = self._generation
        return d

    # This function is what should be overridden in child classes.
    # Then the child class should be passed into the script when you construct it.
    async def do_reduce(self, state: ScriptState, shard: StateShard):
        return state

    async def on_startup(self):
        pass

    async def player_added(self, player: Player, script_info: ScriptInfo):
        pass

    # This is used to check if our version is out of date
    async def sync_redis(self, locked=False):
        db = new_redis()
        async with LockManager(self._lock, already_locked=locked):
            db_version = await db.get(self._key).autodecode
            if db_version:
                # check if either version or generation are newer
                if db_version['version'] > self.version or db_version['generation'] > self._generation:
                    self._state = self._make_new_state(db_version)

    # This calls the static do_reduce that will make any changes to the state in a
    # way that's safe and save the results into redis.
    async def reduce(self):
        # sync with DB
        async with LockManager(self._lock):
            await self.sync_redis(True)
            self.d('Starting do_reduce_cycle')
            self._state = await self.do_reduce(self._state, self.shard)

            await self.save_to_redis(True)

    # save the state to redis, called frequently
    async def save_to_redis(self, locked=False):
        db = new_redis()
        async with LockManager(self._lock, already_locked=locked):
            db_data = await db.get(self._key).autodecode
            if isinstance(db_data, dict):
                self.d(f'Save_to_redis: state_dict: {self._state_dict}')
                self.d(f'Save_to_redis:    db_dict: {db_data}')
                self.d(f'Save_to_redis: state_dict == db_data ? {self._state_dict == db_data}')
                if self._state_dict == db_data:
                    self.d(f'save_to_redis: no changes from version in database')
                    # there are no changes to save, no need to increase the verson
                    return
            self._version += 1
            payload = json.dumps(self._state_dict)
            self.d(f'save_to_redis: saving new version to redis: {payload}')
            await db.set(self._key, payload)

    # load from redis - called once
    async def load_from_redis(self):
        db = new_redis()
        async with LockManager(self._lock):
            db_data = await db.get(self._key)
            if db_data:
                version = -1
                generation = -1
                try:
                    state_data = json.loads(db_data)
                    # definately throw an exception here if these keys don't exist
                    version = state_data['version']
                    generation = state_data['generation']
                    del state_data['version']
                    del state_data['generation']

                    self._state = self._make_new_state(state_data)
                except Exception as e:
                    self.e(f'Encountered exception {e} while trying to load state')
                    version = self._version
                    generation = self._generation

                self._version = version
                self._generation = generation

            self.d(f'load_from_redis: loaded state dict {self._state}')

class AfterRequestActions(Task):

    # This *should* work for synchronization because each copy of the state will do its own
    # lock on the shared lock. So changes will be ordered and will block any additions to the
    # state from people going through their rooms.
    #
    # It's totally possible that these reduce loops happen out of order, but that is *fine*
    # because we don't care about order. This is about reaching threshold values to move people
    # out of waiting states.
    #
    # If we ever need this to be fair and ordered, we need to implement more strict ordering!
    #
    def __init__(self, shard: Shard, state: ScriptStateManager):
        super(AfterRequestActions, self).__init__()
        # remember that Task supports a delay arg if we need it
        self.state = state
        self.shard = shard

    async def execute(self):
        self.d(f'ARATask[{self.state}]')
        await self.shard.integrate()
        self.d(f'ARATask[{self.state}]: integration done')
        await self.state.reduce()
        self.d(f'ARATask[{self.state}]: reduction done')

class Script(Logger):
    # todo: maybe switch to static approach like with scenes
    # We should also name scripts so we can have multiple scenarios we're testing and comparing.
    # That way we can save progress on a per-script basis
    Active_Scripts: List['Script'] = []

    def __init__(self, name, structure: dict, state_object: ScriptStateManager, text_handlers: List[TextHandler] = None):
        super(Script, self).__init__()
        self.name = name
        # structure format:
        # {
        #   Current_State: {
        #        phone# : SceneSet
        #   }
        # }
        self.structure: Dict[str, Dict[str, SceneAndState]] = structure
        # got to give it the key
        state_object.set_key(self.db_key)
        self.state_manager = state_object

        if text_handlers is None:
            text_handlers = []

        self.text_handlers: List[TextHandler] = text_handlers

    # Methods for dealing with making the basic structure

    @classmethod
    def add_script(cls, script):
        cls.Active_Scripts.append(script)

    # methods for dealing with shared state

    @property
    def db_key(self):
        return f'script:{self.name}'

    def get_snapshot(self):
        return self.state_manager._state_dict

    async def reset(self):
        await self.state_manager.reset()
        await self.load_state()

    async def load_state(self):
        await self.state_manager.load_from_redis()
        await self.state_manager.on_startup()

        for choices in self.structure.values():
            for scene_set in choices.values():
                await scene_set.scene.load()

    async def integrate_shard(self, shard: Shard):
        await add_task.send(AfterRequestActions(shard, self.state_manager))

    # return true if player is going t
    async def request_from_player(self, request: TwilRequest):

        await request.load()  # load player

        return self.player_is_playing(request.player)

    def player_is_playing(self, player: Player):
        playing = False

        script_info = player.script(self.name)
        if script_info:
            playing = not script_info.is_complete

        self.d(f"Is {player} playing? -> {playing}")
        return playing

    async def call_could_start_game(self, request: TwilRequest):
        await request.load()  # load player

        # check by seeing if this a new player, with a new ScriptInfo, calling this number,
        # would get a scene
        scene_state = self._get_scene_state(ScriptInfo(), request.num_called)

        self.d(f"Can {request} start a new game? -> {scene_state is not None}")
        return scene_state is not None

    async def process_text(self, request: TwilRequest, snapshot):
        self.d(f'process_text({request})')

        try:
            if not request.is_text:
                self.w(f'Request {request} is not a text! Aborting!')
                return

            script_info: ScriptInfo = request.player.script(self.name)

            if script_info is None or script_info.is_complete:
                self.d(f'Player {request.player} is not on our script, returning!')
                return

            for handler in self.text_handlers:
                shard: StateShard = self.state_manager.shard

                script_info = await handler.new_text(request, shard, script_info)

            return
        except Exception as e:
            await self._handle_exception(request, e, snapshot)

    async def start_game_for_player(self, player):
        self.d(f'start_game_for_player({player}): Previous script completed or we need a new one.')
        script_info = ScriptInfo()  # fresh!
        player.set_script(self.name, script_info)

        await self.state_manager.player_added(player, script_info)

        return script_info

    async def play(self, request: TwilRequest, snapshot):
        self.d(f'play({request})')

        # note: some sloppy planning has resulted in confusing naming. There is the script state [for the player],
        # which we frequently call the script state, and then there is the script state [for the script] that is
        # shared and used by all players going through a script
        script_info: ScriptInfo = request.player.script(self.name)
        shard: StateShard = self.state_manager.shard

        if not self.player_is_playing(request.player):
            script_info = await self.start_game_for_player(request.player)

        self.d(f'play({request}) - {script_info}')

        scene_state = self._get_scene_state(script_info, request.num_called)

        if scene_state is None:
            self.e(f'!!!\n!!!\nCould not get Scene for: {request.num_called} by {request.player.number}')
            return error_response()

        scene = scene_state.scene

        # if something goes wrong
        result = error_response()
        try:
            result = await scene.play(shard, request, script_info)

            await self.integrate_shard(shard)
            # apply changes

            if scene.done(script_info):
                if scene_state.next_state == Script_Ignore_Change:
                    self.d(f'play({request}) - scene is done, but it;s a scene that shouldnt change the player')
                else:
                    self.d(f'play({request}) - scene is done. Script state: {script_info.state} -> {scene_state.next_state}')
                    script_info.scene_history.append(scene.Name)
                    script_info.state = scene_state.next_state

            request.player.set_script(self.name, script_info)  # should not be needed
        except Exception as e:
            await self._handle_exception(request, e, snapshot)

        return result

    async def _handle_exception(self, request, exception: Exception, snapshot):
        self.e(f'Got exception from scene.play: {exception}: {traceback.extract_tb(exception.__traceback__).format()}')
        self.e(f'Returning generic confused response.')
        # save snap to restore state
        snapshot.save()
        await error_sms(f'Player {request.player} in Scene {self} encountered an exception: {exception}')

    def _get_scene_state(self, info: ScriptInfo, number_called: PhoneNumber) -> Optional[SceneAndState]:
        self.d(f'_get_scene_set(info, {number_called.e164})')
        current_structure = self.structure.get(info.state, {})

        if number_called.e164 in current_structure:
            self.d(f'_get_scene_set(info, {number_called.e164}): Specific number matched')
            return current_structure.get(number_called.e164)
        elif Script_Any_Number in current_structure:
            self.d(f'_get_scene_set(info, {number_called.e164}): Matching wildcard')
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

def error_response():
    response = VoiceResponse()
    response.say("Oh no! Something has gone wrong! Please give us a moment to check on it!")
    return response


def confused_response():
    response = VoiceResponse()
    response.say("We're not quite sure where you are, sorry!")
    return response
