import trio
from twilio import rest
# from greenletio import async_
# from trio_asyncio import aio_as_trio
from twilio.base import values

from ..constants import Credentials
from spins_halp_line.util import LockManager
from spins_halp_line.tasks import add_task, Task
from ..resources.numbers import PhoneNumber, Global_Number_Library

_twilio_client: rest.Client = rest.Client(Credentials["twilio"]["sid"], Credentials["twilio"]["token"])
_twil_lock = trio.Lock()



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

async def make_call(to_num: PhoneNumber, from_num: PhoneNumber, callback_url: str):
    global _twilio_client
    global _twil_lock

    async with LockManager(_twil_lock):
        _twilio_client.calls.create(
            url=callback_url,
            to=to_num.e164,
            from_=from_num.e164
        )


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
        self.d(f'Text[{from_num} -> {self.to}]: {self.Text}')
        await send_sms(
            from_num,
            self.to,
            self.Text,
            image
        )

async def send_text(TextClass, player_numer: PhoneNumber, delay=0):
    await add_task.send(TextClass(player_numer, delay))
