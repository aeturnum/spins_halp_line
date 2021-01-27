import pytest
from typing import List
from dataclasses import asdict, dataclass, field

from spins_halp_line.stories.story_objects import ScriptStateManager, StateShard, ScriptState, Shard
from spins_halp_line.resources.redis import delete_key

@dataclass
class TestState:
    version: int = 0
    player_list: List[str] = field(default_factory=lambda: [1])
    player_list_2: List[str] = field(default_factory=list)


class TestShard(TestState, Shard):
    def __init__(self, *args, **kwargs):
        Shard.__init__(self)
        TestState.__init__(self, *args, **kwargs)


class TestManager(ScriptStateManager):
    def _make_new_state(self) -> TestState:
        return TestState()

    def _make_shard(self) -> TestShard:
        shard = TestShard(**self._state_dict)
        shard.set_parent(self)
        return shard


async def test_basic_shard():
    key = 'test_key'
    try:
        state = TestManager()
        state.set_key(key)

        await state.load_from_redis()

        shard = state.shard

        assert shard.version == 0
        assert shard.player_list == [1]
        assert len(shard.player_list_2) == 0

        shard.move('player_list', 'player_list_2', 1)
        shard.append('player_list', 2)
        await shard.integrate()

        assert state._state.player_list[0] == 2
        assert state._state.player_list_2[0] == 1

    finally:
        await delete_key(key)

async def test_state_shard():
    scst = ScriptState()
    scst.version = 2

    ss = StateShard(**asdict(scst))
    # this is not actually a parent :p

    ss.set_parent(scst)

    assert ss.version == 2
    with pytest.raises(ValueError):
        ss.version += 1