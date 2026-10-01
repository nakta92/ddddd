"""v5.0 실시간(SSE) 라이브 테스트.

SSE는 응답이 끝나지 않는 스트림이라 TestClient로는 검증할 수 없어,
가짜 카카오 로그인을 붙인 실제 uvicorn 서버(tests/live_server.py)를 띄워 httpx 스트림으로 이벤트를 받습니다.
"""

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_base(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("live")
    port = free_port()
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp}/live.db",
        "UPLOAD_DIR": str(tmp / "uploads"),
        "KAKAO_REST_API_KEY": "live-test",
        "SECRET_KEY": "live-test",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.live_server", str(port)],
        cwd=PROJECT_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if httpx.get(base + "/", trust_env=False).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("라이브 서버가 시작되지 않았습니다:\n" + proc.stdout.read().decode(errors="replace"))
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def login(base: str, kakao_id: int, nickname: str) -> httpx.Client:
    client = httpx.Client(base_url=base, follow_redirects=True, trust_env=False, timeout=10)
    client.get(f"/__fake_kakao/as/{kakao_id}/{nickname}")
    r = client.get("/auth/kakao/login")
    assert r.status_code == 200 and nickname in r.text
    return client


class SSEListener:
    """백그라운드 스레드에서 SSE 이벤트를 읽어 큐에 넣습니다."""

    def __init__(self, client: httpx.Client, path: str):
        self.events: queue.Queue = queue.Queue()
        self.client = client
        self.path = path
        self.status: int | None = None
        self._response: httpx.Response | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            with self.client.stream("GET", self.path, timeout=httpx.Timeout(10, read=60)) as r:
                self._response = r
                self.status = r.status_code
                if r.status_code != 200:
                    self.events.put(("http_error", {"status": r.status_code}))
                    return
                event = None
                for line in r.iter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:"):
                        self.events.put((event, json.loads(line[5:])))
        except Exception:  # 테스트 종료 시 연결 닫힘
            pass

    def close(self):
        # 읽기 스레드는 데몬이라 기다리지 않습니다. 서버 쪽 정리는 종료 대기 시간 제한으로 처리됩니다.
        if self._response is not None:
            try:
                self._response.close()
            except Exception:
                pass

    def wait_for(self, event_type: str, timeout: float = 5.0, predicate=lambda d: True) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                etype, data = self.events.get(timeout=max(0.05, deadline - time.time()))
            except queue.Empty:
                break
            if etype == event_type and predicate(data):
                return data
        raise AssertionError(f"{timeout}초 안에 '{event_type}' 이벤트를 받지 못했습니다.")


def test_realtime_chat_events(live_base):
    a = login(live_base, 101, "라이브에이")
    b = login(live_base, 102, "라이브비")
    c = login(live_base, 103, "라이브씨")

    # 사이 맺기: 서로 요청하면 자동 수락
    a_id = int(a.get("/__whoami").json()["id"])
    b_id = int(b.get("/__whoami").json()["id"])
    a.post(f"/friends/request/{b_id}", headers={"X-Requested-With": "fetch"})
    b.post(f"/friends/request/{a_id}", headers={"X-Requested-With": "fetch"})

    r = a.post("/chat/rooms", data={"name": "실시간 방", "invitees": [str(b_id)]})
    room = int(str(r.url).rstrip("/").rsplit("/", 1)[1])
    b.post(f"/chat/{room}/accept")

    a_room = SSEListener(a, f"/chat/{room}/events")
    b_room = SSEListener(b, f"/chat/{room}/events")
    b_user = SSEListener(b, "/chat/events")
    a_room.wait_for("ready")
    b_room.wait_for("ready")
    b_user.wait_for("ready")

    # 멤버가 아니면 구독 불가
    c_room = SSEListener(c, f"/chat/{room}/events")
    c_room.wait_for("http_error")
    assert c_room.status == 403

    # 에이가 보낸 메시지가 비에게 실시간으로 도착
    sent = a.post(f"/chat/{room}/messages", data={"content": "실시간 안녕!"}, headers={"X-Requested-With": "fetch"}).json()
    got = b_room.wait_for("message", predicate=lambda d: d["id"] == sent["id"])
    assert "실시간 안녕!" in got["html"] and got["user_id"] == a_id

    # 비의 채팅 목록 채널에는 안 읽은 수 1
    unread = b_user.wait_for("unread", predicate=lambda d: d["room_id"] == room)
    assert unread["count"] == 1 and unread["preview"] == "실시간 안녕!"

    # 비가 읽으면 에이에게 읽음 이벤트 → "1명 읽음" 갱신 근거
    b.post(f"/chat/{room}/read")
    read = a_room.wait_for("read", predicate=lambda d: d["user_id"] == b_id)
    assert read["last_read"] >= sent["id"]

    for listener in (a_room, b_room, b_user, c_room):
        listener.close()
    for client in (a, b, c):
        client.close()
