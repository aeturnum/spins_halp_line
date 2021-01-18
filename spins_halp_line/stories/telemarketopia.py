from dataclasses import dataclass, field
from typing import Dict, Union, List, Optional, Any
from datetime import datetime, timedelta

from twilio.twiml.voice_response import VoiceResponse, Play, Gather, Hangup
from twilio.base import values
from twilio import rest
import trio

from .story_objects import (
    Room,
    Scene,
    Script,
    SceneAndState,
    RoomContext,
    ScriptState,
    ScriptInfo,
    StateShard,
    TextHandler
)

from spins_halp_line.util import Logger
from spins_halp_line.actions.conferences import new_conference, conferences, TwilConference
from spins_halp_line.actions.twilio import send_sms
from spins_halp_line.tasks import add_task, Task
from spins_halp_line.constants import Credentials, Root_Url
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from spins_halp_line.media.common import (
    Karen_Puzzle_Image_1,
    Clavae_Puzzle_Image_1,
    Telemarketopia_Logo,
    Puppet_Master,
    Clavae_Conference_Intro,
    Karen_Conference_Info,
    Conference_Nudge,
    Karen_Final_Puzzle_Image_1,
    Karen_Final_Puzzle_Image_2,
    Clavae_Final_Puzzle_Image_1,
    Clavae_Final_Puzzle_Image_2
)
from spins_halp_line.twil import TwilRequest
from spins_halp_line.player import Player
from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.actions.conferences import TwilConference
from spins_halp_line.constants import (
    Script_New_State,
    Script_Ignore_Change,
    Script_Any_Number,
    Script_End_State
)


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


#   _____           _       _      _____ _                        _    _____ _        _
#  / ____|         (_)     | |    / ____| |                      | |  / ____| |      | |
# | (___   ___ _ __ _ _ __ | |_  | (___ | |__   __ _ _ __ ___  __| | | (___ | |_ __ _| |_ ___
#  \___ \ / __| '__| | '_ \| __|  \___ \| '_ \ / _` | '__/ _ \/ _` |  \___ \| __/ _` | __/ _ \
#  ____) | (__| |  | | |_) | |_   ____) | | | | (_| | | |  __/ (_| |  ____) | || (_| | ||  __/
# |_____/ \___|_|  |_| .__/ \__| |_____/|_| |_|\__,_|_|  \___|\__,_| |_____/ \__\__,_|\__\___|
#                    | |
#                    |_|

#
#  _______        _
# |__   __|      | |
#    | | _____  _| |_ ___
#    | |/ _ \ \/ / __/ __|
#    | |  __/>  <| |_\__ \
#    |_|\___/_/\_\\__|___/
#

class TextTask(Task):
    Text = ""
    From_Number_Label = None
    Image = values.unset

    def __init__(self, to: PhoneNumber, delay=0):
        super(TextTask, self).__init__(delay)
        self.to = to

    async def execute(self):
        image = self.Image
        if self.Image != values.unset:
            await self.Image.load()
            image = self.Image.url

        from_num = Global_Number_Library.from_label(self.From_Number_Label)
        await send_sms(
            from_num,
            self.to,
            self.Text,
            image
        )


class Clavae1(TextTask):
    Text = "Call me at +1-510-256-7710 to learn the horrible truth about Babyface's Telemarketopia!\n - Clavae"
    From_Number_Label = 'clavae_1'


class Clavae2(TextTask):
    Text = """"
Once you fill this in, this puzzle should give you a five-digit code to get into the database at +1-510-256-7705!
- Clavae"""
    From_Number_Label = 'clavae_2'
    Image = Clavae_Puzzle_Image_1


class Karen1(TextTask):
    Text = "Solving this puzzle will give you the next phone number to call and prove you're Telemarketopia material!"
    From_Number_Label = 'karen_1'
    Image = Karen_Puzzle_Image_1


class Karen2(TextTask):
    Text = "Please call +1-510-256-7675 to continue learning about the exciting opportunities you'll have at Telemarketopia!"
    From_Number_Label = 'karen_2'
    Image = Telemarketopia_Logo


