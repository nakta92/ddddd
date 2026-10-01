"""v6.0 스모크 테스트: 공통 레이아웃 상속, 반응형 사이드바 메뉴(권한별), 현재 메뉴 표시, 배지."""

import re
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import User

from .conftest import AJAX

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"


def side_links(html: str) -> list[str]:
    nav = html.split('<nav class="side-nav">')[1].split("</nav>")[0]
    return re.findall(r'<span class="side-label">([^<]+)</span>', nav)


def active_link(html: str) -> str | None:
    m = re.search(r'class="side-link active"[^>]*>.*?<span class="side-label">([^<]+)</span>', html, re.S)
    return m.group(1) if m else None


def test_all_pages_extend_layout():
    pages = [p for p in TEMPLATES.glob("*.html") if not p.name.startswith("_") and p.name != "layout.html"]
    assert pages
    for page in pages:
        assert page.read_text(encoding="utf-8").startswith('{% extends "layout.html" %}'), page.name


def test_topbar_and_sidebar_for_anonymous(make_client):
    html = make_client().get("/").text
    topbar = html.split('<header class="topbar">')[1].split("</header>")[0]
    assert 'class="hamburger"' in topbar and 'class="logo"' in topbar
    assert "notif-badge" not in topbar  # 비로그인: 알림 배지 없음
    assert side_links(html) == ["방명록"]
    assert "카카오 로그인" in html.split('<aside class="sidebar"')[1]


def test_sidebar_for_member_and_active_menu(make_client):
    a = make_client(1, "에이")
    html = a.get("/").text
    assert 'id="notif-badge"' in html.split('<header class="topbar">')[1].split("</header>")[0]
    assert side_links(html) == ["방명록", "채팅", "친구", "알림", "내 정보"]
    assert active_link(html) == "방명록"
    assert active_link(a.get("/friends").text) == "친구"
    assert active_link(a.get("/notifications").text) == "알림"
    room = int(a.post("/chat/rooms", data={"name": "방"}, follow_redirects=False).headers["location"].rsplit("/", 1)[1])
    assert active_link(a.get(f"/chat/{room}").text) == "채팅"  # 하위 경로도 활성
    assert active_link(a.get("/me").text) == "내 정보"


def test_sidebar_admin_menu_and_friend_badge(make_client, monkeypatch):
    monkeypatch.setattr(settings, "admin_kakao_ids", "1")
    admin = make_client(1, "관리자")
    other = make_client(2, "비")
    assert "관리자" in side_links(admin.get("/").text)
    assert active_link(admin.get("/admin").text) == "관리자"

    with SessionLocal() as db:
        admin_id = db.scalar(select(User.id).where(User.kakao_id == 1))
    other.post(f"/friends/request/{admin_id}", headers=AJAX)
    assert re.search(r'data-badge="friends"\s*>1<', admin.get("/").text)
