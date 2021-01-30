from dataclasses import dataclass, field, asdict, fields as datafields
import json
from typing import Any, Dict, Optional, List, Union
from copy import deepcopy

from spins_halp_line.util import Logger
from spins_halp_line.resources.redis import new_redis
from spins_halp_line.resources.numbers import PhoneNumber
from spins_halp_line.errors import DataIntegrityError
from spins_halp_line.constants import Script_New_State, Script_End_State


@dataclass
class RoomInfo:
    name: str
    state: str = ""
    fresh_state: bool = True
    choices: List[str] = field(default_factory=list)
    data: Dict[Any, Any] = field(default_factory=dict)  # the only field exposed to Rooms

    @staticmethod
    def from_dict(d: dict) -> 'RoomInfo':  # "python type system is great"
        return RoomInfo(
            name=d.get('name'),
            state=d.get('state', ""),
            fresh_state=d.get('fresh_state', True),
            choices=d.get('choices', []),
            data=d.get('data', {})
        )

    def __str__(self):
        return f'RoomInfo[{self.name}]'

@dataclass
class SceneInfo:
    name: str
    rooms_visited: List[str] = field(default_factory=list)
    room_states: Dict[str, RoomInfo] = field(default_factory=dict)
    room_queue: List[str] = field(default_factory=list)
    data: Dict[Any, Any] = field(default_factory=dict)  # the only field exposed to Rooms
    ended_early: bool = False

    def room_state(self, name: str) -> RoomInfo:
        if name not in self.room_states:
            self.room_states[name] = RoomInfo(name)

        return self.room_states[name]

    @staticmethod
    def from_dict(d: dict) -> 'SceneInfo':  # "python type system is great"
        return SceneInfo(
            name=d.get('name'),
            rooms_visited=d.get('rooms_visited', []),
            room_states={k: RoomInfo.from_dict(v) for k, v in d.get("room_states", {}).items()},
            room_queue=d.get('room_queue', []),
            data=d.get('data', {}),
            ended_early=d.get('ended_early', False)
        )

    @property
    def prev_room(self) -> Optional[str]:
        room = None
        if len(self.rooms_visited) > 0:
            # get last room on list
            room = self.rooms_visited[-1]

        return room

    @property
    def has_rooms_in_queue(self) -> bool:
        return len(self.room_queue) > 0

    def __str__(self):
        return f'SceneInfo[{self.name}]{self.prev_room}]{self.room_queue}>'


# todo: Add some event-specific dictionary for dealing with particular events
# todo: First, should make managing events easser - new event, new dict
# todo: Second, should help with housekeeping from multiple places

@dataclass
class ScriptInfo:
    state: str = Script_New_State
    scene_states: Dict[str, SceneInfo] = field(default_factory=dict)
    scene_history: List[str] = field(default_factory=list)
    text_handler_states: Dict[str, Dict[Any, Any]] = field(default_factory=list)
    data: Dict[Any, Any] = field(default_factory=dict)  # the only field exposed to Rooms

    def add_scene(self, name: str) -> SceneInfo:
        info = SceneInfo(name=name)
        self.scene_states[name] = info

        return info

    def scene(self, name: str) -> Optional[SceneInfo]:
        return self.scene_states.get(name, None)

    @property
    def is_complete(self):
        return self.state == Script_End_State

    @staticmethod
    def from_dict(d: dict):
        return ScriptInfo(
            state=d.get("state", Script_New_State),
            scene_states={k: SceneInfo.from_dict(v) for k, v in d.get("scene_states", {}).items()},
            scene_history=d.get('scene_history', []),
            text_handler_states=d.get('text_handler_states', []),
            data=d.get('data', {})
        )

    def __str__(self):
        return f'ScriptInfo[{self.state}]{self.scene_history}] -> {list(self.scene_states.keys())}'

# We could add player information but this may not be the way to do it
# todo: think about what information we want to store at a global level for a player
#
# @dataclass
# class Locations:
#     scene: str = ""
#     room: str = ""
#     script: str = ""
#
#     def str(self):
#         return f'{self.script}:{self.scene}.{self.room}'
#
#
# @dataclass
# class PlayerInfo:
#     name: str
#     locations: Locations

# todo: Thoughts on Player State
# todo:
# todo: Originally I thought that nearly all player state changes would take place in rooms and it made
# todo: sense to optimize changes though the room pathway. Unfortunately, though that's true from the
# todo: perspective of tracking which room they are in and which room is next, there's a level of state'd
# todo: storage that does need to be accessed reguarlly and from other places.
# todo:
# todo: Additionally, I've been thinking that it would be useful to have a way to have event-based storage.
# todo: Like, instead of clearing flags at the end of a conference, we create a 'conference1' event on the
# todo: player, and then we delete the event and all its flags with it. Maybe this could be done though
# todo: sub-keys for the player.
# todo:
# todo: Also I've started storing some information about where the player is in the script in the player object
# todo: which isn't really a good approach. That should be in the shared script state object and passed around
# todo: wherever we need it.
# todo:
# todo: Eventually, I think we should transform the single monolithic storage into a more modular systems
# todo: which are loaded and saved seperately:
# todo: - room / scene location tracking section (like now but w/o `data` members) (plr:+14156864014:telemarketopia:position)
# todo: - script / scene / room storage (plr:+14156864014:telemarketopia:reg)
# todo: - events associated with player & script (plr:+14156864014:telemarketopia:event:<name>)


