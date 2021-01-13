from typing import Optional

from spins_halp_line.stories.story_objects import Script, Scene, Room, SceneAndState, RoomContext
from spins_halp_line.player import ScriptInfo, Player
from spins_halp_line.resources.numbers import PhoneNumber
from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)


class MockPlayer(Player):

    def __init__(self, caller):
        self.scripts = {}
        self.number = PhoneNumber(caller)

    def set_script(self, script_name: str, info: ScriptInfo) -> None:
        self.scripts[script_name] = info

    def script(self, script_name: str) -> Optional[ScriptInfo]:
        return self.scripts.get(script_name, None)


class MockRequest:

    @staticmethod
    def make(player, called = "", digits = ""):
        return MockRequest(
            player,
            {
                "From": player.number.e164,
                "Called": called,
                "Digits": digits
            }
        )

    def __init__(self, player, data):
        self.player = player
        self._data = data

    @property
    def data(self):
        return self._data

    @property
    def caller(self) -> Optional[PhoneNumber]:
        if "From" in self.data:
            return PhoneNumber(self.data.get("From"))
        return None

    @property
    def num_called(self) -> Optional[PhoneNumber]:
        if "Called" in self.data:
            return PhoneNumber(self.data.get("Called"))
        return None

    @property
    def digits(self):
        return self.data.get("Digits", None)


class RoomTest(Room):
    def __init__(self, action_value):
        super(RoomTest, self).__init__()
        self.action_value = action_value

    async def action(self, context: RoomContext):
        return self.action_value


class RoomTestOne(RoomTest):
    Name = "First Testing Room"


class RoomTestTwo(RoomTest):
    Name = "Second Testing Room"


class RoomTestThree(RoomTest):
    Name = "Third Testing Room"


# scenes

def one_room(expected):
    class TestScene(Scene):
        Name = "One Room Scene"
        Start = [RoomTestOne(expected)]

    return Script(
        "testing",
        {
            Script_New_State: {
                Script_Any_Number: SceneAndState(TestScene(), Script_End_State)
            }
        }
    )


def two_room(expected1, expected2):
    class TestScene(Scene):
        Name = "Two Room Scene"
        Start = [RoomTestOne(expected1), RoomTestTwo(expected2)]

    return Script(
        "testing",
        {
            Script_New_State: {
                Script_Any_Number: SceneAndState(TestScene(), Script_End_State)
            }
        }
    )

def basic_maze(expected1, expected2, expected3):
    class TestScene(Scene):
        Name = "Two Room Scene"
        Start = [RoomTestOne(expected1)]
        Choices = {
            RoomTestOne(expected1): {
                '1': RoomTestTwo(expected2),
                '*': RoomTestThree(expected3)
            },
            RoomTestTwo(expected1): {
                '1': RoomTestOne(expected1)
            }
        }

    return Script(
        "testing",
        {
            Script_New_State: {
                Script_Any_Number: SceneAndState(TestScene(), Script_End_State)
            }
        }
    )

# tests

async def test_scene():
    expected = 101

    s = one_room(expected)

    caller = "+12223334444"
    player = MockPlayer(caller)

    req = MockRequest.make(player, "+15556667777")

    # import pudb.b
    result = await s.play(req)
    assert result == expected
    assert player.scripts[s.name].state == Script_End_State


async def test_maze():
    s = basic_maze(1, 2, 3)

    caller = "+12223334444"
    player = MockPlayer(caller)

    req = MockRequest.make(player, "+15556667777")

    # import pudb.b
    result = await s.play(req)
    assert result == 1
    assert player.scripts[s.name].state != Script_End_State

    req = MockRequest.make(player, "+15556667777", digits="1")
    result = await s.play(req)
    # check that we went to room two
    assert result == 2
    assert player.scripts[s.name].state != Script_End_State
    result = await s.play(req)
    # back to room one
    assert result == 1
    assert player.scripts[s.name].state != Script_End_State
    req = MockRequest.make(player, "+15556667777", digits="6")
    result = await s.play(req)
    # to final room
    assert result == 3
    # make sure that we detect that no more moves are possible
    assert player.scripts[s.name].state == Script_End_State


async def test_two_rooms():
    expected1 = 101
    expected2 = 202

    s = two_room(expected1, expected2)

    caller = "+12223334444"
    player = MockPlayer(caller)

    req = MockRequest.make(player, "+15556667777")

    # import pudb.b
    result = await s.play(req)
    assert result == expected1
    result = await s.play(req)
    assert result == expected2
    assert player.scripts[s.name].state == Script_End_State

async def test_state():
    s = one_room("")

    caller = "+12223334444"
    player = MockPlayer(caller)

    req = MockRequest.make(player, "+15556667777")

    # import pudb.b
    await s.play(req)
    player_data = player.data
    print(f'player.scripts: {player.scripts}')
    print(f'loaded: {player._load_scripts(player_data)}')
    assert player._load_scripts(player_data) == player.scripts