class ConfWait(TextTask):
    Text = "Our systems are working on bisecting the quantum lagrange points, we'll connect you as soon as we can!"
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class ConfReady(TextTask):
    Text = "HEY!\nHey.\n I've got that person you wanted to talk to! Just text back anything when you're ready!!"
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class ConfUnReadyIfReply(TextTask):
    Text = "Oh no, I'm sorry. It looks like the person we paired you up with was less enthusiastic than we expected. Give us some time to find someone else..."
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class ConfUnReadyIfNoReply(TextTask):
    Text = "Oh no! The lagrange solution has become inverted! We're going to have to wait a little longer."
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class KPostConfOptions(TextTask):
    Text = """
Text one of the following to decide what you will do next:
Text 1 if: I believe I have recruited the other team. Hooray! I will request a promotion from Telemarketopia!
Text 2 if: The other team has convinced me to open a Doortal to release Madame Clavae. 
Text 3 if: Attempt to Destroy Telemarketopia!!"""
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class CPostConfOptions(TextTask):
    Text = """
Text one of the following to decide what you will do next:
Text 1 if: The other team has convinced me to join Telemarketopia! I release my body and go forth in search of personal gain and power.
Text 2 if: I believe I have convinced the other team to open a Doortal. Hooray! I’ll tell Madame Clavae the good news.
Text 3 if: Attempt to Destroy Telemarketopia!!"""
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


class CFinalPuzzle1(TextTask):
    Text = """
To break into the central AI Database and hit the manual self-destruct button, you’ll need to enter the correct passcode. Your only clues are these cryptic notes, left inside one of the database passages.
    """
    From_Number_Label = 'final'
    Image = Clavae_Final_Puzzle_Image_1


class CFinalPuzzle2(TextTask):
    Text = """
You’ll need to work together in another voice conference to finish. One of your team needs to text the correct passcode (AND ONLY THE PASSCODE NUMBER) to +1-510-256-7740.
    """
    From_Number_Label = 'final'
    Image = Clavae_Final_Puzzle_Image_2


class KFinalPuzzle1(TextTask):
    Text = """
To break into the central AI Database and hit the manual self-destruct button, you’ll need to enter the correct passcode. Your only clues are these cryptic notes, left inside one of the database passages.
    """
    From_Number_Label = 'final'
    Image = Karen_Final_Puzzle_Image_1


class KFinalPuzzle2(TextTask):
    Text = """
You’ll need to work together in another voice conference to finish. One of your team needs to text the correct passcode (AND ONLY THE PASSCODE NUMBER) to +1-510-256-7740.
    """
    From_Number_Label = 'final'
    Image = Karen_Final_Puzzle_Image_2


async def send_text(TextClass, player_numer: PhoneNumber, delay=0):
    await add_task.send(TextClass(player_numer, delay))

Telemarketopia_Name = "Telemarketopia"

_got_text = 'got_text'

#   _____             __                                    _             _
#  / ____|           / _|                                  | |           | |
# | |     ___  _ __ | |_ ___ _ __ ___ _ __   ___ ___       | |_   _ _ __ | | __
# | |    / _ \| '_ \|  _/ _ \ '__/ _ \ '_ \ / __/ _ \  _   | | | | | '_ \| |/ /
# | |___| (_) | | | | ||  __/ | |  __/ | | | (_|  __/ | |__| | |_| | | | |   <
#  \_____\___/|_| |_|_| \___|_|  \___|_| |_|\___\___|  \____/ \__,_|_| |_|_|\_\


# state keys
_ready_for_conf = 'pickk'
_player_in_first_conference = 'player_in_first_conference'
_has_decision_text = 'player_has_decision_text'
_path = 'path'
_partner = 'ending_partner'
_player_final_choice = 'final_choice'
_in_final_final = 'player_in_final_final'

# paths
Path_Clavae = 'Clavae'
Path_Karen = 'Karen'

# state
_clavae_players = 'clave_players'
_karen_players = 'karen_players'
_clav_waiting_for_conf = 'clave_play_waiting_for_conf'
_kar_waiting_for_conf = 'karen_play_waiting_for_conf'
_waiting_for_conf = 'conferences_pairs_in_progress'
_pair_waiting_for_2nd_conf = 'karen_clave_players_last_conf'

