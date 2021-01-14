from spins_halp_line.stories.story_objects import ScriptState, StateShard
from spins_halp_line.resources.redis import delete_key


async def test_basic_shard():
    key = 'test_key'
    try:
        state = ScriptState(key, {
            'test_list': [1],
            'test_dict': {'a':'b'}
        })
        await state.load_from_redis()

        shard = state.shard

        assert shard['version'] == 0
        assert shard['test_list'] == [1]

        shard.append('test_list', 2)
        shard.append('test_dict', 'b', 'c')
        await shard.integrate()

        assert state._state['test_list'][1] == 2
        assert state._state['test_dict']['b'] == 'c'

    finally:
        await delete_key(key)