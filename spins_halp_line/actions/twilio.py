
import trio
from twilio import rest
from greenletio import async_
from trio_asyncio import aio_as_trio

from ..constants import Credentials

_twilio_client : rest.Client = rest.Client(Credentials["twilio"]["sid"], Credentials["twilio"]["token"])
_lock = trio.Lock()


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
@aio_as_trio
async def _twil_text(from_number, to_number, message):
    await async_(_twilio_client.messages.create)(
        body=message,
        from_=from_number,
        to=to_number
    )

async def send_sms(from_number, to_number, message):
    global Client
    global _lock

    await _lock.acquire()
    # async_message_create = async_(_twilio_client.messages.create)
    # await aio_as_trio(async_message_create)(
    #     body=message,
    #     from_=from_number,
    #     to=to_number
    # )
    await _twil_text(from_number, to_number, message)
    _lock.release()