class TeleState(ScriptState):

    def __init__(self):
        super(TeleState, self).__init__(
            {
                _clavae_players: [],
                _karen_players: [],
                _clav_waiting_for_conf: [],
                _kar_waiting_for_conf: [],
                _waiting_for_conf: [],
                _pair_waiting_for_2nd_conf: [],
            }
        )

    @staticmethod
    async def do_reduce(state: dict, shard: StateShard):
        # todo: think about doing something about how recently players have been active?
        # todo: players who have been out for a while might not want to play

        print('do_reduce')
        print(f'do_reduce:{state}')
        # move remove people who have been moved back
        clave_waiting = state.get(_clav_waiting_for_conf)
        karen_waiting = state.get(_kar_waiting_for_conf)
        to_remove = []
        for pair in state[_waiting_for_conf]:
            if pair[0] in clave_waiting and pair[1] in karen_waiting:
                to_remove.append(pair)

        # actually remove the things we just found
        for pair in to_remove:
            state[_waiting_for_conf].remove(pair)

        remove_from_clav = []
        remove_from_kar = []
        clave = state.get(_clavae_players)
        karen = state.get(_karen_players)
        for player in clave:
            if player in karen:
                if (len(clave) + len(remove_from_clav)) > (len(karen) + len(remove_from_kar)):
                    print(f"Player {player} is in both queues, removing from Karen because that one is longer")
                    remove_from_kar.append(player)
                else:
                    print(f"Player {player} is in both queues, removing from Clavae because that one is longer")
                    remove_from_clav.append(player)

        for player in remove_from_clav:
            state.get(_clavae_players).remove(player)

        for player in remove_from_kar:
            state.get(_karen_players).remove(player)

        print("duplicates_removed!")
        print(f'do_reduce:{state}')
        print(f'clav_waiting:{clave_waiting}({len(clave_waiting)})')
        print(f'karen_waiting:{karen_waiting}({len(karen_waiting)})')
        if len(clave_waiting) >= 1 and len(karen_waiting) >= 1:
            # conference time baby!
            clav_p = state[_clav_waiting_for_conf].pop(0)
            karen_p = state[_kar_waiting_for_conf].pop(0)
            print(f'Starting conf with {[clav_p, karen_p]}')
            state[_waiting_for_conf].append([clav_p, karen_p])
            await add_task.send(
                ConferenceTask(
                    state[_clav_waiting_for_conf].pop(0),
                    state[_kar_waiting_for_conf].pop(0),
                    shard
                )
            )

        return state

    async def _after_load(self):
        # WE ARE LOCKED HERE
        for pair in self._state.get(_waiting_for_conf, []):
            self._state[_clav_waiting_for_conf].append(pair[0])
            self._state[_kar_waiting_for_conf].append(pair[1])


class TelePlayer(Player):

    @property
    def telemarketopia(self) -> Optional[dict]:
        return self.scripts.get(Telemarketopia_Name).data

    @property
    def path(self) -> Optional[str]:
        return self.telemarketopia.get(_path)

class ConferenceTask(Task):
    def __init__(self, clavae_player: str, karen_player: str, shard: StateShard, delay: int=0):
        super(ConferenceTask, self).__init__(delay)
        self.clavae_num: PhoneNumber = PhoneNumber(clavae_player)
        self.karen_num: PhoneNumber = PhoneNumber(karen_player)
        self.shard = shard
        self.conference: Optional[TwilConference] = None

        self.clavae_script: Optional[dict] = None
        self.karen_script: Optional[dict] = None

    @classmethod
    def from_conf_task(cls, conf: 'ConferenceTask', delay=None):
        if delay is None:
            delay = conf.delay
        new_conf_t = cls(conf.clavae_num.e164, conf.karen_num.e164, conf.shard, delay)
        new_conf_t.conference = conf.conference

        return new_conf_t

    async def refresh_players(self):
        clave_player = TelePlayer(self.clavae_num)
        karen_player = TelePlayer(self.karen_num)
        await clave_player.load()
        await karen_player.load()

        self.karen_script = karen_player.telemarketopia
        self.clavae_script = clave_player.telemarketopia

    async def check_player_status(self):
        await self.refresh_players()

        # cheeck to make sure we've seen them within last 5
        clavae_ready = self.clavae_script.get(_got_text, None)
        if clavae_ready:
            clavae_ready = datetime.fromisoformat(clavae_ready)
            clavae_ready = timedelta(seconds=60 * 5) < (datetime.now() - clavae_ready)
        karen_ready = self.karen_script.get(_got_text, None)
        if karen_ready:
            karen_ready = datetime.fromisoformat(karen_ready)
            karen_ready = timedelta(seconds=60 * 5) < (datetime.now() - karen_ready)

        return clavae_ready, karen_ready

    async def start_child_task(self, task):
        await add_task(task)

    async def load_conference(self):
        from_number = Global_Number_Library.from_label('conference')
        if not self.conference:
            self.conference = await new_conference(from_number)

        for conf in conferences():
            if conf == self.conference:
                # this *should* not matter but I am past dealing with instance fuckary
                self.conference = conf
                return conf

class ReturnPlayers(ConferenceTask):

    async def unready_text(self, ready: bool, number: PhoneNumber):
        cls = ConfUnReadyIfReply
        if not ready:
            cls = ConfUnReadyIfNoReply
        await send_text(cls, number)

    async def execute(self):
        c_r, k_r = await self.check_player_status()
        # Put back into queue, but put them at the back of the queue if they didn't reply
        self.shard.append(_clav_waiting_for_conf, self.clavae_num.e164, to_front=c_r)
        self.shard.append(_kar_waiting_for_conf, self.karen_num.e164, to_front=c_r)

        # Text player to let them know the conference is off
        await self.unready_text(c_r, self.clavae_num)
        await self.unready_text(k_r, self.karen_num)

        # Send changes and re-run pairing
        await self.shard.integrate()
        await self.shard.trigger_reduction()

