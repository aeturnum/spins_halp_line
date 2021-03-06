import json
from datetime import datetime
from typing import List, Optional, Dict

import trio
from twilio.twiml.voice_response import VoiceResponse, Dial, Play
from twilio.rest.api.v2010.account.conference import ConferenceInstance

from spins_halp_line.constants import Root_Url
from spins_halp_line.media.common import Conference_Hold_Music
from spins_halp_line.media.resource_space import RSResource
from spins_halp_line.resources.numbers import PhoneNumber
from spins_halp_line.resources.redis import new_redis
from spins_halp_line.util import Logger, LockManager
from spins_halp_line.actions.twilio import (
    _twilio_client,
    _twil_lock
)

_last_conference = 0

_conference_lock = trio.Lock()
# I get why we use strings of object names that haven't been defined yet but like my god
_conferences: List['TwilConference'] = []
# This exists because we need to keep track of conferences and how they are progressing

_conference_key = "spins_conference_list"

Conf_Twiml_Path = "/conf/twiml/<c_number>"
Conf_Status_Path = "/conf/status/<c_number>"


class TwilConference(Logger):
    Event_Conference_Start = 'conference-start'
    Event_Participant_Join = 'participant-join'
    Event_Participant_Leave = 'participant-leave'

    Status_Invited = 'invited'
    Status_Active = 'active'
    Status_Left = 'left'

    _callbacks = " ".join(['start', 'end', 'leave', 'join'])
    _custom_handlers = []

    # This function does not use the global conference lock because trio locks are not reentrant and
    # in theory that should be fine? We should only call this once a lock is established and EVEN IF WE DON'T,
    # it will not be a problem because this is writing to the persistent database and those writes should be
    # ordered by redio
    @classmethod
    async def _save_conference_list(cls, locked=False):
        # global _conferences
        # global _conference_lock
        db = new_redis()
        async with LockManager(_conference_lock, locked):
            await db.set(_conference_key, json.dumps([c.to_redis() for c in _conferences]))  # list of dict

    @classmethod
    async def from_redis(cls, saved_data, locked=False):
        # global _conference_lock
        global _last_conference

        async with LockManager(_conference_lock, locked):
            int_id = int(saved_data['id'])
            if int_id > _last_conference:
                # keep up gid as conference increases
                _last_conference = int_id

            participants = saved_data.get('participants', {})
            from_num = saved_data.get('from')
            sid = saved_data.get('sid', "")
            started = saved_data.get('started', None)
            if started:
                started = datetime.fromisoformat(started)

            return TwilConference(int_id, from_num, participants, sid, started)

    @classmethod
    async def create(cls, number: PhoneNumber, locked=None) -> 'TwilConference':
        # global _conference_lock
        global _last_conference

        async with LockManager(_conference_lock, locked):
            new_id = _last_conference + 1
            _last_conference = new_id

            return TwilConference(new_id, number)

    def __init__(self, id_, from_number: PhoneNumber, participants=None, sid=None, started=None):
        super(TwilConference, self).__init__()
        if not participants:
            participants = {}

        if not sid:
            sid = ""

        self.id: int = id_
        self.from_number = from_number
        # This is the real thing we need to make changes
        # We should get it on callback
        self.twil_sid: str = sid
        self._participating: Dict[str, str] = participants
        self.intros: Dict[str, int] = {}
        self.started: Optional[datetime] = started

    @property
    def is_active(self) -> bool:
        return len(self.active) > 1

    @property
    def active(self) -> List[PhoneNumber]:
        return [PhoneNumber(p) for p, v in self._participating.items() if v == self.Status_Active]

    @property
    def invited(self) -> List[PhoneNumber]:
        return [PhoneNumber(p) for p, v in self._participating.items() if v == self.Status_Invited]

    @property
    def left(self) -> List[PhoneNumber]:
        return [PhoneNumber(p) for p, v in self._participating.items() if v == self.Status_Left]

    @property
    def participating(self) -> List[PhoneNumber]:
        return [PhoneNumber(p) for p, v in self._participating.items()]

    @property
    def status_callback(self):
        return '/'.join([Root_Url, 'conf', 'status', str(self.id)])

    @property
    def twiml_callback(self):
        return '/'.join([Root_Url, 'conf', 'twiml', str(self.id)])

    def __eq__(self, other):
        if isinstance(other, TwilConference):
            return self.id == other.id
        elif isinstance(other, str):
            try:
                return self.id == int(other)
            except ValueError:
                # fall out to default
                pass
        elif isinstance(other, int):
            return self.id == other

        return False

    def to_redis(self):
        started = ""
        if self.started:
            started = self.started.isoformat()
        return {
            'id': self.id,
            'from': self.from_number.e164,
            'participants': self._participating,
            'sid': self.twil_sid,
            'started': started,
            'intros': json.dumps(self.intros)
        }

    def __str__(self):
        return f'Conf[{self.from_number}|A:{self.active}]'

    # Headers:
    #   [...]
    # Body:
    #   Coaching: false
    #   FriendlyName: 2
    #   ParticipantLabel: +14156864014
    #   EndConferenceOnExit: false
    #   StatusCallbackEvent: participant-leave
    #   Timestamp: Thu, 14 Jan 2021 00:25:05 +0000
    #   StartConferenceOnEnter: true
    #   AccountSid: AC7196e8082e73460f6c5c961109940e6d
    #   SequenceNumber: 1
    #   ConferenceSid: CF68a65a63fd20c14069a0ec784858ecb0
    #   CallSid: CA3dbed34340ac3d3f530a3d72468d91fb
    #   Hold: false
    #   Muted: false

    # events:
    # last-participant-left: conference over
    # participant-leave: someone left
    # conference-start: both people are in
    async def handle_conf_event(self, body) -> str:

        async with LockManager(_conference_lock):
            dirty = False

            participant = body.get('ParticipantLabel')
            event_name = body.get('StatusCallbackEvent')
            conf_sid = body.get('ConferenceSid')

            if participant:
                self.d(f'{participant} triggered an {event_name} event!')
            else:
                self.d(f'{event_name} event was triggered!')

            if not self.twil_sid:
                self.twil_sid = conf_sid
                dirty = True

            if participant and participant not in self.invited:
                # add a participant when we first see them in a callback
                self.invited.append(PhoneNumber(participant))
                dirty = True

            if event_name == self.Event_Conference_Start:  # conference start, mark time
                self.started = datetime.now()
                dirty = True

            if event_name == self.Event_Participant_Join:  # conference start, mark time
                self._participating[participant] = self.Status_Active
                dirty = True

            if event_name == self.Event_Participant_Leave:  # conference start, mark time
                self._participating[participant] = self.Status_Left
                dirty = True

            handlers_made_changes = await self.do_handle_event(event_name, participant)
            if handlers_made_changes:
                dirty = True

            if dirty:
                await self._save_conference_list(True)

        return ""

    async def stop(self):
        async with LockManager(_twil_lock):
            if self.twil_sid and len(self.active) > 1:
                self.d(f"stop(): Stopping {self.twil_sid}")
                _twilio_client.conferences(self.twil_sid).update(status=ConferenceInstance.Status.COMPLETED)
            else:
                self.d("stop(): Have not gotten SID yet, can't stop")

    # Override this to do custom event handling
    async def do_handle_event(self, event, participant):
        self.d(f'Calling custom Conference handlers for {event}!')
        for handler in self._custom_handlers:
            await handler.event(self, event, participant)

    async def add_participant(self, number_to_call: PhoneNumber, play_first: RSResource = None):

        # todo: figure out this whole async machine detection business
        async with LockManager(_twil_lock):
            _twilio_client.calls.create(
                # machine_detection='Enable',
                # async_amd='true',
                # async_amd_status_callback='',
                url=self.twiml_callback,
                to=number_to_call.e164,
                from_=self.from_number.e164
            )

        async with LockManager(_conference_lock):
            self._participating[number_to_call.e164] = self.Status_Invited
            self.intros[number_to_call.e164] = play_first.id
            await self._save_conference_list(True)

    async def play_sound(self, sound: RSResource):
        if not self.twil_sid:
            return

        await sound.load()

        async with LockManager(_twil_lock):
            _twilio_client.conferences(self.twil_sid).update(announce_url=sound.url)

    async def twiml_xml(self, number_calling: PhoneNumber) -> VoiceResponse:
        response = VoiceResponse()
        if number_calling.e164 in self.intros:
            resource = RSResource(self.intros[number_calling.e164])
            # hopefully these requests will be cached
            await resource.load()
            play = Play(resource.url, loop=1)
            response.append(play)
            async with LockManager(_conference_lock):
                # clear flag
                del self.intros[number_calling.e164]
                await self._save_conference_list(True)

        dial = Dial()
        self.d(f'Returning conference xml. Hold music url: {Conference_Hold_Music.url}')
        dial.conference(
            f'{self.id}',
            status_callback_event=self._callbacks,
            status_callback=self.status_callback,
            wait_url=Conference_Hold_Music.url,
            # This argument is not documented in the SDK, but it does work in the generated XML
            participant_label=number_calling.e164
        )
        response.append(dial)

        return response


async def new_conference(number: PhoneNumber) -> TwilConference:
    # global _conferences
    # global _conference_lock

    # will lock and unlock
    new_conf = await TwilConference.create(number)

    async with LockManager(_conference_lock):
        _conferences.append(new_conf)
        await TwilConference._save_conference_list(True)

    return new_conf


async def load_conferences():
    async with LockManager(_conference_lock):
        db = new_redis()
        confs = await db.get(_conference_key).autodecode  # list of dict
        if confs:
            _conferences = [(await TwilConference.from_redis(conf_data, locked=True)) for conf_data in confs]


def conferences() -> List[TwilConference]:
    # global _conferences

    return _conferences
