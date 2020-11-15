from dataclasses import dataclass, field, asdict, fields as datafields
import json
from typing import Any, Dict, Optional, List

import redio

from spins_halp_line.constants import Script_New_State


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
class SceneInfo:
    name: str
    prev_room: Optional[int] = None
    rooms_visited: List[str] = field(default_factory=list)
    data: Dict[Any, Any] = field(default_factory=dict)  # the only field exposed to Rooms

    def __str__(self):
        return f'SceneInfo[{self.name}]{self.rooms_visited}]{self.prev_room}>'


@dataclass
class ScriptInfo:
    state: str
    scene_states: Dict[str, SceneInfo] = field(default_factory=dict)
    scene_path: List[str] = field(default_factory=list)
    data: Dict[Any, Any] = field(default_factory=dict)  # the only field exposed to Rooms

    def scene(self, name: str) -> SceneInfo:
        if name not in self.scene_states.keys():
            self.scene_states[name] = SceneInfo(name=name)

        return self.scene_states[name]

    def __str__(self):
        return f'ScriptInfo[{self.state}]{self.scene_path}] -> {list(self.scene_states.keys())}'

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


# https://gist.github.com/gatopeich/1efd3e1e4269e1e98fae9983bb914f22
def dataclass_from_dict(klass, dikt):
    try:
        fieldtypes = {f.name: f.type for f in datafields(klass)}
        return klass(**{f: dataclass_from_dict(fieldtypes[f], dikt[f]) for f in dikt})
    except Exception:
        return dikt


class Player(object):

    _info = 'info'
    _scripts = 'scripts'

    def __init__(self, number):
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
        self.scripts = self._load_script(self._data)
        self._loaded = True

    # def _load_info(self, data):
    #     return dataclass_from_dict(
    #         PlayerInfo,
    #         data.get(self._info, {})
    #     )

    # we need to do this because dataclasses won't nest by default
    def _load_script(self, data):
        return {
            k: dataclass_from_dict(ScriptInfo, v) for k, v in data.get(self._scripts, {}).items()
        }

    @property
    def _key(self):
        return f'player:{self._number}'

    async def save(self):
        current_data = self.data
        # only write if we've actually changed something
        if current_data != self._data:
            await self._db.set(self._key, json.dumps(current_data))

    def ensure_loaded(self):
        if not self._loaded:
            raise ValueError("Must Load a player before using its values")

    @property
    def data(self):
        return {
            # 'info': asdict(self.info),
            'scripts': {k: asdict(v) for k, v in self.scripts.items()}
        }

    def script(self, script_name: str) -> ScriptInfo:
        if script_name not in self.scripts:
            self.scripts[script_name] = ScriptInfo(Script_New_State)

        return self.scripts[script_name]
