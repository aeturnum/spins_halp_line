from typing import Set, List
from datetime import datetime

from twilio.twiml.voice_response import VoiceResponse

from .tele_constants import (
    Telemarketopia_Name,
    _ready_for_conf,
    _player_in_first_conference,
    _has_decision_text,
    _path,
    _partner,
    _player_final_choice,
    Path_Clavae, Path_Karen,
    Clavae1, Clavae2,
    Karen1, Karen2,
    ConfWait,
    KPostConfOptions, CPostConfOptions
)
from .tele_story_objects import TeleRoom, PathScene, TelePlayer, TeleShard, TeleState
from .story_objects import (
    Script,
    SceneAndState,
    RoomContext,
    ScriptStateManager,
    ScriptInfo,
    TextHandler
)


from spins_halp_line.util import Logger, LockManager
from spins_halp_line.tasks import add_task
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from spins_halp_line.media.common import (
    Puppet_Master
)
from .telemarketopia_conferences import ConfStartFirst, MakeClimaxCallsTask, SendFinalFinalResult, StoryInfo
from ..actions.twilio import send_text
from spins_halp_line.twil import TwilRequest
from spins_halp_line.actions.conferences import TwilConference
from spins_halp_line.constants import (
    Script_New_State,
    Script_Ignore_Change
)



class ConferenceChecker(TextHandler):

    async def first_conf_text(self, text_request: TwilRequest, shard: TeleShard, script_info: ScriptInfo):
        self.d(f'new_text({text_request.caller}) - player is agreeing to conf?')
        # only set if they are not yet in their first conference
        TelePlayer.record_timestamp(script_info.data, _ready_for_conf)
        return script_info

    async def first_conf_choice(self, text_request: TwilRequest, shard: TeleShard, script_info: ScriptInfo):
        self.d(f'new_text({text_request.caller}, {text_request.text_body})')
        script_info.data[_player_final_choice] = text_request.text_body.strip()
        partner = TelePlayer(script_info.data[_partner])
        await partner.load()

        # check if we have a choice
        if partner.telemarketopia.get(_player_final_choice, False):
            if script_info.data[_path] == Path_Clavae:
                await add_task.send(
                    MakeClimaxCallsTask(text_request.caller,
                                        script_info.data[_player_final_choice],
                                        partner.number,
                                        partner.telemarketopia[_player_final_choice]
                                        )
                )
            else:
                await add_task.send(
                    MakeClimaxCallsTask(partner.number,
                                        partner.telemarketopia[_player_final_choice],
                                        text_request.caller,
                                        script_info.data[_player_final_choice]
                                        )
                )

        return script_info

    async def final_answer_text(self, text_request: TwilRequest, shard: TeleShard, script_info: ScriptInfo):
        self.d(f'text[{text_request.caller}] final answer? {text_request.text_body})')
        partner = PhoneNumber(script_info.data[_partner])
        await add_task.send(SendFinalFinalResult(
            text_request.caller,
            partner,
            text_request.text_body.strip() == '462'
        ))

        return script_info

    async def new_text(self, text_request: TwilRequest, shard: TeleShard, script_info: ScriptInfo):
        self.d(f'new_text({text_request.caller}, {text_request.text_body})')
        if text_request.num_called == Global_Number_Library.from_label('conference'):
            if not script_info.data.get(_player_in_first_conference, False):
                return await self.first_conf_text(text_request, shard, script_info)

            if script_info.data.get(_has_decision_text):
                return await self.first_conf_choice(text_request, shard, script_info)

        elif text_request.num_called == Global_Number_Library.from_label('final'):
            return await self.final_answer_text(text_request, shard, script_info)
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
        self.d(f"Got coference event: {conference}:{event}!")
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


