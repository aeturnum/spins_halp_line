from typing import Dict

from twilio.twiml.voice_response import VoiceResponse


from .story_objects import Room, Scene, Script, SceneAndState
from spins_halp_line.twil import TwilRequest
from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)

#  _____
# |  __ \
# | |__) |___   ___  _ __ ___  ___
# |  _  // _ \ / _ \| '_ ` _ \/ __|
# | | \ \ (_) | (_) | | | | | \__ \
# |_|  \_\___/ \___/|_| |_| |_|___/
#

class AdventureRoom(Room):
    Name = "AdventureRoom"

    async def description(self, script_data: dict, scene_data: dict) -> str:
        pass

    async def choices(self, script_data: dict, scene_data: dict) -> Dict[str, str]:
        pass

    async def action(self, request: TwilRequest, script_data: dict, scene_data: dict):
        self.d("")
        response = VoiceResponse()
        with response.gather(num_digits=1, method="POST") as g:
            message = await self.description(scene_data, scene_data)
            choices = await self.choices(scene_data, scene_data)
            if choices:
                message += "\nWhat would you like to do?"
                for number, text in choices.items():
                    message += f"\nPress {number} to {text}."
            g.say(message=message)
            response.pause(length=2)
            g.say(message=message)
            response.pause(length=2)


        return response

class ShipwreckYardFront(AdventureRoom):
    Name = "Shipwreck Yard Front"

    async def description(self, script_data: dict, scene_data: dict) -> str:
        return (
            "You stand in the front yard of the shipwreck. Behind you is the gate to seventh street."
            "On your right, you can see a fire pit. On your left you can see what looks like a construction"
            "area and a sculpture of a ship."
        )

    async def choices(self, script_data: dict, scene_data: dict) -> Dict[str, str]:
        return {
            "1": "Walk in the front door.",
            "2": "Walk over to the sculpture of the ship."
        }



class ShipwreckYardShip(AdventureRoom):
    Name = "Shipwreck Yard Ship"

    async def description(self, script_data: dict, scene_data: dict) -> str:
        return (
            "You stand next to a sculpture of a ship. It's sprinkled in leaves and needles. You can see that its walls"
            "are thinner than you thought at a distance. It doesn't look that comfortable but the design is striking. You" 
            "can now see a side door."
        )

    async def choices(self, script_data: dict, scene_data: dict) -> Dict[str, str]:
        return {
            "1": "Walk back to the entrance gate.",
            "2": "Enter in the side door."
        }

class ShipwreckLaundry(AdventureRoom):
    Name = "Shipwreck Laundry Room"

    async def description(self, script_data: dict, scene_data: dict) -> str:
        return (
            "You stand in a cluttered storage room. A washer and dryer are stacked in the corner, opposite an exercise"
            "machine. Someone is doing a load of laundry. There's another door that leads further into the house and the"
            "door leading back out to the yard."
        )

    async def choices(self, script_data: dict, scene_data: dict) -> Dict[str, str]:
        return {
            "1": "Walk out to the side yard.",
            "2": "Go into the living room."
        }

class ShipwreckLivingRoom(AdventureRoom):
    Name = "Shipwreck Living Room"

    async def description(self, script_data: dict, scene_data: dict) -> str:
        return (
            "You stand in a living room. There's a carpet with a red starburst under several couches and the walls are"
            "filled with art. There's a broken projector hanging from the ceiling."
        )

    async def choices(self, script_data: dict, scene_data: dict) -> Dict[str, str]:
        return {
            "1": "Walk out the front door into the yard.",
            "2": "Go into the laundry room.",
            "3": "Walk up the stairs"
        }

class ShipwreckLanding(AdventureRoom):
    Name = "Shipwreck Landing"

    async def description(self, script_data: dict, scene_data: dict) -> str:
        return (
            "As you walk up the stairs, you suddenly notice an unsettling light pouring out of the room"
            "on the left. It has a hollow, dark energy to it and you're unsure of what it fortells for you"
            "if you walk into it. However, you're unable to stop yourself as you stride toward it."
            "...Thank you for playing this demo of the adventure system!"
        )

    async def choices(self, script_data: dict, scene_data: dict) -> Dict[str, str]:
        return {}


#   _____
#  / ____|
# | (___   ___ ___ _ __   ___  ___
#  \___ \ / __/ _ \ '_ \ / _ \/ __|
#  ____) | (_|  __/ | | |  __/\__ \
# |_____/ \___\___|_| |_|\___||___/

class ShipwreckScene(Scene):
    Name = "Shipwreck Scene"
    Start = [ShipwreckYardFront()]
    Choices = {
        ShipwreckYardFront(): {
            "1": ShipwreckLivingRoom(),
            "2": ShipwreckYardShip()
        },
        ShipwreckYardShip(): {
            "1": ShipwreckYardFront(),
            "2": ShipwreckLaundry()
        },
        ShipwreckLaundry(): {
            "1": ShipwreckYardShip(),
            "2": ShipwreckLivingRoom()
        },
        ShipwreckLivingRoom(): {
            "1": ShipwreckYardFront(),
            "2": ShipwreckLaundry(),
            "3": ShipwreckLanding()
        }
    }


#   _____           _       _
#  / ____|         (_)     | |
# | (___   ___ _ __ _ _ __ | |_ ___
#  \___ \ / __| '__| | '_ \| __/ __|
#  ____) | (__| |  | | |_) | |_\__ \
# |_____/ \___|_|  |_| .__/ \__|___/
#                    | |
#                    |_|

adventure = Script(
    "Shipwreck Adventure",
    {
        Script_New_State: {
            Script_Any_Number: SceneAndState(ShipwreckScene(), Script_End_State)
        }
    }
)