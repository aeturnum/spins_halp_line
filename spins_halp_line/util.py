import logging
from typing import Union, Optional, IO, Any
from copy import deepcopy

import trio

import hypercorn.logging as hyplog
import phonenumbers

logging.basicConfig(level=logging.DEBUG)


# modified version of create logger
def our_create_logger(
    name: str,
    target: Union[logging.Logger, str, None],
    level: Optional[str],
    sys_default: IO,
    *,
    propagate: bool = True,
) -> Optional[logging.Logger]:
    if isinstance(target, logging.Logger):
        return target

    if target:
        logger = logging.getLogger(name)
        logger.handlers = [
            logging.StreamHandler(sys_default) if target == "-" else logging.FileHandler(target)
        ]
        logger.propagate = propagate
        formatter = logging.Formatter(
            "[%(levelname)s] %(message)s",
            "",
        )
        logger.handlers[0].setFormatter(formatter)
        if level is not None:
            logger.setLevel(logging.getLevelName(level.upper()))
        return logger
    else:
        return None


def do_monkey_patches():
    # who needs config options with python
    hyplog._create_logger = our_create_logger


def get_logger():
    return logging.getLogger("spins")


class Logger(object):

    def __init__(self):
        super(Logger, self).__init__()
        self._log = get_logger()

    def e(self, line):
        self._log.error(f'{self}: {line}', stacklevel=2)

    def w(self, line):
        self._log.warning(f'{self}: {line}', stacklevel=2)

    def d(self, line):
        # print(f'{self}: {line}')
        self._log.debug(f'{self}: {line}', stacklevel=2)

    def __str__(self):
        return str(self.__class__)

async def pretty_print_request(r, label=""):
    s = []
    content_type = r.headers.get("Content-Type", None)

    if label:
        s.append(f"{label}:")
    s.append(f"{r.method} {r.url}")
    s.append("Headers:")
    for header, value in r.headers.items():
        s.append(f'  {header}: {value}')

    if r.args:
        s.append("Args:")
        for arg, value in r.args.items():
            s.append(f'{arg}: {value}')

    if content_type:
        if 'x-www-form-urlencoded' in content_type:
            form = await r.form
            s.append("Form:")
            for arg, value in form.items():
                s.append(f'{arg}: {value}')
        if 'json' in content_type:
            json = await r.get_json()
            s.append("JSON:")
            for arg, value in json.items():
                s.append(f'{arg}: {value}')

    print("\n".join(s))

class SynchedCache(Logger):

    def __init__(self):
        super(SynchedCache, self).__init__()

        self.cache = {}
        self.lock = trio.Lock()

    async def get(self, key):
        async with self.lock:
            return self.cache.get(key, None)

    async def set(self, key, value):
        async with self.lock:
            self.cache[key] = value
            return value


# Helper class to ease the demands on trio.Lock state tracking
class LockManager(Logger):

    def __init__(self, lock, already_locked = False):
        super(LockManager, self).__init__()

        self.lock : trio.Lock = lock
        self.expect_locked = already_locked

    def __enter__(self):
        raise NotImplementedError("Lock Manager only manages async locks!")

    async def __aenter__(self):
        if not self.expect_locked:
            await self.lock.acquire()
        else:
            if not self.lock.locked():
                raise ValueError("Locked method called as if lock was acquired, but it was not.")

        return self

    async def __aexit__(self, exc_type, exc, tb):
        if not self.expect_locked:
            self.lock.release()

# Helper class to restore a reference to a previous set of values (used to create psudo-transactions)
class Snapshot:
    def __init__(self, snap_of: Any):
        self._ref = snap_of
        # todo: This can cause potential problems for references to nested items in the data structure.
        # todo: I.e. if you have this setup:   {a: {b: {c: "d"}}}}
        # todo: and you have a reference to b, here/\
        # todo: restoring a snapshot will mean that reference is pointed to a data structure that doesn't exist because we did \
        # todo: a deep copy.
        self._snap = deepcopy(snap_of)

    def restore(self):
        for key, value in vars(self._snap).items():
            setattr(self._ref, key, value)

# Helper class to transform numbers
class PhoneNumber:

    def __init__(self, number: Union[str, int, 'PhoneNumber']):
        if isinstance(number, PhoneNumber):
            # This is to allow us to construct PhoneNumbers everywhere and not worry about nesting
            self._e164 = number._e164
        else:
            self._e164 = self._parse(number)

    # This is a rough, hand-rolled method for dealing with numbers
    def _parse(self, number) -> phonenumbers.PhoneNumber:
        if isinstance(number, int):
            number = str(number)

        try:
            # check for a clean e164
            number = phonenumbers.parse(number)
        except phonenumbers.phonenumberutil.NumberParseException:
            # if this throws just let it fly
            number = phonenumbers.parse("+1" + number)



        return number

    # Used for twilio purposes
    @property
    def e164(self):
        return phonenumbers.format_number(self._e164, phonenumbers.PhoneNumberFormat.E164)

    @property
    def friendly(self):
        if self._e164.country_code == 1:
            # If in the US or Canada, just do national
            return phonenumbers.format_number(self._e164, phonenumbers.PhoneNumberFormat.NATIONAL)
        else:
            # Otherwise international
            return phonenumbers.format_number(self._e164, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

    def __str__(self):
        return self.friendly
