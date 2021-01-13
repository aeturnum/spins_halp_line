import trio

from spins_halp_line.util import Logger

class Task(Logger):
    _re_raise_exceptions = False

    def __init__(self):
        super(Task, self).__init__()

    async def execute(self):
        pass

    @property
    def re_raise_exceptions(self):
        return self._re_raise_exceptions

    def __str__(self):
        return f"{self.__class__.__name__}"


class GitUpdate(Task):
    async def execute(self):
        result = await trio.run_process("./pull_git.sh", shell=True)
        print(result)


async def work_queue(get_task):
    async for task in get_task:
        print(f"got task: {task}")
        try:
            await task.execute()
        except Exception as e:
            print(f"Task got exception: {e}")
            if task.re_raise_exceptions:
                raise e
