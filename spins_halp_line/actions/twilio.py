import json
from copy import copy
from typing import List, Union

import trio
from twilio import rest
from twilio.twiml.voice_response import Conference, Dial, VoiceResponse
from greenletio import async_
from trio_asyncio import aio_as_trio
from twilio.base import values

from ..constants import Credentials, Root_Url
from spins_halp_line.services.redis import new_redis
from spins_halp_line.util import LockManager, PhoneNumber

_twilio_client : rest.Client = rest.Client(Credentials["twilio"]["sid"], Credentials["twilio"]["token"])
_twil_lock = trio.Lock()
_conference_lock = trio.Lock()
# I get why we use strings of object names that haven't been defined yet but like my god
_conferences : List['TwilConference'] = []
_last_conference = 0

_conference_key = "spins_conference_list"

Conf_Twiml_Path = "/conf/twiml/<cnumber>"
Conf_Status_Path = "/conf/status/<cnumber>"

# This exists because we need to keep track of conferences and how they are progressing
class TwilConference:

    _callbacks = " ".join(['start', 'end', 'leave'])

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
    async def _save_conference_list(cls, confs: List['TwilConference']):
        db = new_redis()
        await db.set(_conference_key, json.dumps([c.to_redis() for c in confs]))  # list of dict

    @classmethod
    async def from_redis(cls, saved_data, locked=False):
        global _conference_lock
        global _last_conference

        async with LockManager(_conference_lock, locked):
            int_id = int(saved_data['id'])
            if int_id > _last_conference:
                # keep up gid as conference increases
                _last_conference = int_id

            return TwilConference(saved_data['id'], saved_data['participants'], saved_data['sid'])

    @classmethod
    async def create(cls, locked=None) -> 'TwilConference':
        global _conference_lock
        global _last_conference

        async with LockManager(_conference_lock, locked):
            new_id = _last_conference + 1
            _last_conference = new_id

            return TwilConference(new_id)

    @classmethod
    async def handle_callback(cls, conf_id, args, locked=False) -> str:
        global _conference_lock
        global _conferences

        async with LockManager(_conference_lock, locked):
            for conf in _conferences:
                if conf.matches(conf_id): # use function to handle type problems
                    if conf.twil_sid is None:
                        conf.twil_sid = args.get('ConferenceSid')
                    event = args.get('StatusCallbackEvent')

                    await cls._save_conference_list(_conferences)

        return ""

    def __init__(self, id, participants=None, sid=None):
        if not participants:
            participants = []

        self.id = id
        # This is the real thing we need to make changes
        # We should get it on callback
        self.twil_sid = sid
        self.participants = participants

    @property
    def status_callback(self):
        return '/'.join([Root_Url, 'conf', 'status', str(self.id)])

    @property
    def twiml_callback(self):
        return '/'.join([Root_Url, 'conf', 'twiml', str(self.id)])

    def matches(self, potential_id: Union[str, int]):
        if not isinstance(potential_id, int):
            try:
                potential_id = int(potential_id)
            except:
                # we don't care
                pass

        # should be fine if we pass a string int, otherwise should cleanly return false
        return potential_id == self.id

    def to_redis(self):
        return {
            'id': self.id,
            'participants': self.participants,
            'sid': self.twil_sid
        }

    async def _add_through_conf(self, from_number: PhoneNumber, number_to_call: PhoneNumber):
        pass

    async def add_participant(self, from_number: PhoneNumber, number_to_call: PhoneNumber):
        if self.twil_sid:
            return await self._add_through_conf(from_number, number_to_call)

        global _twil_lock
        global _twilio_client

        async with LockManager(_twil_lock):
            _twilio_client.calls.create(
                url=self.twiml_callback,
                to=number_to_call.e164,
                from_=from_number.e164
            )


    def twiml_xml(self, number_calling: PhoneNumber) -> VoiceResponse:
        response = VoiceResponse()
        dial = Dial()
        dial.conference(
            f'{self.id}',
            status_callback_event=self._callbacks,
            status_callback=self.status_callback,
            # This argument is not documented in the SDK, but it does work in the generated XML
            participant_label=number_calling.e164
        )
        response.append(dial)
        return response

def conferences() -> List[TwilConference]:
    global _conferences
    return _conferences

async def new_conference() -> TwilConference:
    global _conferences
    global _conference_lock

    # will lock and unlock
    new_conf = await TwilConference.create()

    async with LockManager(_conference_lock):
        _conferences.append(new_conf)
        print(_conferences)
        await TwilConference._save_conference_list(_conferences)

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

async def send_sms(from_number, to_number, message, media_url=values.unset):
    global Client
    global _twil_lock

    await _twil_lock.acquire()
    try:
        _twilio_client.messages.create(
            body=message,
            from_=from_number,
            to=to_number,
            media_url=media_url
        )
        # await _twil_text(from_number, to_number, message, media_url)
    finally:
        _twil_lock.release()