from twilio.twiml.voice_response import VoiceResponse

from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)
from .story_objects import Room, Scene, Script, SceneAndState, RoomContext


#  _____
# |  __ \
# | |__) |___   ___  _ __ ___  ___
# |  _  // _ \ / _ \| '_ ` _ \/ __|
# | | \ \ (_) | (_) | | | | | \__ \
# |_|  \_\___/ \___/|_| |_| |_|___/
#

class TestIntro(Room):
    Name = "Tip List"

    async def action(self, context: RoomContext):
        self.d("")
        response = VoiceResponse()
        with response.gather(num_digits=1, method="POST") as g:
            g.say(message="This is doctor spins tip line!" +
                          "Please press 1 to do one thing" +
                          "Or press 2 to do another!.", loop=3)

        return response


class TestTip(Room):
    Name = "Tip Read Back"

    async def action(self, context: RoomContext):
        self.d("")
        response = VoiceResponse()
        response.say(f"You chose option Unknown!")
        return response


#   _____
#  / ____|
# | (___   ___ ___ _ __   ___  ___
#  \___ \ / __/ _ \ '_ \ / _ \/ __|
#  ____) | (_|  __/ | | |  __/\__ \
# |_____/ \___\___|_| |_|\___||___/

class TestScene(Scene):
    Name = "Test scene"
    Start = [TestIntro(), TestTip()]


#   _____           _       _
#  / ____|         (_)     | |
# | (___   ___ _ __ _ _ __ | |_ ___
#  \___ \ / __| '__| | '_ \| __/ __|
#  ____) | (__| |  | | |_) | |_\__ \
# |_____/ \___|_|  |_| .__/ \__|___/
#                    | |
#                    |_|

testing = Script(
    "testing",
    {
        Script_New_State: {
            Script_Any_Number: SceneAndState(TestScene(), Script_End_State)
        }
    }
)

# Script.add_script(testing)
