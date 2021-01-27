from typing import List, Optional, Union, Dict
import json

from spins_halp_line.stories.story_objects import Script
from spins_halp_line.util import Logger
from spins_halp_line.player import Player

async def replace_script_state(state_name: str, new_state_dict: dict):
    target_script = None
    for script in Script.Active_Scripts:
        if script.name == state_name:
            target_script = script

    # Who knows what happens if there is an exception in here
    target_script.state_manager._state = target_script.state_manager._make_new_state(new_state_dict)
    # will replace all versions of the state with this version
    await target_script.state_manager.set_new_generation()

async def replace_player_state(number: str, new_state_dict: dict):
    player = Player(number)
    await player.advance_generation_to(new_state_dict)

class Snapshot(Logger):

    _index = {

    }
    _num = 0

    @classmethod
    def get_snapshot(cls, index) -> Optional['Snapshot']:
        index = str(index)
        return cls._index.get(index, None)

    def __init__(self, script: Optional[Script], players: Optional[List[Player]]):
        super(Snapshot, self).__init__()
        self.script_name: Optional[str] = None
        self.script_snap = None
        self.player: Dict[str, dict] = {}
        self.index = str(self._num)
        self._num += 1

        self._from_objects(script, players)

    def _from_objects(self, script: Optional[Script], players: Optional[List[Player]]):
        if script:
            self.script_name = script.name
            self.script_snap = script.get_snapshot()
        if players:
            self.players = {
                p.key: p.get_snapshot() for p in players
            }

    def save(self):
        # called when a snapshot is used
        self._index[self.index] = self.json
        self.e(f"Snapshot {self.index} saved!:\n{self.json}")

    async def restore(self):
        await replace_script_state(self.script_name, self.script_snap)
        for key, state in self.players.items():
            await replace_player_state(key, state)

    @property
    def data(self):
        return {
            'script': [self.script_name, self.script_snap],
            'players': self.players
        }

    @property
    def json(self):
        return json.dumps(self.data)

    @staticmethod
    def from_json(jsn: Union[str, dict]):
        ss = Snapshot(None, None)

        if isinstance(jsn, str):
            jsn = json.loads(jsn)

        ss.script_name = jsn['script'][0]
        ss.script_snap = jsn['script'][1]
        ss.players = jsn['players']

        return ss