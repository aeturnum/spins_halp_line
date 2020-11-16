from functools import wraps
from typing import Set

import trio

from trio import MemorySendChannel


# https://gitlab.com/pgjones/quart/-/blob/master/examples/websocket/websocket.py
event_websocket_channels: Set[MemorySendChannel] = set()

def event_websocket(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        global event_websocket_channels
        add_event, get_event = trio.open_memory_channel(10)
        event_websocket_channels.add(add_event)
        try:
            return await func(get_event, *args, **kwargs)
        finally:
            event_websocket_channels.remove(add_event)

    return wrapper

async def send_event(text: str):
    global event_websocket_channels
    for channel in event_websocket_channels:
        print(f"sending {text} to {channel}")
        await channel.send(text)