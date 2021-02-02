import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Union, Optional

from twilio.twiml.voice_response import VoiceResponse, Gather

from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.resources.numbers import PhoneNumber
from spins_halp_line.player import ScriptInfo, Player
from spins_halp_line.stories.story_objects import Room, RoomContext, Scene, Shard
from spins_halp_line.stories.tele_constants import (
    Telemarketopia_Name, Key_path, Key_ready_for_conf
)

_player_in_first_conference = 'player_in_first_conference'
_has_decision_text = 'player_has_decision_text'
_partner = 'ending_partner'
_player_final_choice = 'final_choice'
_in_final_final = 'player_in_final_final'

#   _____                 _       _    _____ _
#  / ____|               (_)     | |  / ____| |
# | (___  _ __   ___  ___ _  __ _| | | |    | | __ _ ___ ___  ___  ___
#  \___ \| '_ \ / _ \/ __| |/ _` | | | |    | |/ _` / __/ __|/ _ \/ __|
#  ____) | |_) |  __/ (__| | (_| | | | |____| | (_| \__ \__ \  __/\__ \
# |_____/| .__/ \___|\___|_|\__,_|_|  \_____|_|\__,_|___/___/\___||___/
#        | |
#        |_|


class TeleRoom(Room):
    Name = "TeleRoom"
    State_Transitions = {}
    Gather = True
    Gather_Digits = 1

    def __init__(self):
        super(TeleRoom, self).__init__()
        self.resources: List[RSResource] = []

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

    async def get_audio_for_room(self, context: RoomContext) -> Union[RSResource, List[RSResource]]:
        return await self.get_resource_for_path(context)

    async def get_resource_for_path(self, context: RoomContext):
        if len(self.resources) == 1:
            return self.resources[0]

        for resource in self.resources:
            # self.d(f'get_resource_for_path() {resource}')
            if context.script['path'] == resource.path:
                # self.d(f'get_resource_for_path() Returning: {resource}')
                return resource

    async def action(self, context: RoomContext):
        self.d(f"action() context: {context}")
        response = VoiceResponse()

        if self.Gather:
            maybe_gather = Gather(num_digits=self.Gather_Digits, method="POST", action_on_empty_result=True)
            response.append(maybe_gather)
        else:
            maybe_gather = response

        res = await self.get_audio_for_room(context)
        # Some rooms do not have audio and only exist to take actions and hang up on the player
        if res:
            self.d(f'Got Audio Resource(s): {res}')
            if isinstance(res, list):
                for r in res:
                    maybe_gather.play(r.url, loop=1)
            else:
                maybe_gather.play(res.url, loop=1)
        else:
            vr = VoiceResponse()
            vr.hangup()
            return vr

        return response


class PathScene(Scene):
    Choices: Dict[Room, Dict[str, Dict[str, Union[Room, List[Room]]]]] = {}
    # Choices has a new structure here:
    # Choices = {
    #   <path>: {
    #       "*": Room()
    #   }
    # }
    #
    # <path> can be a string (stored in the players' script data object
    # or it can be '*' meaning it doesn't matter

    def _index_rooms(self):
        self._room_index: Dict[str, Room] = {}
        for r in self.Start:
            self._add_to_index(r)
        for r, paths in self.Choices.items():
            self._add_to_index(r)

            for path, room_dict in paths.items():
                for choice, room_choice in room_dict.items():
                    self._add_to_index(room_choice)

    def _get_choice_for_request(self, number: str, room: Room, script_state: ScriptInfo):
        path = script_state.data.get('path')
        # select path
        path_options = self.Choices.get(room)  # dictionary path choices
        if len(path_options.keys()) == 1:
            # We just are using '*'
            room_choices = path_options.get(path,
                                            path_options.get('*')
                                            )
        else:
            # This could throw an exception, which is fine
            room_choices = path_options[path]

        self.d(f"_get_queue() choices: {room_choices}")
        # todo: standardize digits as a string?
        queue = None
        if number in room_choices:
            queue = room_choices[number]
            self.d(f"Choice #{number}: {queue}")
        elif '*' in room_choices:  # default
            queue = room_choices['*']
            self.d(f"Choice *: {queue}")

        return queue


