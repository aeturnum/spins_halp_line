import logging
from typing import Union, Optional, IO

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


# Todo: Maybe finish this class, but only if synched cache doesn't work out
#
# class TrioRWLock:
#     _reader_max = 10
#
#     def __int__(self):
#         self.read_lock = trio.Semaphore(self._reader_max) # 10 readers
#         self.write_lock = trio.Lock()
#         self.writer_waiting: Optional[trio.Event] = None
#         self.reading_tasks = {}
#
#
#     async def rlock(self):
#         our_task = trio.lowlevel.current_task()
#         # increment depth, don't lock again
#         if our_task in self.reading_tasks:
#             self.reading_tasks[our_task] += 1
#             return
#
#         # we might need to wait for a write to finish
#         if self.writer_waiting:
#             # the write will set this event when it finishes
#             await self.writer_waiting.wait()
#
#         # block if a write is happening
#         await self.write_lock.acquire()
#         await self.write_lock.release()
#         # aquire lock
#         await self.read_lock.acquire()
#         # set count to 1
#         self.reading_tasks[our_task] = 1
#
#     async def un_rlock(self):
#         our_task = trio.lowlevel.current_task()
#         if self.reading_tasks[our_task] > 1:
#             # undo repeated read lock
#             self.reading_tasks[our_task] -= 1
#         else:
#             await self.read_lock.release()
#
#     async def wlock(self):
#         if self.read_lock.value < self._reader_max:
#             self.worker_waiting = trio.Event()
#
#         await self.write_lock.acquire()
#         while
#
#     async def un_wlock(self):
#         pass
