from twilio.twiml.voice_response import VoiceResponse

from .story_objects import Room, Scene, Script, SceneAndState, RoomContext
from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)

class TipLineScene(Scene):
    Name = "TipLine Scene"
    Start = []
    Choices = {
    }

telemarketopia = Script(
    "Telemarketopia",
    {
        Script_New_State: {
            Script_Any_Number: SceneAndState(TipLineScene(), Script_End_State)
        }
    }
)