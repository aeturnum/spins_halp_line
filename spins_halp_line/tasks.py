import traceback

import trio

from spins_halp_line.util import Logger


class Task(Logger):
    _re_raise_exceptions = False

    def __init__(self, delay: int = 0):
        super(Task, self).__init__()
        # this is an approximate delay but that's fine
        self.delay = delay

    async def execute(self):
        pass

    @staticmethod
    async def do_an_execute(task_object: 'Task', task_status=trio.TASK_STATUS_IGNORED):
        task_status.started()
        task_object.d(f'Sleeping for {task_object.delay}s before starting')
        await trio.sleep(task_object.delay)
        try:
            # task_object.d(f'Starting....')
            await task_object.execute()
        except Exception as e:
            print(f"Task got exception: {e}")
            print("\n".join(traceback.extract_tb(e.__traceback__).format()))
            if task_object.re_raise_exceptions:
                raise e

        task_object.d(f'Finished!')

    @property
    def re_raise_exceptions(self):
        return self._re_raise_exceptions

    def __str__(self):
        return f"{self.__class__.__name__}"


class GitUpdate(Task):
    async def execute(self):
        result = await trio.run_process("./pull_git.sh", shell=True)
        print(result)


add_task, _get_task = trio.open_memory_channel(50)


async def Trio_Task_Task_Object_Runner():
    global _get_task
    # this is a work queue that fans out
    # We need to open the nursery first otherwise only one task will execute at once
    async with trio.open_nursery() as nurse:
        async for task in _get_task:
            print(f"got task: {task}")
            nurse.start_soon(task.do_an_execute, task)
