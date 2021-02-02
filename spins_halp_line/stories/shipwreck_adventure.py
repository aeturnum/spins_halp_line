from typing import Dict

from twilio.twiml.voice_response import VoiceResponse

from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)
from .story_objects import Room, Scene, Script, SceneAndState, RoomContext, ScriptStateManager


#  _____
# |  __ \
# | |__) |___   ___  _ __ ___  ___
# |  _  // _ \ / _ \| '_ ` _ \/ __|
# | | \ \ (_) | (_) | | | | | \__ \
# |_|  \_\___/ \___/|_| |_| |_|___/
#

class AdventureRoom(Room):
    Name = "AdventureRoom"
    State_Transitions = {}
    Gather = True

    def loop(self):
        return 2

    async def new_player_choice(self, choice: str, context: RoomContext):
        self.d(f"new_player_choice({choice}) context: {context}")
        current_transitions = self.State_Transitions.get(context.state, {})
        if choice in current_transitions:
            context.state = current_transitions[choice]
            self.d(f"new_player_choice({choice}) new state: {context.state}")

    async def description(self, context: RoomContext) -> str:
        pass

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        pass

    async def action(self, context: RoomContext):
        self.d(f"action() context: {context}")
        response = VoiceResponse()
        message = await self.description(context)
        if self.Gather:
            with response.gather(num_digits=1, method="POST", action_on_empty_result=True) as g:
                choices = await self.choices(context)
                if choices:
                    message += "\nWhat would you like to do?"
                    for number, text in choices.items():
                        message += f"\nPress {number} to {text}."
                for loop in range(0, self.loop()):
                    g.say(message=message)
                    # don't pause the last time
                    if loop < self.loop() - 1:
                        g.pause(length=2)
        else:
            response.say(message=message)

        return response


class ShipwreckYardFront(AdventureRoom):
    Name = "Shipwreck Yard Front"

    async def description(self, context: RoomContext) -> str:
        return (
            "You stand in the front yard of the shipwreck. Behind you is the gate to seventh street."
            "On your right, you can see a fire pit. On your left you can see what looks like a construction"
            "area and a sculpture of a ship."
        )

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        choices = {
            "1": "Walk in the front door.",
            "2": "Walk over to the sculpture of the ship.",
            "3": "Walk over to the fire pit.",
            "4": "Turn around and leave the yard"
        }

        return choices


class ShipwreckYardShip(AdventureRoom):
    Name = "Shipwreck Yard Ship"
    State_Transitions = {
        "": {
            "3": "Ship_Push"
        },
        "Ship_Push": {
            "3": "Ship_Fix"
        }
    }

    async def description(self, context: RoomContext) -> str:
        text = ""

        if not context.state:
            text += (
                "You stand next to a sculpture of a ship. It's sprinkled in leaves and needles. "
                "You can see that its walls are thinner than you thought at a distance. "
                "It doesn't look that comfortable but the design is striking. "
                "You can now see a side door next to the construction area. "
            )
        elif context.state == "Ship_Push":
            if context.state_is_new:
                text += (
                    "You shove the ship. It's lighter than you thought and it tips over violently. "
                    "The bow strikes the ground and shatters, splintering all over the ground. "
                    "You jump back to avoid the shards. "
                )

            text += (
                "You stand next to a sculpture of a ship lying on its side. "
                "It's sprinkled in leaves and needles and its bow is broken. "
                "You feel bad about pushing it over. "
                "You can now see a side door next to the construction area. "
            )
        elif context.state == "Ship_Fix":

            context.scene["has_pendant"] = True

            if context.state_is_new:
                text += (
                    "You pull the ship back so that it's standing up. "
                    "The damage is less serious than it seemed with it lying on the ground. "
                    "The prow, once shapely and curved, is now pointed and sharp. "
                    "While you fix the ship you discover a small pendant on the ground. "
                    "Its made of a material you can't identify and you can't resist tucking it into your pocket. "
                    "You feel a little better about pushing the ship over. "
                )
            text += (
                "You stand next to a sculpture of a ship. It's sprinkled in leaves and needles. "
                "The freshly pointed prow gives the ship a warlike, strident quality. "
            )
        return text

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        choices = {
            "1": "Walk back to the entrance gate.",
            "2": "Enter in the side door."
        }

        if not context.state:
            choices["3"] = "Push the ship over."
        elif context.state == "Ship_Push":
            choices["3"] = "Try to fix the ship."

        return choices


