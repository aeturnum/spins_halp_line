import redio


# holds the class that manages the player info in redis
# todo: Consider using a single coroutine to do all loading and storing of players so that
# todo: we can detect if a player is getting race condition'd (i.e. there are two copies of them)
# todo: out and they might get squashed

def redis_factory() -> redio.Redis:
    return redio.Redis("redis://localhost/")


# global redis connection factory
_redis = None


def new_redis():
    global _redis
    if _redis is None:
        _redis = redis_factory()

    return _redis()


async def delete_key(key):
    db = new_redis()

    await db.delete(key)
