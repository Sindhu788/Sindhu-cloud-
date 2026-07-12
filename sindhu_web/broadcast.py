"""Thread-safe pub/sub bridge between background job threads and the
WebSocket clients. Job threads call publish() synchronously from any
thread; the FastAPI app drains the queue in an asyncio task and forwards
to every connected client."""

import queue

_outbound = queue.Queue()
clients = set()


def publish(message: dict):
    _outbound.put(message)


def get_queue():
    return _outbound
