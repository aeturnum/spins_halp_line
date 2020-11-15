import trio


class Task(object):
    async def execute(self):
        pass


class GitUpdate(object):
    async def execute(self):
        result = await trio.run_process("./pull_git.sh", shell=True)
        print(result)

    def __str__(self):
        return "GitUpdate"


async def work_queue(get_task):
    async for task in get_task:
        print(f"got task: {task}")
        try:
            await task.execute()
        except Exception as e:
            print(f"Task got exception: {e}")
            pass
