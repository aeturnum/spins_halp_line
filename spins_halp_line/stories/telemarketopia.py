from twilio.twiml.voice_response import VoiceResponse, Play

from .story_objects import Room, Scene, Script, SceneAndState, RoomContext, ScriptState
from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.actions.conferences import TwilConference
from spins_halp_line.constants import (
    Script_New_State,
    Script_Any_Number,
    Script_End_State
)


class AdventureRoom(Room):
    Name = "AdventureRoom"
    State_Transitions = {}
    Gather = True
    Gather_Digits = 1

    def __init__(self):
        super(AdventureRoom, self).__init__()
        self.resources = []

    async def load(self):
        self.resources = await RSResource.for_room(self.Name)
        for res in self.resources:
            await res.load()

    async def new_player_choice(self, choice: str, context: RoomContext):
        self.d(f"new_player_choice({choice}) context: {context}")
        current_transitions = self.State_Transitions.get(context.state, {})
        if choice in current_transitions:
            context.state = current_transitions[choice]
            self.d(f"new_player_choice({choice}) new state: {context.state}")

    async def action(self, context: RoomContext):
        self.d(f"action() context: {context}")
        response = VoiceResponse()
        for res in self.resources:
            p = Play(res.url, loop=1)
            response.append(p)
        if self.Gather:
            with response.gather(num_digits=self.Gather_Digits, method="POST", action_on_empty_result=True) as g:
                g.pause(length=2)

        return response

# state
_clavae_players = 'clave_players'
_karen_players = 'karen_players'
_clav_waiting_for_conf = 'clave_play_waiting_for_conf'
_kar_waiting_for_conf = 'karen_play_waiting_for_conf'

class TeleState(ScriptState):

    def __init__(self):
        super(TeleState, self).__init__(
            {
                _clavae_players: [],
                _karen_players: [],
                _clav_waiting_for_conf: [],
                _kar_waiting_for_conf: [],
            }
        )

    @staticmethod
    async def do_reduce(state):
        # todo: think about doing something about how recently players have been active?
        # todo: players who have been out for a while might not want to play

        return state


# subclass to handle our specific needs around conferences
class TeleConference(TwilConference):

    # do the things we need to do once players leave the conference
    async def do_handle_event(self, event, participant):


        return False


class TipLineScene(Scene):
    Name = "Telemarketopia Tip Line Scene"
    Start = []
    Choices = {
    }

telemarketopia = Script(
    "Telemarketopia",
    {
        Script_New_State: {
            Script_Any_Number: SceneAndState(TipLineScene(), Script_End_State)
        }
    },
    ScriptState({})
)