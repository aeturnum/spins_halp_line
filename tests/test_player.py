from spins_halp_line.player import ScriptInfo
from spins_halp_line.util import StateCopy
from spins_halp_line.resources.numbers import PhoneNumber


async def test_player_object():
    si = ScriptInfo.from_dict({})
    snap = StateCopy(si)
    test_value = "test"

    old_value = si.state_manager # probably None
    si.state_manager = test_value


    assert si.state_manager == test_value
    snap.restore()
    assert si.state_manager == old_value

async def test_phone_number():
    p1 = PhoneNumber("4156864014")
    p2 = PhoneNumber("+14156864014")
    p3 = PhoneNumber("+551122223333") # brazilian format

    assert p1.friendly == "(415) 686-4014"
    assert p2.friendly == "(415) 686-4014"
    assert p3.friendly == "+55 11 2222-3333"