class TeleStateManager(ScriptStateManager):

    def _make_new_state(self, base: dict = None) -> TeleState:
        if not base:
            base = {}
        return TeleState(**base)

    def _make_shard(self) -> TeleShard:
        d = self._state_dict
        d.pop('version', None) # remove version
        d.pop('generation', None)  # remove version
        ts = TeleShard(**d)
        ts.set_parent(self)

        return ts

    def filter_list(self, player_list: List, player_set: Set):
        result = []
        added = set()

        # updated to both:
        # only add players who are on the whitelist
        # and also only add them once to each list
        for p in player_list:
            if p not in added and p in player_set:
                added.add(p)
                result.append(p)

        return result

    def remove_dupes(self, player_list, player_set = None):
        if not player_set:
            player_set = set()
        clean_list = []

        for player in player_list:
            if player not in player_set:
                player_set.add(player)
                clean_list.append(player)

        return {
            'set': player_set,
            'list': clean_list
        }

    async def on_startup(self):
        self.d('on_startup()')
        async with LockManager(self._lock):
            state: TeleState = self._state

            # Don't try to recover state from conferences, just return them back to the wait list
            self.d(f'on_startup(): Returning players in conference to waiting state')
            self.d(f'on_startup(): {state.clavae_in_conf}')
            self.d(f'on_startup(): {state.karen_in_conf}')
            self.d(f'on_startup(): >>>>>>>>')
            self.d(f'on_startup(): {state.clavae_waiting_for_conf}')
            self.d(f'on_startup(): {state.karen_waiting_for_conf}')
            self.d(f'on_startup(): ----------------------------')
            state.clavae_waiting_for_conf.extend(state.clavae_in_conf)
            state.karen_waiting_for_conf.extend(state.karen_in_conf)
            state.clavae_in_conf = []
            state.karen_in_conf = []
            # move remove people who have been moved back

            self.d(f'on_startup(): Removing dupes')
            self.d(f'on_startup(): {state.clavae_players}')
            self.d(f'on_startup(): {state.karen_players}')
            clav_uniques = self.remove_dupes(state.clavae_players)
            kare_uniques = self.remove_dupes(state.karen_players)

            # find intersection
            shared_players = clav_uniques['set'].intersection(kare_uniques['set'])
            if shared_players:
                self.d(f'shared: {shared_players}')
                for shared_player in shared_players:
                    # nuke it from orbit
                    clav_uniques['set'].remove(shared_player)
                    kare_uniques['set'].remove(shared_player)
                    clav_uniques['list'].remove(shared_player)
                    kare_uniques['list'].remove(shared_player)
                    # also delete player state
                    await TelePlayer.reset(shared_player)

            # now filter all lists
            state.clavae_players = clav_uniques['list']
            state.karen_players = kare_uniques['list']

            clav_set = clav_uniques['set']
            state.clavae_waiting_for_conf = self.filter_list(state.clavae_waiting_for_conf, clav_set)
            state.clavae_final_conf = self.filter_list(state.clavae_final_conf, clav_set)

            kare_set = kare_uniques['set']
            state.karen_waiting_for_conf = self.filter_list(state.karen_waiting_for_conf, kare_set)
            state.karen_final_conf = self.filter_list(state.karen_final_conf, kare_set)
            self.d(f'on_startup(): >>>>>>>>')
            self.d(f'on_startup(): {state.clavae_players}')
            self.d(f'on_startup(): {state.karen_players}')

            await self.save_to_redis(True)


    async def do_reduce(self, state: TeleState, shard: TeleShard):
        # todo: think about doing something about how recently players have been active?
        # todo: players who have been out for a while might not want to play

        self.d('do_reduce()')
        self.d(f'do_reduce():{state}')

        clave_waiting = state.clavae_waiting_for_conf
        karen_waiting = state.karen_waiting_for_conf

        self.d(f'clav_waiting:{clave_waiting}({len(clave_waiting)})')
        self.d(f'karen_waiting:{karen_waiting}({len(karen_waiting)})')
        if len(clave_waiting) >= 1 and len(karen_waiting) >= 1:
            # conference time baby!
            clav_p = state.clavae_waiting_for_conf.pop(0)
            karen_p = state.karen_waiting_for_conf.pop(0)
            self.d(f'Starting conf with {[clav_p, karen_p]}')
            state.clavae_in_conf.append(clav_p)
            state.karen_in_conf.append(karen_p)

            await add_task.send(
                ConfStartFirst(
                    StoryInfo(clav_p, karen_p, shard)
                )
            )

        return state


    def __str__(self):
        return f'TeleSM'

class TipLineStart(TeleRoom):
    Name = "Tip Line Start"

    async def get_audio_for_room(self, context: RoomContext):
        # we need to select a path
        path = context.script.get(_path, None)
        print(f'context shard in first room: {context.shard}')
        if path is None:
            shard: TeleShard = context.shard
            print(f'context shard in first room: {context.shard}')
            clavae_players = shard.clavae_players
            karen_players = shard.karen_players

            if len(clavae_players) <= len(karen_players):
                path = Path_Clavae
                shard.append('clavae_players', context.player.number.e164)
            else:
                path = Path_Karen
                shard.append('karen_players', context.player.number.e164)

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
        context.shard.append('clave_waiting_for_conf', context.player.number.e164)
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
        context.shard.append('karen_waiting_for_conf', context.player.number.e164)
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
    TeleStateManager(),
    text_handlers=[ConferenceChecker()]
)

telemarketopia.add_script(telemarketopia)