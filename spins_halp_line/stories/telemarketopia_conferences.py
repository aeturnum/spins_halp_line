from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional, Dict

import trio
from twilio import rest

from spins_halp_line.actions.conferences import TwilConference, new_conference
from spins_halp_line.actions.twilio import send_text
from spins_halp_line.constants import Root_Url, Credentials
from spins_halp_line.media.common import Conference_Nudge, Clavae_Conference_Intro, Karen_Conference_Info
from spins_halp_line.resources.numbers import PhoneNumber, Global_Number_Library
from spins_halp_line.stories.tele_constants import (
    Key_ready_for_conf,
    ConfUnReadyIfReply, ConfUnReadyIfNoReply, ConfReady, ConfReadyTwo,
    CFinalPuzzle1, KFinalPuzzle1, CFinalPuzzle2, KFinalPuzzle2
)
from spins_halp_line.stories.tele_story_objects import TeleShard, TelePlayer
from spins_halp_line.tasks import Task, add_task


#   _____             __                                    _             _
#  / ____|           / _|                                  | |           | |
# | |     ___  _ __ | |_ ___ _ __ ___ _ __   ___ ___       | |_   _ _ __ | | __
# | |    / _ \| '_ \|  _/ _ \ '__/ _ \ '_ \ / __/ _ \  _   | | | | | '_ \| |/ /
# | |___| (_) | | | | ||  __/ | |  __/ | | | (_|  __/ | |__| | |_| | | | |   <
#  \_____\___/|_| |_|_| \___|_|  \___|_| |_|\___\___|  \____/ \__,_|_| |_|_|\_\


# Create object that:
# - can load player script objects and then save them again when neede
# - can load the shared state
# - can send changes to the script shared state

class StoryInfo:

    def __init__(self, clavae_player: str, karen_player: str, shard: TeleShard):
        self.clv_p: TelePlayer = TelePlayer(clavae_player)
        self.kar_p: TelePlayer = TelePlayer(karen_player)
        self.shard = shard
        self._loaded = False

    async def load(self):
        if not self._loaded:
            await self.clv_p.load()
            await self.kar_p.load()
            self._loaded = True

    async def save(self):
        await self.clv_p.save()
        await self.kar_p.save()

    @property
    def c_num(self) -> PhoneNumber:
        return self.clv_p.number

    @property
    def k_num(self) -> PhoneNumber:
        return self.kar_p.number

    def __str__(self):
        return f'SI[{self.clv_p},{self.kar_p}]'


class ConferenceTask(Task):
    def __init__(self, info: StoryInfo, delay: int = 0, conf: TwilConference = None):
        super(ConferenceTask, self).__init__(delay)
        self.info = info
        self.conference: Optional[TwilConference] = conf

    async def refresh_players(self):
        await self.info.load()
        await self.info.clv_p.load()
        await self.info.kar_p.load()

    async def check_player_status(self):
        await self.refresh_players()
        # self.d(f'check_player_status({self.info})')
        # cheeck to make sure we've seen them within last 10 mins
        time_limit = timedelta(minutes=10)

        clavae_time_passed = self.info.clv_p.time_passed(Key_ready_for_conf)
        karen_time_passed = self.info.kar_p.time_passed(Key_ready_for_conf)

        # self.d(f'check_player_status({self.info}) -> {clavae_ready}, {karen_ready}')
        return clavae_time_passed < time_limit, karen_time_passed < time_limit

    @staticmethod
    async def start_child_task(task):
        await add_task.send(task)

    async def execute(self):
        await self.info.load()
        await self.execute_conference_action()

    async def execute_conference_action(self):
        pass

    async def start_conference(self, clav_media=None, karen_media=None):
        from_number = Global_Number_Library.from_label('conference')
        self.conference = await new_conference(from_number)

        self.d(f"ConfWaitForPlayers({self.info}): Starting conference")
        await self.conference.add_participant(
            self.info.c_num,
            play_first=clav_media,

        )

        await self.conference.add_participant(
            self.info.k_num,
            play_first=karen_media
        )

    def __str__(self):
        return f"{self.__class__.__name__}[{self.info}]"


class ReturnPlayers(ConferenceTask):

    async def unready_text(self, ready: bool, number: PhoneNumber):
        cls = ConfUnReadyIfReply
        if not ready:
            cls = ConfUnReadyIfNoReply
        self.d(f'unready_text({ready}, {number}): {cls}')
        await send_text(cls, number)

    async def execute_conference_action(self):
        self.d(f'e_c_a():')
        c_r, k_r = await self.check_player_status()
        # Put back into queue, but put them at the back of the queue if they didn't reply
        self.d(f'{self.info}] Trying to stop Conf {self.conference}')
        if self.conference:
            await self.conference.stop()

        self.d(f'e_c_a(): registering moves')
        self.d(f'e_c_a(): registering moves: {self.info.shard.clavae_in_conf=}, {self.info.c_num=}')
        if self.info.c_num.e164 in self.info.shard.clavae_in_conf:
            self.info.shard.move(
                "clavae_in_conf",
                "clavae_waiting_for_conf",
                self.info.c_num.e164,
                to_front=c_r)

        if self.info.k_num.e164 in self.info.shard.karen_in_conf:
            self.info.shard.move(
                "karen_in_conf",
                "karen_waiting_for_conf",
                self.info.k_num.e164,
                to_front=k_r)

        # remove info the players got the text
        await self.info.clv_p.reset_conference_flags()
        await self.info.kar_p.reset_conference_flags()

        self.d(f'e_c_a(): sending texts')
        # Text player to let them know the conference is off
        await self.unready_text(c_r, self.info.c_num)
        await self.unready_text(k_r, self.info.k_num)

        self.d(f'e_c_a(): queueing update')
        # Eventually put players back in queue
        await self.info.shard.queue_state_update()