class ShipwreckYardSide(AdventureRoom):
    Name = "Shipwreck Yard Side"

    State_Transitions = {
        "": {
            "3": "Fire_On"
        },
        "Fire_On": {
            "3": ""
        }
    }

    async def description(self, context: RoomContext) -> str:
        text = ""
        if not context.state:
            text += (
                "You're standing in front of a propane fire pit. It's surrounded by a circle of chairs. "
            )
        elif context.state == "Fire_On":
            if context.state_is_new:
                text += "You light the propane burner and it whooshes up into a cheery fire. "

            text += (
                "You're standing in front of a propane fire pit. It's lit, but the fire doesn't cast much "
                "heat or light in the sunlight. It's surrounded by a circle of chairs."
            )

        # common
        text += (
            "Nearby you can see the can of propane, attached with a hose, and a lighter. "
            "At the side of the house you can see some trash cans and, next to them, a second door "
            "into the house."
        )

        return text

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        choices = {
            "1": "Walk in to the door closest to you.",
            "2": "Walk back to the entrance gate.",
        }

        if not context.state:
            choices["3"] = "Turn on the propane fire"
        else:
            choices["3"] = "Turn off the propane fire"

        return choices


class ShipwreckLaundry(AdventureRoom):
    Name = "Shipwreck Laundry Room"

    async def description(self, context: RoomContext) -> str:
        return (
            "You stand in a cluttered storage room. A washer and dryer "
            "are stacked in the corner, opposite an exercise machine. Someone is doing a load of laundry. "
            "There's another door that leads further into the house and the door leading back out to the yard."
        )

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        return {
            "1": "Walk out to the side yard.",
            "2": "Go into the living room."
        }


class ShipwreckLivingRoom(AdventureRoom):
    Name = "Shipwreck Living Room"

    async def description(self, context: RoomContext) -> str:
        return (
            "You stand in a living room. There's a carpet with a starburst of bright red tufts "
            "coming out of its center. The carpet is surrounded by several couches and the walls are "
            "filled with art. There's a broken projector hanging from the ceiling. "
        )

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        return {
            "1": "Walk out the front door into the yard.",
            "2": "Go into the laundry room.",
            "3": "Go into the kitchen.",
            "4": "Walk up the stairs"
        }


class ShipwreckKitchen(AdventureRoom):
    Name = "Shipwreck Kitchen"

    async def description(self, context: RoomContext) -> str:
        return (
            "You stand in a kitchen. On your right, there's a large slate table with small piles of mail laid "
            "out on it. Shelves with various dry goods are mounted above the table. On the left there's a "
            "cooking area with a stove, refrigerator and food prep area. "
            "Back through the door behind you, you can see the yard and a little propane fire pit. "
            "Past the oven, you can see a living room. "
        )

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        return {
            "1": "Walk out of the door into the yard.",
            "2": "Go into the living room."
        }


class ShipwreckLanding(AdventureRoom):
    Name = "Shipwreck Landing"

    def loop(self):
        return 1

    async def description(self, context: RoomContext) -> str:

        text = (
            "As you walk up the stairs, you suddenly notice an unsettling light pouring out of the room "
            "on the left. It has a hollow, dark energy to it and you're unsure of what it fortells for you "
            "if you walk into it. "
        )

        if context.scene.get("has_pendant", False):
            text += (
                "As you feel your body being drawn towards the light, you feel something weighing you down in your pocket. "
                "You reach down and pull out the pendant you found earlier. As you hold it up to the door you can feel "
                "the lights' pull on your body lessen. The pendant seems to cancel out the threatening nature of the glow. "
                "You put the pendant around your neck and stride, with confidence, into the light. "
            )
        else:
            text += (
                "However, you're unable to stop yourself as you stride toward it."
            )

        return text

    async def choices(self, context: RoomContext) -> Dict[str, str]:
        return {}


class ShipwreckEnding(AdventureRoom):
    Name = "Shipwreck Ending"
    Gather = False

    def loop(self):
        return 1

    async def description(self, context: RoomContext) -> str:
        context.end_scene()
        return (
            "Thank you for playing this demo of our phone-based adventure system. "
            "For ease of development, this all uses text-to-speech technology, but we expect the full version "
            "to contain voice acting, sound effects, text messages, and many other fun things to do. "
            "However you heard about this project, we would love it if you kept up with development! "
        )

    async def choices(self, context: RoomContext) -> Dict[str, str]:
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
            "2": ShipwreckYardShip(),
            "3": ShipwreckYardSide(),
            "4": ShipwreckEnding()
        },
        ShipwreckYardSide(): {
            "1": ShipwreckKitchen(),
            "2": ShipwreckYardFront(),
            "3": ShipwreckYardSide()
        },
        ShipwreckKitchen(): {
            "1": ShipwreckYardSide(),
            "2": ShipwreckLivingRoom()
        },
        ShipwreckYardShip(): {
            "1": ShipwreckYardFront(),
            "2": ShipwreckLaundry(),
            "3": ShipwreckYardShip()
        },
        ShipwreckLaundry(): {
            "1": ShipwreckYardShip(),
            "2": ShipwreckLivingRoom()
        },
        ShipwreckLivingRoom(): {
            "1": ShipwreckYardFront(),
            "2": ShipwreckLaundry(),
            "3": ShipwreckKitchen(),
            "4": [ShipwreckLanding(), ShipwreckEnding()]
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
    },
    ScriptStateManager()
)