class ConnectFirstConference(ConferenceTask):
    async def execute(self):
        self.d(f"ConnectFirstConference({self.clavae_num}, {self.karen_num}): Checking if players connected...")
        await trio.sleep(30)

        await self.load_conference()
        if not self.conference.started:
            self.d(f"ConnectFirstConference({self.clavae_num}, {self.karen_num}): Someone didn't pick up, returning")
            return await add_task(ReturnPlayers.from_conf_task(self))

        await trio.sleep(60 * 5)
        await self.conference.play_sound(Conference_Nudge)

class ConfWaitForPlayers(ConferenceTask):

    @dataclass
    class ConfWaitForPlayersState:
        time_elapsed: int = 0
        text_counts: Dict[str, int] = field(default_factory=dict)  # the only field exposed to Rooms

    def __init__(self, clavae_player: str, karen_player: str, shard: StateShard, delay:int=0, ongoing_state: dict=None):
        super(ConfWaitForPlayers, self).__init__(clavae_player, karen_player, shard, delay)
        if ongoing_state is None:
            ongoing_state = self.ConfWaitForPlayersState(0, {karen_player: 1, clavae_player: 1})
        self.state: ConfWaitForPlayers.ConfWaitForPlayersState = ongoing_state
        self.state.time_elapsed += delay

    @classmethod
    def from_conf_task(cls, conf: 'ConferenceTask', delay=0, last_state = None):
        new_conf_t = cls(conf.clavae_num.e164, conf.karen_num.e164, conf.shard, delay, last_state)
        new_conf_t.conference = conf.conference

        return new_conf_t

    async def maybe_send_text(self, ready: bool, number: PhoneNumber):
        text_count = self.state.text_counts[number]
        if not ready and self.state.time_elapsed > 60 * 5 and text_count == 1:
            await send_text(ConfReady, number)
            self.state.text_counts[number] += 1

    async def execute(self):
        self.d(f"ConfWaitForPlayers({self.clavae_num}, {self.karen_num})")
        c_r, k_r = await self.check_player_status()
        await self.maybe_send_text(c_r, self.clavae_num)
        await self.maybe_send_text(k_r, self.karen_num)

        task_to_start = None
        if not c_r and not k_r:
            self.d(f"ConfWaitForPlayers({self.clavae_num}, {self.karen_num}): {c_r}, {k_r}: someone isn't ready!")
            if self.state.time_elapsed < 60 * 10:
                # wait another 15 seconds and check again
                task_to_start = ConfWaitForPlayers.from_conf_task(self, 15, self.state)
            else:
                self.d(f"ConfWaitForPlayers({self.clavae_num}, {self.karen_num}): Aborting both!")
                # put people back in the queue
                task_to_start = ReturnPlayers.from_conf_task(self)
        else:
            self.d(f"ConfWaitForPlayers({self.clavae_num}, {self.karen_num}): Starting conference")
            await self.conference.add_participant(
                self.clavae_num,
                play_first=Clavae_Conference_Intro
            )

            await self.conference.add_participant(
                self.karen_num,
                play_first=Karen_Conference_Info
            )

            task_to_start = ConnectFirstConference.from_conf_task(self, )

        return await self.start_child_task(task_to_start)

