import json
from typing import List, Union, Optional
from datetime import datetime

import trio
from twilio import rest
from twilio.twiml.voice_response import Conference, Dial, VoiceResponse
# from greenletio import async_
# from trio_asyncio import aio_as_trio
from twilio.base import values

from ..constants import Credentials, Root_Url
from spins_halp_line.resources.redis import new_redis
from spins_halp_line.media.common import Conference_Hold_Music
from spins_halp_line.util import LockManager, Logger
from ..resources.numbers import PhoneNumber

_twilio_client: rest.Client = rest.Client(Credentials["twilio"]["sid"], Credentials["twilio"]["token"])
_twil_lock = trio.Lock()
_conference_lock = trio.Lock()
# I get why we use strings of object names that haven't been defined yet but like my god
_conferences: List['TwilConference'] = []
_last_conference = 0

_conference_key = "spins_conference_list"

Conf_Twiml_Path = "/conf/twiml/<c_number>"
Conf_Status_Path = "/conf/status/<c_number>"


# This exists because we need to keep track of conferences and how they are progressing
class TwilConference(Logger):

    _callbacks = " ".join(['start', 'end', 'leave', 'join'])

    @classmethod
    async def _load_conferences(cls, locked=False):
        global _conferences
        global _conference_lock

        async with LockManager(_conference_lock, locked):
            db = new_redis()
            confs = await db.get(_conference_key).autodecode  # list of dict
            _conferences = [(await cls.from_redis(conf_data, locked=True)) for conf_data in confs]

    # This function does not use the global conference lock because trio locks are not reentrant and
    # in theory that should be fine? We should only call this once a lock is established and EVEN IF WE DON'T,
    # it will not be a problem because this is writing to the persistant database and those writes should be
    # ordered by redio
    @classmethod
    async def _save_conference_list(cls, locked=False):
        global _conferences
        global _conference_lock
        db = new_redis()

        async with LockManager(_conference_lock, locked):
            await db.set(_conference_key, json.dumps([c.to_redis() for c in _conferences]))  # list of dict

    @classmethod
    async def from_redis(cls, saved_data, locked=False):
        global _conference_lock
        global _last_conference

        async with LockManager(_conference_lock, locked):
            int_id = int(saved_data['id'])
            if int_id > _last_conference:
                # keep up gid as conference increases
                _last_conference = int_id

            id_ = saved_data['id']
            participants = [PhoneNumber(p) for p in saved_data['participants']]
            sid = saved_data.get('sid', "")
            started = saved_data.get('started', None)
            if started:
                started = datetime.fromisoformat(started)

            return TwilConference(id_, participants, sid, started)

    @classmethod
    async def create(cls, locked=None) -> 'TwilConference':
        global _conference_lock
        global _last_conference

        async with LockManager(_conference_lock, locked):
            new_id = _last_conference + 1
            _last_conference = new_id

            return TwilConference(new_id)

    def __init__(self, id_, participants=None, sid=None, started=None):
        super(TwilConference, self).__init__()
        if not participants:
            participants = []

        if not sid:
            sid = ""


        self.id: int = id_
        # This is the real thing we need to make changes
        # We should get it on callback
        self.twil_sid: str = sid
        self.participants: List[PhoneNumber] = participants
        self.started: Optional[datetime] = started

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
            except Exception:
                # fall out to default
                pass
        elif isinstance(other, int):
            return self.id == other

        return False

    def to_redis(self):
        return {
            'id': self.id,
            'participants': self.participants,
            'sid': self.twil_sid,
            'started': self.started.isoformat()
        }


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
        global _conference_lock
        global _conferences

        async with LockManager(_conference_lock):
            dirty = False

            # conf_name = body.get('FriendlyName')
            participant = body.get('ParticipantLabel')
            event_name = body.get('StatusCallbackEvent')
            conf_sid = body.get('ConferenceSid')

            self.d(f'{participant} triggered {event_name}')

            if not self.twil_sid:
                self.twil_sid = conf_sid
                dirty = True

            if participant not in self.participants:
                # add a participant when we first see them in a callback
                self.participants.append(PhoneNumber(participant))
                dirty = True

            if event_name == 'conference-start': # conference start, mark time
                self.started = datetime.now()

            if dirty:
                await self._save_conference_list(True)

        return ""

    async def add_participant(self, from_number: PhoneNumber, number_to_call: PhoneNumber):
        global _twil_lock
        global _twilio_client
        global _conferences
        global _conference_lock

        async with LockManager(_twil_lock):
            _twilio_client.calls.create(
                url=self.twiml_callback,
                to=number_to_call.e164,
                from_=from_number.e164
            )

        async with LockManager(_conference_lock):
            await self._save_conference_list()

    def twiml_xml(self, number_calling: PhoneNumber) -> VoiceResponse:
        response = VoiceResponse()
        dial = Dial()
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

    def __str__(self):
        return f'Conf[{self.id}]'

