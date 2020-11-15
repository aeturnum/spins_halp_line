from spins_halp_line.story_objects import Script, Scene, Room, SceneSet
from spins_halp_line.player import ScriptInfo, Player
from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)


class MockPlayer(Player):

    def __init__(self):
        self.scripts = {}

    def script(self, script_name: str):
        if script_name not in self.scripts:
            self.scripts[script_name] = ScriptInfo(Script_New_State)

        return self.scripts[script_name]


class MockRequest:

    @staticmethod
    def make(player, caller, called):
        return MockRequest(
            player,
            {
                "From": caller,
                "Called": called
            }
        )

    def __init__(self, player, data):
        self.player = player
        self._data = data

    @property
    def data(self):
        return self._data

    @property
    def caller(self):
        return self.data.get("From", None)

    @property
    def num_called(self):
        return self.data.get("Called", None)


class RoomTest(Room):
    Name = "Testing Room"

    def __init__(self, action_value):
        super(RoomTest, self).__init__()
        self.action_value = action_value

    async def action(self, request, script_data, scene_data):
        return self.action_value


async def test_scene():
    expected = 101

    class TestScene(Scene):
        Name = "TestTest Scene"
        Rooms = [RoomTest(expected)]

    script_name = "testing"
    caller = "+1234"
    player = MockPlayer()

    req = MockRequest.make(player, caller, "")

    s = Script(
        script_name,
        {
            Script_New_State: {
                Script_Any_Number: SceneSet([TestScene()], Script_End_State)
            }
        }
    )

    # import pudb.b
    result = await s.play(req)
    assert result == expected
    assert player.scripts[script_name].state == Script_End_State


async def test_two_rooms():
    expected1 = 101
    expected2 = 202

    class TestScene(Scene):
        Name = "test_two_rooms Scene"
        Rooms = [RoomTest(expected1), RoomTest(expected2)]

    script_name = "testing"
    caller = "+1234"
    player = MockPlayer()

    req = MockRequest.make(player, caller, "")

    s = Script(
        script_name,
        {
            Script_New_State: {
                Script_Any_Number: SceneSet([TestScene()], Script_End_State)
            }
        }
    )

    # import pudb.b
    result = await s.play(req)
    assert result == expected1
    result = await s.play(req)
    assert result == expected2
    assert player.scripts[script_name].state == Script_End_State

async def test_state():

    class TestScene(Scene):
        Name = "test_state Scene"
        Rooms = [RoomTest('')]

    script_name = "testing"
    caller = "+1234"
    player = MockPlayer()

    req = MockRequest.make(player, caller, "<anywhere>")

    s = Script(
        script_name,
        {
            Script_New_State: {
                Script_Any_Number: SceneSet([TestScene()], Script_End_State)
            }
        }
    )

    # import pudb.b
    await s.play(req)
    player_data = player.data
    print(f'player.scripts: {player.scripts}')
    print(f'loaded: {player._load_scripts(player_data)}')
    assert player._load_scripts(player_data) == player.scripts