class ConfStartFirst(ConferenceTask):
    async def execute(self):
        self.d(f"ConfStartFirst({self.clavae_num}, {self.karen_num})")

        await send_text(ConfReady, self.clavae_num)
        await send_text(ConfReady, self.karen_num)

        wait_task = ConfWaitForPlayers.from_conf_task(self, 60)
        await self.start_child_task(wait_task)

        # await self.wait_for_players()

    # async def wait_for_players(self):
    #     # wait 1 min
    #     await trio.sleep(60)
    #     await self.refresh_players()
    #
    #     # todo: add task to text players and see if they are ready
    #     c_r, k_r = await self.check_player_status()
    #
    #     count = 60
    #     kr_again = False
    #     cr_again = False
    #     while not c_r and not k_r:
    #         for x in range(0, 3):
    #             await trio.sleep(10)
    #         c_r, k_r = await self.check_player_status()
    #         count += 1
    #
    #         if count > 60 * 5:
    #             # text again if no response and
    #             if not c_r and not cr_again:
    #                 cr_again = True
    #                 await send_text(ConfReady, self.clavae_num)
    #
    #             if not k_r and not kr_again:
    #                 kr_again = True
    #                 await send_text(ConfReady, self.clavae_num)
    #
    #         if count > 60 * 10:
    #             return await self.return_players()
    #
    #     return await self.call_players()
    #
    # async def return_players(self):
    #     c_r, k_r = await self.check_player_status()
    #     self.shard.append(_clav_waiting_for_conf, self.clavae_num.e164, to_front=not c_r)
    #     self.shard.append(_kar_waiting_for_conf, self.karen_num.e164, to_front=not c_r)
    #
    #     await self.shard.integrate()
    #     await self.shard.trigger_reduction()
    #
    # async def call_players(self):
    #     await self.conference.add_participant(
    #         self.clavae_num,
    #         play_first=Clavae_Conference_Intro
    #     )
    #
    #     await self.conference.add_participant(
    #         self.karen_num,
    #         play_first=Karen_Conference_Info
    #     )
    #
    #     await trio.sleep(30)
    #
    #     await self.load_conference()
    #     if not self.conference.started:
    #         return await self.return_players()
    #
    #     await trio.sleep(60 * 5)
    #     await self.conference.play_sound(Conference_Nudge)

class DestroyTelemarketopia(Task):
    def __init__(self, clavae_num: PhoneNumber, karen_num: PhoneNumber):
        super(DestroyTelemarketopia, self).__init__()
        self.clavae_num = clavae_num
        self.karen_num = karen_num

    async def execute(self):
        self.d(f"DestroyTelemarketopia({self.clavae_num}, {self.karen_num}): Let's go!")
        await send_text(CFinalPuzzle1, self.clavae_num)
        await send_text(KFinalPuzzle1, self.karen_num)

        await send_text(CFinalPuzzle2, self.clavae_num)
        await send_text(KFinalPuzzle2, self.karen_num)

        conference = await new_conference(Global_Number_Library.from_label('final'))

        await conference.add_participant(self.clavae_num)

        await conference.add_participant(self.karen_num)

        clave_p = TelePlayer(self.clavae_num)
        karen_p = TelePlayer(self.karen_num)

        await clave_p.load()
        await karen_p.load()

        clave_p.telemarketopia[_in_final_final] = True
        karen_p.telemarketopia[_in_final_final] = True

        await clave_p.save()
        await karen_p.save()

class MakeClimaxCallsTask(Task):

    def __init__(self, clavae_num: PhoneNumber, clav_choice:str, karen_num:PhoneNumber, karen_choice:str):
        super(MakeClimaxCallsTask, self).__init__()
        self.clavae_num = clavae_num
        self.clav_choice = clav_choice
        self.karen_num = karen_num
        self.karen_choice = karen_choice

    @property
    def status_callback(self):
        return '/'.join([Root_Url, 'climax', self.clav_choice, self.karen_choice])

    @property
    def start_second_conference(self):
        return self.clav_choice == self.karen_choice == '3'

    async def execute(self):
        self.d(f"MakeClimaxCallsTask({self.clavae_num}({self.clav_choice}), {self.karen_num}({self.karen_choice}))!!")
        twilio_client: rest.Client = rest.Client(Credentials["twilio"]["sid"], Credentials["twilio"]["token"])
        from_number = Global_Number_Library.from_label("final")
        twilio_client.calls.create(
            url=self.status_callback,
            to=self.clavae_num.e164,
            from_=from_number.e164
        )

        twilio_client.calls.create(
            url=self.status_callback,
            to=self.karen_num.e164,
            from_=from_number.e164
        )

        if self.start_second_conference:
            await add_task(DestroyTelemarketopia(self.clavae_num, self.karen_num))


class SendFinalFinalResult(Task):
    def __init__(self, clavae_num: PhoneNumber, karen_num:PhoneNumber, got_right_answer: bool):
        super(SendFinalFinalResult, self).__init__()
        self.got_right_answer = got_right_answer
        self.clavae_num = clavae_num
        self.karen_num = karen_num

    async def execute(self):
        self.d(f"SendFinalFinalResult({self.clavae_num}, {self.karen_num}): !!!!!!!!!!!!!!!!!\n!!!!!!!!!!!!!!!!")
        twilio_client: rest.Client = rest.Client(Credentials["twilio"]["sid"], Credentials["twilio"]["token"])
        from_number = Global_Number_Library.from_label("final")

        path = f"{Root_Url}/finalclimax/wrong"
        if self.got_right_answer:
            path = f"{Root_Url}/finalclimax/right"

        twilio_client.calls.create(
            url=path,
            to=self.clavae_num.e164,
            from_=from_number.e164
        )

        twilio_client.calls.create(
            url=path,
            to=self.karen_num.e164,
            from_=from_number.e164
        )