class TelePlayer(Player):

    Infinity = timedelta(days=3650)  # 10 years

    @property
    def telemarketopia(self) -> Optional[dict]:
        # print(f'Telemarketopia accessor: {self.scripts}')
        return getattr(self.scripts.get(Telemarketopia_Name, {}), 'data', {})

    # flag section

    # If the player has responded to our text asking them if they are ready
    @property
    def ready_for_conference(self):
        return self.telemarketopia.get(Key_ready_for_conf, False)

    @ready_for_conference.setter
    def ready_for_conference(self, value):
        self.telemarketopia[Key_ready_for_conf] = bool(value)

    # If player is in final conference
    @property
    def in_final_conference(self):
        return self.telemarketopia.get(_in_final_final, False)

    @in_final_conference.setter
    def in_final_conference(self, value):
        self.telemarketopia[_in_final_final] = bool(value)

    # If player is in final conference
    @property
    def was_sent_final_decision_text(self):
        return self.telemarketopia.get(_has_decision_text, False)

    @was_sent_final_decision_text.setter
    def was_sent_final_decision_text(self, value):
        self.telemarketopia[_has_decision_text] = bool(value)

    # In the first conference or not
    @property
    def player_in_first_conference(self) -> bool:
        return self.telemarketopia.get(_player_in_first_conference, False)

    @player_in_first_conference.setter
    def player_in_first_conference(self, value):
        self.telemarketopia[_player_in_first_conference] = bool(value)

    # The final choice the player makes after the conference
    @property
    def path(self) -> str:
        return self.telemarketopia.get(Key_path, None)

    @path.setter
    def path(self, value):
        self.telemarketopia[Key_path] = str(value)

    # The final choice the player makes after the conference
    @property
    def final_choice(self) -> str:
        return self.telemarketopia.get(_player_final_choice, None)

    @final_choice.setter
    def final_choice(self, value):
        self.telemarketopia[_player_final_choice] = str(value)

    # Partner in the conference
    @property
    def partner(self) -> str:
        return self.telemarketopia.get(_partner, None)

    @partner.setter
    def partner(self, value: Union[str, PhoneNumber, Player]):
        if isinstance(value, str):
            value = PhoneNumber(value)

        if isinstance(value, Player):
            value = value.number

        self.telemarketopia[_partner] = value.e164

    # script_info.data[_player_final_choice] = text_request.text_body.strip()
    # partner = TelePlayer(script_info.data[_partner])

    async def clear(self, keys: Union[List[str], str]):
        self.d(f'clear({keys})')
        if not isinstance(keys, list):
            keys = [keys]
        for k in keys:
            self.telemarketopia.pop(k, None)

        await self.save()

    async def reset_conference_flags(self):
        await self.clear([
            Key_ready_for_conf, _in_final_final,
            _player_in_first_conference, _partner
        ])

    @classmethod
    def record_timestamp(cls, data: dict, name: str):
        data[name] = datetime.now().isoformat()
        print(f'record_timestamp(name:{name}) -> {data}')

    def timestamp(self, name: str):
        self.record_timestamp(self.telemarketopia, name)

    def time_passed(self, name: str):
        # self.d(f'check_timestamp(name:{name}, within:{timedelta}): {self.telemarketopia}')
        passed = self.Infinity
        old_ts = self.telemarketopia.get(name, None)
        if old_ts:
            # self.d(f'check_timestamp(name:{name}) -> {datetime.now() - datetime.fromisoformat(old_ts)}')
            passed = datetime.now() - datetime.fromisoformat(old_ts)

        if passed == self.Infinity:
            self.d(f'check_timestamp(name:{name}) -> Infinity!')
        else:
            self.d(f'check_timestamp(name:{name}) -> {passed}')
        return passed


#   _____           _       _      _____ _                        _    _____ _        _
#  / ____|         (_)     | |    / ____| |                      | |  / ____| |      | |
# | (___   ___ _ __ _ _ __ | |_  | (___ | |__   __ _ _ __ ___  __| | | (___ | |_ __ _| |_ ___
#  \___ \ / __| '__| | '_ \| __|  \___ \| '_ \ / _` | '__/ _ \/ _` |  \___ \| __/ _` | __/ _ \
#  ____) | (__| |  | | |_) | |_   ____) | | | | (_| | | |  __/ (_| |  ____) | || (_| | ||  __/
# |_____/ \___|_|  |_| .__/ \__| |_____/|_| |_|\__,_|_|  \___|\__,_| |_____/ \__\__,_|\__\___|
#                    | |
#                    |_|


@dataclass
class TeleState:
    clavae_players: List[str] = field(default_factory=list)
    karen_players: List[str] = field(default_factory=list)
    clavae_waiting_for_conf: List[str] = field(default_factory=list)
    karen_waiting_for_conf: List[str] = field(default_factory=list)
    clavae_in_conf: List[str] = field(default_factory=list)
    karen_in_conf: List[str] = field(default_factory=list)
    clavae_final_conf: List[str] = field(default_factory=list)
    karen_final_conf: List[str] = field(default_factory=list)

    @property
    def all_lists(self):
        return [
            self.clavae_players,
            self.karen_players,
            self.clavae_waiting_for_conf,
            self.karen_waiting_for_conf,
            self.clavae_in_conf,
            self.karen_in_conf,
            self.clavae_final_conf,
            self.karen_final_conf
        ]

    def __str__(self):
        return f'TeleState: {json.dumps(asdict(self))}'


class TeleShard(TeleState, Shard):
    def __init__(self, *args, **kwargs):
        Shard.__init__(self)
        TeleState.__init__(self, *args, **kwargs)