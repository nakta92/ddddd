"""SSE용 in-memory pub/sub.

채널(예: "room:3", "user:7")마다 구독자 큐를 두고, publish하면 각 구독자의 이벤트 루프로 안전하게 넘깁니다.
동기 엔드포인트(스레드풀)에서도 호출할 수 있도록 loop.call_soon_threadsafe를 씁니다.
단일 프로세스 전용이므로 uvicorn 워커를 여러 개 띄우면 워커 간에는 전달되지 않습니다.
"""

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass, field

QUEUE_SIZE = 200


@dataclass(eq=False)
class Subscriber:
    channel: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=QUEUE_SIZE))

    def _put(self, event: dict) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:  # 느린 클라이언트: 오래된 이벤트를 버리고 최신 이벤트 유지
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


class Broker:
    def __init__(self) -> None:
        self._subs: dict[str, set[Subscriber]] = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, channel: str) -> Subscriber:
        sub = Subscriber(channel=channel, loop=asyncio.get_running_loop())
        with self._lock:
            self._subs[channel].add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            subs = self._subs.get(sub.channel)
            if subs:
                subs.discard(sub)
                if not subs:
                    del self._subs[sub.channel]

    def publish(self, channel: str, event: dict) -> int:
        with self._lock:
            subs = list(self._subs.get(channel, ()))
        for sub in subs:
            try:
                sub.loop.call_soon_threadsafe(sub._put, event)
            except RuntimeError:  # 루프가 이미 닫힘
                self.unsubscribe(sub)
        return len(subs)

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._subs.get(channel, ()))


broker = Broker()