class ConferenceChecker(TextHandler):

    async def first_conf_text(self, context: RoomContext, text_request: TwilRequest):
        self.d(f'new_text - player is agreeing to conf?')
        # only set if they are not yet in their first conference
        context.script[_ready_for_conf] = datetime.now().isoformat()

    async def first_conf_choice(self, context: RoomContext, text_request: TwilRequest):
        self.d(f'new_text(context, {text_request.text_body})')
        context.script[_player_final_choice] = text_request.text_body.strip()
        partner = TelePlayer(context.script[_partner])
        await partner.load()

        # check if we have a choice
        if partner.telemarketopia.get(_player_final_choice, False):
            if context.script[_path] == Path_Clavae:
                await add_task(
                    MakeClimaxCallsTask(text_request.caller,
                                        context.script[_player_final_choice],
                                        partner.number,
                                        partner.telemarketopia[_player_final_choice]
                                        )
                )
            else:
                await add_task(
                    MakeClimaxCallsTask(partner.number,
                                        partner.telemarketopia[_player_final_choice],
                                        text_request.caller,
                                        context.script[_player_final_choice]
                                        )
                )

    async def final_answer_text(self, context: RoomContext, text_request: TwilRequest):
        self.d(f'final answer? {text_request.text_body})')
        partner = PhoneNumber(context.script[_partner])
        await add_task(SendFinalFinalResult(
            text_request.caller,
            partner,
            text_request.text_body.strip() == '462'
        ))


    async def new_text(self, context: RoomContext, text_request: TwilRequest):
        self.d(f'new_text(context, {text_request.text_body})')
        if text_request.num_called == Global_Number_Library.from_label('conference'):
            if not context.script.get(_player_in_first_conference, False):
                await self.first_conf_text(context, text_request)

            if context.script.get(_has_decision_text):
                await self.first_conf_choice(context, text_request)

        elif text_request.num_called == Global_Number_Library.from_label('final'):
            await self.final_answer_text(context, text_request)
        else:
            self.w(f'Do not know what to do with: [From:{text_request.caller}] -> {text_request.num_called}: {text_request.text_body})')


# subclass to handle our specific needs around conferences
class ConferenceEventHandler(Logger):
    async def save_state_for_start(self, partipant: PhoneNumber, partner: PhoneNumber):
        player = TelePlayer(partipant.e164)
        await player.load()
        player.telemarketopia[_player_in_first_conference] = True
        player.telemarketopia[_partner] = partner.e164
        await player.save()

    async def event(self, conference:TwilConference, event: str, participant: str):
        # first conference
        if conference.from_number.e164 == Global_Number_Library.from_label('conference'):
            if event == 'conference-start':
                self.d(f"Conference with {conference.participants} started!")
                p1 = conference.participants[0]
                p2 = conference.participants[1]
                await self.save_state_for_start(p1, p2)
                await self.save_state_for_start(p2, p1)

            if event == 'conference-leave':
                player_left = TelePlayer(participant)
                await player_left.load()
                player_left.telemarketopia[_has_decision_text] = True
                if player_left.path == Path_Clavae:
                    await send_text(CPostConfOptions, PhoneNumber(participant))
                else:
                    await send_text(KPostConfOptions, PhoneNumber(participant))

                await player_left.save()

        return False


TwilConference._custom_handlers.append(ConferenceEventHandler())


class TipLineStart(TeleRoom):
    Name = "Tip Line Start"

    async def get_audio_for_room(self, context: RoomContext):
        # we need to select a path
        path = context.script.get(_path, None)
        print(f'context shard in first room: {context.shard}')
        if path is None:
            print(f'context shard in first room: {context.shard}')
            clavae_players = context.shard.get(_clavae_players)
            karen_players = context.shard.get(_karen_players)

            if len(clavae_players) <= len(karen_players):
                path = Path_Clavae
                context.shard.append(_clavae_players, context.player.number.e164)
            else:
                path = Path_Karen
                context.shard.append(_karen_players, context.player.number.e164)

            # set path!
            context.script[_path] = path

        return await self.get_resource_for_path(context)


class TipLineRecruit(TeleRoom):
    Name = "Tip Line Recruit"


class TipLineQuiz1(TeleRoom):
    Name = "Tip Line Quiz 1"


class TipLineQuiz2(TeleRoom):
    Name = "Tip Line Quiz 2"


class TipLineQuiz3(TeleRoom):
    Name = "Tip Line Quiz 3"