async def new_conference() -> TwilConference:
    global _conferences
    global _conference_lock

    # will lock and unlock
    new_conf = await TwilConference.create()

    async with LockManager(_conference_lock):
        _conferences.append(new_conf)
        await TwilConference._save_conference_list(True)

    return new_conf



# todo: This is the source of the following error during the tests:
# Error in atexit._run_exitfuncs:
# Traceback (most recent call last):
#   File "/Users/ddrexler/src/python/spins_halp_line/.venv/lib/python3.8/site-packages/greenletio/core.py", line 75, in stop
#     self.wait_event.set()
#   File "/Users/ddrexler/.pyenv/versions/3.8.1/lib/python3.8/asyncio/locks.py", line 288, in set
#     fut.set_result(True)
#   File "/Users/ddrexler/src/python/spins_halp_line/.venv/lib/python3.8/site-packages/trio_asyncio/_base.py", line 365, in call_soon
#     return self._queue_handle(Handle(callback, args, self, context=context, is_sync=True))
#   File "/Users/ddrexler/src/python/spins_halp_line/.venv/lib/python3.8/site-packages/trio_asyncio/_async.py", line 13, in _queue_handle
#     self._check_closed()
#   File "/Users/ddrexler/.pyenv/versions/3.8.1/lib/python3.8/asyncio/base_events.py", line 508, in _check_closed
#     raise RuntimeError('Event loop is closed')
# RuntimeError: Event loop is closed
# Exception in default exception handler
# Traceback (most recent call last):
#   File "/Users/ddrexler/.pyenv/versions/3.8.1/lib/python3.8/asyncio/base_events.py", line 1729, in call_exception_handler
#     self.default_exception_handler(context)
#   File "/Users/ddrexler/src/python/spins_halp_line/.venv/lib/python3.8/site-packages/trio_asyncio/_async.py", line 42, in default_exception_handler
#     raise RuntimeError(message)
# RuntimeError: Task was destroyed but it is pending!
# todo: This may not matter for this project, because the server should never terminate (and we aren't trying to persist
# todo: tasks if it does). Also the text message *is* sent so it's not clear what the still-running Task task is
# todo: supposed to be *doing*. However, this is still a problem and we should keep an eye on it.

# This pile of garbage is worth some explanation
# aio_as_trio is a decorator that tells Python that _twil_text is an asyncio function as opposed to a trio function.
# Why do we say that? Because we're using the asyncio library greenletio to make the synchronous
# twilio.rest.messages.create function async!
# todo: figure out if this gross stack of wrappers actually makes sense or not.
# @aio_as_trio
# async def _twil_text(from_number, to_number, message, media_url):
#     await async_()(
#         body=message,
#         from_=from_number,
#         to=to_number,
#         media_url=media_url
#     )

def _do_send_sms(client, frm:str, to:str, msg:str, m_url=values.unset):
    client.messages.create(body=msg,from_=frm,to=to,media_url=m_url)


async def send_sms(
        from_number:PhoneNumber,
        to_number:PhoneNumber,
        message:str,
        media_url=values.unset,
        client=None
):
    if client:
        # used for error state where we send out texts to ourselves
        _do_send_sms(
            client,
            from_number.e164,
            to_number.e164,
            message,
            media_url
        )
    else:
        global _twilio_client
        global _twil_lock

        async with LockManager(_twil_lock):
            _do_send_sms(
                _twilio_client,
                from_number.e164,
                to_number.e164,
                message,
                media_url
            )