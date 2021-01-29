import logging
from typing import Union, Optional, IO, Any
from copy import deepcopy

import trio
import hypercorn.logging as hyplog

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


# todo: Maybe we want to write our own version of hypercorn.logging.Logger so we can
# todo: control which access logs we log and which ones we don't
# sample log from the hypercorn code:
# await self.config.log.access(
#         self.scope, {"status": status_code, "headers": []}, time() - self.start_time
#     )

def do_monkey_patches():
    # who needs config options with python
    hyplog._create_logger = our_create_logger

_logger = None

def get_logger():
    global _logger
    if _logger is None:
        # Permanent note to self: Syslog already has timestamps ya git. Stop adding them back in!
        # formatter = logging.Formatter('[%(asctime)s.%(msecs)03d]%(message)s', datefmt="%d|%H:%M:%S")
        formatter = logging.Formatter('%(message)s')

        stream_formatter = logging.StreamHandler()
        stream_formatter.setFormatter(formatter)

        logger = logging.getLogger("spins")
        # https://stackoverflow.com/questions/19561058/duplicate-output-in-simple-python-logging-configuration/19561320#19561320
        logger.propagate = False # prevent double logs
        logger.handlers.clear()
        logger.addHandler(stream_formatter)
        _logger = logger

    return _logger


class Logger(object):

    def __init__(self):
        super(Logger, self).__init__()
        self._log = get_logger()

    def _log_line(self, level, line) -> str:
        return f' {level}|{self}: {line}'

    def e(self, line):
        self._log.error(self._log_line('E',line), stacklevel=2)

    def w(self, line):
        self._log.warning(self._log_line('W',line), stacklevel=2)

    def d(self, line):
        self._log.debug(self._log_line('D',line), stacklevel=2)

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