class TipLineQuizResults(TeleRoom):
    Name = "Tip Line Quiz Results"


class TipLineQuizOrientation(TeleRoom):
    Name = "Tip Line Quiz Orientation"


class TipLineKarenText(TeleRoom):
    Name = "Tip Line Karen Text"

    async def get_audio_for_room(self, context: RoomContext):
        await send_text(Karen1, context.player.number)
        return None


class TipLineTip1(TeleRoom):
    Name = "Tip Line Tip 1"


class TipLineTip2(TeleRoom):
    Name = "Tip Line Tip 2"


class TipLineClavae(TeleRoom):
    Name = "Tip Line Clavae"

    async def get_audio_for_room(self, context: RoomContext):
        await send_text(Clavae1, context.player.number)
        return None


class TipLineScene(PathScene):
    Name = "Telemarketopia Tip Line Scene"
    Start = [TipLineStart()]
    Choices = {
        TipLineStart(): {
            Path_Clavae: {
                '1': TipLineTip1(),
                '2': TipLineTip2(),
                '6': TipLineClavae(),
                '*': TipLineStart()
            },
            Path_Karen: {
                '1': TipLineTip1(),
                '2': TipLineTip2(),
                '5': TipLineRecruit(),
                '*': TipLineStart()
            }
        },
        TipLineRecruit() : {
            Path_Karen: {
                '5': TipLineQuiz1()
            }
        },
        TipLineQuiz1(): {
            Path_Karen: {
                '*': TipLineQuiz2()
            }
        },
        TipLineQuiz2(): {
            Path_Karen: {
                '*': TipLineQuiz3()
            }
        },
        TipLineQuiz3(): {
          Path_Karen: {
              '*': TipLineQuizResults()
          }
        },
        TipLineQuizResults(): {
            Path_Karen: {
                '*': TipLineQuizOrientation()
            }
        },
        TipLineQuizOrientation(): {
            Path_Karen: {
                '*': TipLineKarenText()
            }
        },
        TipLineTip1(): {
            '*': {
                '*': TipLineStart()
            }
        },
        TipLineTip2(): {
            '*': {
                '*': TipLineStart()
            }
        }
    }


class KarenInitiation(TeleRoom):
    Name = "Telemarketopia Initiation"


class KarenAccepted(TeleRoom):
    Name = "Accepted Initialaiton"
    Gather = False

    async def get_audio_for_room(self, context: RoomContext):
        await send_text(Karen2, context.player.number)
        return None


class TeleInitiation(PathScene):
    Name = "Karen Initiation"
    Start = [KarenInitiation(), KarenAccepted()]
    Choices = {}


class ClavaeAppeal(TeleRoom):
    Name = "First Clavae Appeal"


class ClavaeAccept(TeleRoom):
    Name = "First Clavae Accepted"

    async def get_audio_for_room(self, context: RoomContext):
        await send_text(Clavae2, context.player.number)
        return await self.get_resource_for_path(context)


class ClavaeAsksForHelp(PathScene):
    Name = "Clavae Asks For Help"
    Start = [ClavaeAppeal()]
    Choices = {
        ClavaeAppeal(): {
            Path_Clavae: {
                '1': ClavaeAccept(),
                '*': ClavaeAppeal()
            }
        }
    }

class DatabasePassword(TeleRoom):
    Name = "Database Password"
    Gather_Digits = 5


class DatabaseMenu(TeleRoom):
    Name = "Database Menu"


class DatabaseClassified(TeleRoom):
    Name = "Database Classified Files"


class DatabaseSecretMemo(TeleRoom):
    Name = "Database Secret Memo"


class DatabaseAIStart(TeleRoom):
    Name = "Database AI Start"


class DatabaseAINewArrivals(TeleRoom):
    Name = "Database AI New Arrivals"


class DatabaseAINewDepartures(TeleRoom):
    Name = "Database AI Departures"


class DatabaseAIThirdCall(TeleRoom):
    Name = "Database AI Third Call"

    async def get_audio_for_room(self, context: RoomContext):
        context.shard.append(_clav_waiting_for_conf, context.player.number.e164)
        await send_text(ConfWait, context.player.number)
        return await self.get_resource_for_path(context)


class DatabaseCorrupted(TeleRoom):
    Name = "Database File Corrupted"
    Gather = False


class Ghost(TeleRoom):
    Name = 'Ghost'
    Gather = False

    async def get_audio_for_room(self, context: RoomContext):
        return Puppet_Master


