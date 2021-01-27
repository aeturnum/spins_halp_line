import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Union, Optional

from twilio.twiml.voice_response import VoiceResponse, Gather

from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.player import ScriptInfo, Player
from spins_halp_line.stories.story_objects import Room, RoomContext, Scene, Shard, ScriptStateManager
from spins_halp_line.stories.tele_constants import Telemarketopia_Name, _path
from spins_halp_line.tasks import add_task

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

    async def get_audio_for_room(self, context: RoomContext):
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
            self.d(f'Got Audio Resource: {res}')
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

    @property
    def telemarketopia(self) -> Optional[dict]:
        # print(f'Telemarketopia accessor: {self.scripts}')
        return getattr(self.scripts.get(Telemarketopia_Name, {}), 'data', {})

    def record_timestamp(self, name: str):
        self.telemarketopia[name] = datetime.now().isoformat()

    def check_timestamp(self, name: str, within: timedelta):
        self.d(f'check_timestamp(name:{name}, within:{timedelta}')
        old_ts = self.telemarketopia.get(name, None)
        if old_ts:
            ready = datetime.fromisoformat(old_ts)
            self.d(f'check_timestamp(name:{name}, within:{timedelta}) - old_ts:{ready}, {within} < {(datetime.now() - ready)}')
            return within < (datetime.now() - ready)

        return False

    @property
    def path(self) -> Optional[str]:
        return self.telemarketopia.get(_path)


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

    def __str__(self):
        return f'TeleState: {json.dumps(asdict(self))}'


class TeleShard(TeleState, Shard):
    def __init__(self, *args, **kwargs):
        Shard.__init__(self)
        TeleState.__init__(self, *args, **kwargs)