class ConnectFirstConference(ConferenceTask):
    _sleep_time = 60 * 3

    async def execute_conference_action(self):
        self.d(f"e_c_a(): Sleeping for {self._sleep_time}s")
        # todo: apparently twilio only sends the conference-join event after the user listens to the audio
        # todo: and stays on the line, so this should adjust depending on the length of the
        # todo: audio pre-roll we're using.

        # todo: to be clear, this means that the player can pick up the call and we will *not*
        # todo: get a notification until they have finished listening to the audio on that call.
        await trio.sleep(self._sleep_time)
        self.d(f"e_c_a(): Checking if players connected...")

        if not self.conference.started:
            # todo: end conference through twilio conference interface here
            self.d(f"e_c_a(): Someone didn't pick up, returning")
            return await add_task.send(ReturnPlayers(self.info))

        await trio.sleep(60 * 5)
        if self.conference.is_active > 1:
            await self.conference.play_sound(Conference_Nudge)


class ConfWaitForPlayers(ConferenceTask):
    _wait_before_retext = 60 * 5
    _wait_before_give_up = 60 * 10

    @dataclass
    class ConfWaitForPlayersState:
        time_elapsed: int = 0
        text_counts: Dict[str, int] = field(default_factory=dict)  # the only field exposed to Rooms

    def __init__(self, info: StoryInfo, delay: int = 0, ongoing_state: ConfWaitForPlayersState = None):
        super(ConfWaitForPlayers, self).__init__(info, delay)
        if ongoing_state is None:
            ongoing_state = self.ConfWaitForPlayersState(0, {info.k_num.e164: 1, info.c_num.e164: 1})
        self.state: ConfWaitForPlayers.ConfWaitForPlayersState = ongoing_state
        self.state.time_elapsed += delay

    async def maybe_send_text(self, ready: bool, number: PhoneNumber):
        text_count = self.state.text_counts[number.e164]
        if not ready and self.state.time_elapsed > self._wait_before_retext and text_count == 1:
            self.d(f'Re-texting player {number} as we have not heard from them yet...')
            await send_text(ConfReadyTwo, number)
            self.state.text_counts[number.e164] += 1

    async def execute_conference_action(self):
        self.d(f"e_c_a(): {self.state.time_elapsed}s elapsed!")
        c_r, k_r = await self.check_player_status()
        await self.maybe_send_text(c_r, self.info.c_num)
        await self.maybe_send_text(k_r, self.info.k_num)

        self.d(f"e_c_a(): {c_r=}, {k_r=}!")
        if not c_r or not k_r:
            self.d(f"e_c_a(): someone isn't ready!")
            if self.state.time_elapsed < self._wait_before_give_up:
                # wait another 15 seconds and check again
                task_to_start = ConfWaitForPlayers(self.info, 15, self.state)
            else:
                self.d(f"e_c_a(): Aborting both!")
                # put people back in the queue
                task_to_start = ReturnPlayers(self.info)
        else:
            self.d(f"e_c_a(): Starting conference!!")
            await self.start_conference(
                clav_media=Clavae_Conference_Intro,
                karen_media=Karen_Conference_Info
            )
            task_to_start = ConnectFirstConference(self.info, conf=self.conference)

        return await self.start_child_task(task_to_start)


class ConfStartFirst(ConferenceTask):
    async def execute_conference_action(self):
        self.d(f"ConfStartFirst({self.info})")

        # remove info the players got the text
        # clear
        await self.info.clv_p.reset_conference_flags()
        await self.info.kar_p.reset_conference_flags()

        self.d(f"ConfStartFirst({self.info}): cleared old flags")
        await send_text(ConfReady, self.info.c_num)
        await send_text(ConfReady, self.info.k_num)

        self.d(f"ConfStartFirst({self.info}): Sent text")
        # wait 30s
        wait_task = ConfWaitForPlayers(self.info, delay=30)
        await self.start_child_task(wait_task)


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

        clave_p.in_final_conference = True
        karen_p.in_final_conference = True

        await clave_p.save()
        await karen_p.save()


class MakeClimaxCallsTask(Task):

    def __init__(self, clavae_num: PhoneNumber, clav_choice: str, karen_num: PhoneNumber, karen_choice: str):
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
            await add_task.send(DestroyTelemarketopia(self.clavae_num, self.karen_num))


class SendFinalFinalResult(Task):
    def __init__(self, clavae_num: PhoneNumber, karen_num: PhoneNumber, got_right_answer: bool):
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