class Database(PathScene):
    Name = "Database"
    Start = [DatabasePassword()]
    Choices = {
        DatabasePassword(): {
            Path_Clavae: {
                '02501': [Ghost(), DatabasePassword()],
                '12610': DatabaseMenu(),
                '*': DatabasePassword()
            }
        },
        DatabaseMenu(): {
            Path_Clavae: {
                '1': DatabaseClassified(),
                '2': DatabaseSecretMemo(),
                '3': DatabaseAIStart(),
                '*': DatabaseMenu()
            }
        },
        DatabaseClassified(): {
            Path_Clavae: {
                '1': [DatabaseCorrupted(), DatabaseMenu()],
                '2': [DatabaseCorrupted(), DatabaseMenu()],
                '*': DatabaseMenu()
            }
        },
        DatabaseAIStart() : {
            Path_Clavae: {
                '1': DatabaseAINewArrivals(),
                '2': DatabaseAINewDepartures(),
                '*': DatabaseAIStart()
            }
        },
        DatabaseAINewArrivals(): {
            Path_Clavae: {
                '2': DatabaseAINewDepartures(),
                '*': DatabaseAIStart()
            }
        },
        DatabaseAINewDepartures(): {
            Path_Clavae: {
                '1': DatabaseAIThirdCall(),
                '*': DatabaseAINewDepartures()
            }
        }
    }

# name is INTENTIONALLY wrong
class TelemarketopiaPreOath(TeleRoom):
    Name = "Telemarketopia Oath"


# name is INTENTIONALLY wrong
class TelemarketopiOath(TeleRoom):
    Name = "Telemarketopia Promotion 1"


# name is INTENTIONALLY wrong
class TelemarketopiAcceptPromo(TeleRoom):
    Name = "Telemarketopia Accept Recruit"


class TelemarketopiQueueForConf(TeleRoom):
    Name = "Telemarketopia Karen Queue For Conf"

    async def get_audio_for_room(self, context: RoomContext):
        context.shard.append(_kar_waiting_for_conf, context.player.number.e164)
        await send_text(ConfWait, context.player.number)
        return await self.get_resource_for_path(context)


class TelemarketopiaPromotionScene(PathScene):
    Name = "Telemarketopia Promotion"
    Start = [TelemarketopiaPreOath()]
    Choices = {
        TelemarketopiaPreOath(): {
            Path_Karen: {
                '1': TelemarketopiOath(),
                '*': TelemarketopiaPreOath()
            }
        },
        TelemarketopiOath(): {
            Path_Karen: {
                '1': TelemarketopiAcceptPromo(),
                '*': TelemarketopiOath()
            }
        },
        TelemarketopiAcceptPromo(): {
            Path_Karen: {
                '1': TelemarketopiQueueForConf(),
                '*': TelemarketopiAcceptPromo()
            }
        },
    }


Path_Assigned = "State_Path_Assigned"
Second_Call_Done = "State_Second_Call_Done"
Third_Call_Done = "State_Waiting_For_Conference"

# todo: Put a function into Script that will handle texts that we get from twilio
# todo: Then we need a method of updating player state and also updating shared script state
# todo: Maybe we do this with one huge function that we run
# todo: Maybe we pass in an object that does it
# todo

class PleaseWaitRoom(TeleRoom):
    Name = "Please Wait Room"
    
    async def action(self, context: RoomContext):
        self.d(f"action() context: {context}")
        response = VoiceResponse()
        response.say("Thank you for expressing your interest in more Telemarketopia! You will get more Telemarketopia shortly.")

        return response

class PleaseWaitScene(PathScene):
    Name = "PleaseWaitScene"
    Start = [PleaseWaitRoom()]
    Choices = {}

PleaseWaitSceneAndState = SceneAndState(PleaseWaitScene(), Script_Ignore_Change)

telemarketopia = Script(
    Telemarketopia_Name,
    {
        Script_New_State: {
            "+18337594257": SceneAndState(TipLineScene(), Path_Assigned)
        },
        Path_Assigned: {
            # karen
            '+15102567656': SceneAndState(TeleInitiation(), Second_Call_Done),
            # clavae
            '+15102567710': SceneAndState(ClavaeAsksForHelp(), Second_Call_Done)
        },
        Second_Call_Done: {
            # karen
            "+15102567675": SceneAndState(TelemarketopiaPromotionScene(), Third_Call_Done),
            # clavae
            "+15102567705": SceneAndState(Database(), Third_Call_Done)
        },
        Third_Call_Done: {
            '+15102567710': PleaseWaitSceneAndState,
            '+15102567656': PleaseWaitSceneAndState,
            '+15102567705': PleaseWaitSceneAndState,
            '+15102567675': PleaseWaitSceneAndState
        }
    },
    TeleState(),
    text_handlers=[ConferenceChecker()]
)
