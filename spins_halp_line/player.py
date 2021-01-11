from dataclasses import dataclass, field, asdict, fields as datafields
import json
from typing import Any, Dict, Optional, List

import redio

from spins_halp_line.util import Logger
from spins_halp_line.constants import Script_New_State, Script_End_State


# holds the class that manages the player info in redis
# todo: Consider using a single coroutine to do all loading and storing of players so that
# todo: we can detect if a player is getting race condition'd (i.e. there are two copies of them)
# todo: out and they might get squashed


def redis_factory() -> redio.Redis:
    return redio.Redis("redis://localhost/")


# global redis connection factory
_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        _redis = redis_factory()

    return _redis()


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


@dataclass
class ScriptInfo:
    state: str = Script_New_State
    scene_states: Dict[str, SceneInfo] = field(default_factory=dict)
    scene_history: List[str] = field(default_factory=list)
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



class Player(Logger):

    _info = 'info'
    scripts_key = 'scripts'

    @classmethod
    async def _get_player_keys(cls) -> List[str]:
        # This is a bad method, but I'm not sure how to make it better. There is no documentation in redio about
        # how to specify a filter in scan (which redis supports but we'd need to format properly) and, in any
        # case, a filter would still get all keys first but only give us some of them. Hopefully a minor
        # optimization?
        db = _get_redis()
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
    async def get_all_json(cls) -> List[dict]:
        db = _get_redis()
        players = await cls._get_player_keys()
        print(await db.mget(" ".join(players)).autodecode)
        return ""

    def __init__(self, number):
        super(Player, self).__init__()
        global _redis
        self._number = number
        self._db = _get_redis()
        self._data = {}
        # self.info: Optional[PlayerInfo] = None
        self.scripts: Optional[Dict[str, ScriptInfo]] = None
        self._loaded = False

    # connection stuff

    async def load(self):
        jsn = await self._db.get(self._key)
        if not jsn:
            jsn = "{}"
        self._data = json.loads(jsn)
        # self.info = self._load_info(self._data)
        self.scripts = self._load_scripts(self._data)
        self.d(f"loaded scripts: {self.scripts}")
        self._loaded = True

    @classmethod
    def _load_scripts(cls, data: dict):
        scripts = data.get(cls.scripts_key, {})
        return {
            script: ScriptInfo.from_dict(info) for script, info in scripts.items()
        }

    # def _load_info(self, data):
    #     return dataclass_from_dict(
    #         PlayerInfo,
    #         data.get(self._info, {})
    #     )

    @property
    def _key(self):
        return f'plr:{self._number}'

    async def save(self):
        # always save damnit
        await self._db.set(self._key, json.dumps(self.data))

    def ensure_loaded(self):
        if not self._loaded:
            raise ValueError("Must Load a player before using its values")

    @property
    def data(self):
        return {
            # 'info': asdict(self.info),
            self.scripts_key: {k: asdict(v) for k, v in self.scripts.items()}
        }

    def set_script(self, script_name: str, info: ScriptInfo) -> None:
        self.scripts[script_name] = info

    def script(self, script_name: str) -> Optional[ScriptInfo]:
        return self.scripts.get(script_name, None)

    def __str__(self):
        return f"Player[{self._number}]"