class Player(Logger):

    _info = 'info'
    _scripts_key = 'scripts'
    _generation_key = 'generation'

    @classmethod
    async def _get_player_keys(cls, db = None) -> List[str]:
        # This is a bad method, but I'm not sure how to make it better. There is no documentation in redio about
        # how to specify a filter in scan (which redis supports but we'd need to format properly) and, in any
        # case, a filter would still get all keys first but only give friendly some of them. Hopefully a minor
        # optimization?
        if db is None:
            db = new_redis()
        cursor = "0"
        players = []
        while True:
            scan = await db.scan(cursor) # don't use autodecode here because the cursor should stay a string I think?
            cursor = scan[0].decode("utf-8") # scan returns bytes
            these_players = [entry.decode("utf-8") for entry in scan[1] if entry[0:4] == b'plr:']
            for entry in these_players:
                print(entry)

            players.extend(these_players)

            if cursor == "0":
                break

        return players

    @classmethod
    async def get_all_json(cls) -> dict:
        db = new_redis()
        players = await cls._get_player_keys(db)
        result = {}
        for player in players:

            play_dict = await db.get(player).autodecode
            result[player] = play_dict

        return result

    @classmethod
    async def reset(cls, plr: Union[str, 'Player']):
        db = new_redis()
        if not isinstance(plr, Player):
            plr = Player(plr)
        return await db.delete(plr.key)

    @classmethod
    def from_number(cls, number: Union[int, str]) -> str:
        return f'plr:+{number}'

    def __init__(self, number: Union[str, PhoneNumber]):
        super(Player, self).__init__()
        global _redis
        self.number = PhoneNumber(number)
        self._generation = 0
        self._db = new_redis()
        self._data = {}
        # self.info: Optional[PlayerInfo] = None
        self.scripts: Optional[Dict[str, ScriptInfo]] = None
        self._loaded = False

    # connection stuff

    async def load(self):
        jsn = await self._db.get(self.key)
        if not jsn:
            jsn = "{}"
        self._data = json.loads(jsn)
        await self.load_state_from_dict(self._data)

    async def load_state_from_dict(self, data):
        self._generation = data.get(self._generation_key, 0)
        # deletes the generation key without raising an error if it doesn't exist
        # https://stackoverflow.com/questions/11277432/how-can-i-remove-a-key-from-a-python-dictionary
        # !POP RETURN VALUE INTENTIONALLY IGNORED!
        data.pop(self._generation_key, None)

        # self.info = self._load_info(self._data)
        self.scripts = self._load_scripts(data)
        self.d(f'Loaded: {self.scripts}')

        self._data = data
        self._loaded = True

    async def advance_generation_to(self, state_data):
        # increase our generation and overwrite the current object in redis, making sure our data survives until
        # we start a request with that generation
        # get latest

        # make backup
        await self.load()
        # copy the latest generation
        backup_gen = self._generation
        await self.load_state_from_dict(state_data)
        self._generation = backup_gen + 1

        # replace whatever was in the db with the state we got passed
        await self.save()

    def get_snapshot(self):
        return self.data

    @classmethod
    def _load_scripts(cls, data: dict):
        scripts = data.get(cls._scripts_key, {})
        return {
            script: ScriptInfo.from_dict(info) for script, info in scripts.items()
        }

    # def _load_info(self, data):
    #     return dataclass_from_dict(
    #         PlayerInfo,
    #         data.get(self._info, {})
    #     )

    @property
    def key(self):
        return f'plr:{self.number.e164}'

    async def save(self):
        # always save damnit
        jsn = await self._db.get(self.key)
        if jsn:
            data = json.loads(jsn)
            db_generation = data.get(self._generation_key, 0)
            if db_generation > self._generation:
                # Do not overwrite
                self.d("save(): Aborting due to generaton")
                return

        await self._db.set(self.key, json.dumps(self.data))
        self.d(f"save(): {self.key} <- {json.dumps(self.data)}")

    def ensure_loaded(self):
        if not self._loaded:
            raise ValueError("Must Load a player before using its values")

    @property
    def data(self):
        return {
            self._generation_key: self._generation,
            self._scripts_key: {k: asdict(v) for k, v in self.scripts.items()}
        }

    def set_script(self, script_name: str, info: ScriptInfo) -> None:
        self.scripts[script_name] = info

    def script(self, script_name: str) -> Optional[ScriptInfo]:
        return self.scripts.get(script_name, None)

    def __str__(self):
        return f"Plr[{self.number.friendly}]"
