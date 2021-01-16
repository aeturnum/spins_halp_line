from typing import Dict, Union, List

from twilio.twiml.voice_response import VoiceResponse, Play, Gather, Hangup
from twilio.base import values
import trio

from .story_objects import (
    Room,
    Scene,
    Script,
    SceneAndState,
    RoomContext,
    ScriptState,
    ScriptInfo,
    StateShard
)

from spins_halp_line.actions.conferences import new_conference, conferences
from spins_halp_line.actions.twilio import send_sms
from spins_halp_line.tasks import add_task, Task
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from spins_halp_line.media.common import (
    Karen_Puzzle_Image_1,
    Clavae_Puzzle_Image_1,
    Telemarketopia_Logo,
    Puppet_Master,
    Clavae_Conference_Intro,
    Karen_Conference_Info
)
from spins_halp_line.twil import TwilRequest
from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.actions.conferences import TwilConference
from spins_halp_line.constants import (
    Script_New_State,
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
    Text = "Once you fill this in, this puzzle should give you a five-digit code to get into the database.\n - Clavae"
    From_Number_Label = 'clavae_2'
    Image = Clavae_Puzzle_Image_1

class Karen1(TextTask):
    Text = "Solving this puzzle will give you the next phone number to call and prove you're Telemarketopia material!"
    From_Number_Label = 'karen_1'
    Image = Karen_Puzzle_Image_1

class Karen2(TextTask):
    Text = "Please call +1-510-256-7751 to continue learning about the exciting opportunities you'll have at Telemarketopia!"
    From_Number_Label = 'karen_2'
    Image = Telemarketopia_Logo

class ConfWait(TextTask):
    Text = "Our systems are working on bisecting the quantum lagrange points, we'll connect you as soon as we can!"
    From_Number_Label = 'conference'
    Image = Telemarketopia_Logo


async def send_text(TextClass, player_numer: PhoneNumber, delay=0):
    await add_task.send(TextClass(player_numer, delay))


#   _____           _       _      _____ _                        _    _____ _        _
#  / ____|         (_)     | |    / ____| |                      | |  / ____| |      | |
# | (___   ___ _ __ _ _ __ | |_  | (___ | |__   __ _ _ __ ___  __| | | (___ | |_ __ _| |_ ___
#  \___ \ / __| '__| | '_ \| __|  \___ \| '_ \ / _` | '__/ _ \/ _` |  \___ \| __/ _` | __/ _ \
#  ____) | (__| |  | | |_) | |_   ____) | | | | (_| | | |  __/ (_| |  ____) | || (_| | ||  __/
# |_____/ \___|_|  |_| .__/ \__| |_____/|_| |_|\__,_|_|  \___|\__,_| |_____/ \__\__,_|\__\___|
#                    | |
#                    |_|


# subclass to handle our specific needs around conferences
class TeleConference(TwilConference):

    def do_create(self, new_id):
        return TeleConference(new_id)

    # do the things we need to do once players leave the conference
    async def do_handle_event(self, event, participant):

        return False

class ConferenceTask(Task):
    def __init__(self, clavae_player: str, karen_player: str, shard: StateShard):
        super(ConferenceTask, self).__init__(0)
        self.clavae = clavae_player
        self.karen = karen_player
        self.shard = shard
        self.conference = None

    async def load_conference(self):
        if not self.conference:
            self.conference = await new_conference(TeleConference)
            return self.conference

        for conf in conferences():
            if conf == self.conference:
                # this *should* not matter but I am past dealing with instance fuckary
                return conf

    async def execute(self):
        conference = await new_conference(TeleConference)
        from_number = Global_Number_Library.from_label('conference')
        clavae_num = PhoneNumber(self.clavae)
        karen_num = PhoneNumber(self.karen)

        while True:
            # todo: add task to text players and see if they are ready

            # todo: also need a way to trigger the reduce loop from a task so we can re-match
            # todo: players without a new person calling

            await trio.sleep(60 * 5)

            await conference.add_participant(
                from_number,
                clavae_num,
                play_first=Clavae_Conference_Intro
            )

            await conference.add_participant(
                from_number,
                karen_num,
                play_first=Karen_Conference_Info
            )

            await trio.sleep(30)

# paths
Path_Clavae = 'Clavae'
Path_Karen = 'Karen'

# state
_clavae_players = 'clave_players'
_karen_players = 'karen_players'
_clav_waiting_for_conf = 'clave_play_waiting_for_conf'
_kar_waiting_for_conf = 'karen_play_waiting_for_conf'
_pair_waiting_for_2nd_conf = 'karen_clave_players_last_conf'

class TeleState(ScriptState):

    def __init__(self):
        super(TeleState, self).__init__(
            {
                _clavae_players: [],
                _karen_players: [],
                _clav_waiting_for_conf: [],
                _kar_waiting_for_conf: [],
                _pair_waiting_for_2nd_conf: [],
            }
        )

    @staticmethod
    async def do_reduce(state: dict, shard: StateShard):
        # todo: think about doing something about how recently players have been active?
        # todo: players who have been out for a while might not want to play

        clave_waiting = state.get(_clav_waiting_for_conf)
        karen_waiting = state.get(_kar_waiting_for_conf)
        if len(clave_waiting) > 1 and len(karen_waiting) > 1:
            # conference time baby!
            await add_task.send(
                ConferenceTask(
                    state[_clav_waiting_for_conf].pop(0),
                    state[_kar_waiting_for_conf].pop(0),
                    shard
                )
            )

        return state

class TipLineStart(TeleRoom):
    Name = "Tip Line Start"

    async def get_audio_for_room(self, context: RoomContext):
        # we need to select a path
        path = context.script.get('path', None)
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
            context.script['path'] = path

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
        context.shard.append(_clav_waiting_for_conf, context.player.number)
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
        context.shard.append(_kar_waiting_for_conf, context.player.number)
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
Third_Call_Done = "State_Second_Call_Done"

# todo: Put a function into Script that will handle texts that we get from twilio
# todo: Then we need a method of updating player state and also updating shared script state
# todo: Maybe we do this with one huge function that we run
# todo: Maybe we pass in an object that does it
# todo

telemarketopia = Script(
    "Telemarketopia",
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
        }
    },
    TeleState()
)