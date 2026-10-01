"""v4.0 스모크 테스트: 사용자 검색, 친구 요청/수락/거절/취소/끊기, 관계 라벨, 방명록 '+친구 추가'·관계 칩."""

from sqlalchemy import select

from app.database import SessionLocal
from app.friends import are_friends, clean_label
from app.models import Friendship, Notification, User

from .conftest import AJAX


def uid(kakao_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.kakao_id == kakao_id))


def friendship(a_kakao: int, b_kakao: int) -> Friendship | None:
    a, b = uid(a_kakao), uid(b_kakao)
    with SessionLocal() as db:
        return db.scalar(
            select(Friendship).where(
                ((Friendship.requester_id == a) & (Friendship.addressee_id == b))
                | ((Friendship.requester_id == b) & (Friendship.addressee_id == a))
            )
        )


def notif_types(kakao_id: int) -> list[str]:
    with SessionLocal() as db:
        return list(db.scalars(select(Notification.type).where(Notification.user_id == uid(kakao_id)).order_by(Notification.id)))


def test_clean_label():
    assert clean_label("친구") == "친구"
    assert clean_label("동료") == "동료"
    assert clean_label("custom", "  대학  동기 ") == "대학 동기"
    assert clean_label("custom", "") is None
    assert clean_label("custom", "x" * 21) is None


def test_search_users(make_client):
    a = make_client(1, "에이")
    make_client(2, "비비")
    make_client(3, "씨씨")
    page = a.get("/friends", params={"q": "비"}).text
    assert "비비" in page and "씨씨" not in page
    page = a.get("/friends", params={"q": "에이"}).text  # 나 자신은 검색 결과에서 제외
    assert f'href="/users/{uid(1)}"' not in page and "해당하는 사용자가 없어요" in page


def test_request_accept_flow_with_labels(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    b_id = uid(2)

    r = a.post(f"/friends/request/{b_id}", data={"label": "custom", "custom_label": "대학 동기"}, headers=AJAX)
    assert r.json()["reload"] is True
    f = friendship(1, 2)
    assert f.status == "pending" and f.requester_label == "대학 동기"
    assert notif_types(2) == ["friend_request"]

    # 중복 요청 / 자기 자신 / 없는 사용자
    assert a.post(f"/friends/request/{b_id}", headers=AJAX).status_code == 400
    assert a.post(f"/friends/request/{uid(1)}", headers=AJAX).status_code == 400
    assert a.post("/friends/request/9999", headers=AJAX).status_code == 404

    page_b = b.get("/friends").text
    assert "받은 요청" in page_b and f'id="fr-{f.id}"' in page_b and "대학 동기" in page_b

    # 요청자는 수락할 수 없음, 수신자가 '동료'로 수락
    assert a.post(f"/friends/{f.id}/accept", headers=AJAX).status_code == 403
    b.post(f"/friends/{f.id}/accept", data={"label": "동료"}, headers=AJAX)
    f = friendship(1, 2)
    assert f.status == "accepted" and f.addressee_label == "동료" and f.accepted_at
    assert notif_types(1) == ["friend_accept"]
    with SessionLocal() as db:
        assert are_friends(db, uid(1), uid(2))

    # 각자 자기 라벨로 보임
    assert "대학 동기" in a.get("/friends").text
    assert '<span class="chip rel-chip">동료</span>' in b.get("/friends").text

    # 라벨 수정(본인 쪽만)
    a.post(f"/friends/{f.id}/label", data={"label": "친구"}, headers=AJAX)
    assert friendship(1, 2).requester_label == "친구" and friendship(1, 2).addressee_label == "동료"
    assert a.post(f"/friends/{f.id}/label", data={"label": "custom", "custom_label": ""}, headers=AJAX).status_code == 400

    # 끊기는 양쪽 다 가능, 제3자는 불가
    c = make_client(3, "씨")
    assert c.post(f"/friends/{f.id}/remove", headers=AJAX).status_code == 403
    b.post(f"/friends/{f.id}/remove", headers=AJAX)
    assert friendship(1, 2) is None


def test_reject_and_cancel(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    a.post(f"/friends/request/{uid(2)}", headers=AJAX)
    fid = friendship(1, 2).id
    assert a.post(f"/friends/{fid}/reject", headers=AJAX).status_code == 403  # 요청자가 거절 불가
    b.post(f"/friends/{fid}/reject", headers=AJAX)
    assert friendship(1, 2) is None
    assert notif_types(1) == ["friend_reject"]

    # 거절 알림 클릭 → 친구 페이지
    with SessionLocal() as db:
        nid = db.scalar(select(Notification.id).where(Notification.user_id == uid(1)))
    assert a.get(f"/notifications/{nid}/go", follow_redirects=False).headers["location"] == "/friends"

    a.post(f"/friends/request/{uid(2)}", headers=AJAX)
    fid = friendship(1, 2).id
    assert b.post(f"/friends/{fid}/cancel", headers=AJAX).status_code == 403  # 수신자는 취소 불가
    a.post(f"/friends/{fid}/cancel", headers=AJAX)
    assert friendship(1, 2) is None


def test_reverse_request_auto_accepts(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    a.post(f"/friends/request/{uid(2)}", headers=AJAX)
    b.post(f"/friends/request/{uid(1)}", data={"label": "동료"}, headers=AJAX)
    f = friendship(1, 2)
    assert f.status == "accepted" and f.addressee_label == "동료"


def test_guestbook_add_friend_button_and_chip(make_client):
    a = make_client(1, "에이")
    b = make_client(2, "비")
    a.get("/"), b.get("/")  # 환영 메시지 소비
    a.post("/posts", data={"content": "에이의 글"}, headers=AJAX)

    assert "+친구 추가" not in a.get("/").text          # 내 글에는 없음
    assert "+친구 추가" not in make_client().get("/").text  # 비로그인도 없음
    page = b.get("/").text
    assert f'class="rel rel-user-{uid(1)}"' in page and "+친구 추가" in page

    # 글에서 바로 요청(inline) → 새로고침 없이 관계 표시만 교체
    r = b.post(f"/friends/request/{uid(1)}", data={"label": "친구", "inline": "1"}, headers=AJAX).json()
    assert "reload" not in r
    assert r["replace_all"][0]["selector"] == f".rel-user-{uid(1)}" and "요청 보냄" in r["replace_all"][0]["html"]
    assert "요청 받음" in a.get(f"/users/{uid(2)}").text

    a.post(f"/friends/{friendship(1, 2).id}/accept", data={"label": "custom", "custom_label": "옆집"}, headers=AJAX)
    page = b.get("/").text
    assert "+친구 추가" not in page and ">친구</a>" in page  # 비가 붙인 라벨 '친구'가 칩으로
    assert ">옆집</a>" in a.get(f"/users/{uid(2)}").text

    # 친구 관계는 회원 삭제 시 함께 삭제
    with SessionLocal() as db:
        db.delete(db.get(User, uid(2)))
        db.commit()
        assert db.scalar(select(Friendship)) is None
