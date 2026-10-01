from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import AppError, back_path, flash, login_required, render, templates, wants_json
from ..friends import LABEL_MAX, PRESET_LABELS, clean_label, friendship_between, my_friendships, relation_map
from ..models import Friendship, User, utcnow
from ..notify import notify

router = APIRouter(prefix="/friends")

SEARCH_LIMIT = 20


def relation_html(request: Request, db: Session, viewer: User, target: User) -> str:
    return templates.get_template("_relation.html").render(
        {"request": request, "user": viewer, "target": target, "relations": relation_map(db, viewer.id)}
    )


def done(request: Request, db: Session, viewer: User, message: str, target: User | None = None,
         inline: bool = False):
    """친구 관련 동작 응답.

    inline=True(방명록 글의 '+친구 추가' 버튼 등)면 페이지를 새로고침하지 않고 해당 사용자 관계 표시만 교체,
    아니면 플래시 메시지를 남기고 새로고침/리다이렉트합니다.
    """
    if wants_json(request):
        if inline and target is not None:
            return JSONResponse({
                "ok": True,
                "message": message,
                "replace_all": [{"selector": f".rel-user-{target.id}", "html": relation_html(request, db, viewer, target)}],
            })
        flash(request, message, "success")
        return JSONResponse({"ok": True, "reload": True})
    flash(request, message, "success")
    return RedirectResponse(back_path(request, "/friends"), status_code=303)


def get_friendship(db: Session, fid: int) -> Friendship:
    f = db.get(Friendship, fid)
    if f is None:
        raise AppError("관계를 찾을 수 없습니다. 이미 처리되었을 수 있어요.", 404, redirect_to="/friends")
    return f


def label_or_error(label: str, custom_label: str) -> str:
    cleaned = clean_label(label, custom_label)
    if cleaned is None:
        raise AppError(f"관계 라벨을 1~{LABEL_MAX}자로 입력해 주세요.", redirect_to="/friends")
    return cleaned


@router.get("")
def friends_page(request: Request, q: str = "", db: Session = Depends(get_db), user: User = Depends(login_required)):
    friendships = my_friendships(db, user.id)
    q = q.strip()
    results = []
    if q:
        like = f"%{q}%"
        results = db.scalars(
            select(User)
            .where(User.id != user.id, or_(User.nickname.ilike(like), User.display_name.ilike(like)))
            .order_by(User.id)
            .limit(SEARCH_LIMIT)
        ).all()
    return render(
        request, "friends.html", user, db,
        q=q, results=results,
        relations=relation_map(db, user.id),
        friends=[f for f in friendships if f.status == "accepted"],
        received=[f for f in friendships if f.status == "pending" and f.addressee_id == user.id],
        sent=[f for f in friendships if f.status == "pending" and f.requester_id == user.id],
        preset_labels=PRESET_LABELS,
    )


@router.post("/request/{user_id}")
def send_request(request: Request, user_id: int, label: str = Form("친구"), custom_label: str = Form(""),
                 inline: str = Form(""), db: Session = Depends(get_db), user: User = Depends(login_required)):
    target = db.get(User, user_id)
    if target is None:
        raise AppError("사용자를 찾을 수 없습니다.", 404)
    if target.id == user.id:
        raise AppError("자기 자신에게는 친구 요청을 보낼 수 없습니다.")
    my_label = label_or_error(label, custom_label)

    existing = friendship_between(db, user.id, target.id)
    if existing and existing.status == "accepted":
        raise AppError(f"이미 {target.name}님과 사이를 맺었습니다.")
    if existing and existing.requester_id == user.id:
        raise AppError(f"이미 {target.name}님에게 친구 요청을 보냈습니다.")
    if existing:  # 상대가 먼저 보낸 요청이 있으면 바로 수락
        existing.status = "accepted"
        existing.addressee_label = my_label
        existing.accepted_at = utcnow()
        notify(db, existing.requester_id, user, "friend_accept",
               f"{user.name}님이 친구 요청을 수락했습니다.", "friends", existing.id)
        db.commit()
        return done(request, db, user, f"{target.name}님과 사이를 맺었습니다.", target, bool(inline))

    f = Friendship(requester_id=user.id, addressee_id=target.id, requester_label=my_label)
    db.add(f)
    db.flush()
    notify(db, target.id, user, "friend_request",
           f"{user.name}님이 친구 요청을 보냈습니다. (관계: {my_label})", "friends", f.id)
    db.commit()
    return done(request, db, user, f"{target.name}님에게 친구 요청을 보냈습니다.", target, bool(inline))


@router.post("/{fid}/accept")
def accept_request(request: Request, fid: int, label: str = Form("친구"), custom_label: str = Form(""),
                   db: Session = Depends(get_db), user: User = Depends(login_required)):
    f = get_friendship(db, fid)
    if f.addressee_id != user.id or f.status != "pending":
        raise AppError("수락할 수 있는 요청이 아닙니다.", 403, redirect_to="/friends")
    f.status = "accepted"
    f.addressee_label = label_or_error(label, custom_label)
    f.accepted_at = utcnow()
    notify(db, f.requester_id, user, "friend_accept", f"{user.name}님이 친구 요청을 수락했습니다.", "friends", f.id)
    db.commit()
    return done(request, db, user, f"{f.requester.name}님과 사이를 맺었습니다.")


@router.post("/{fid}/reject")
def reject_request(request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(login_required)):
    f = get_friendship(db, fid)
    if f.addressee_id != user.id or f.status != "pending":
        raise AppError("거절할 수 있는 요청이 아닙니다.", 403, redirect_to="/friends")
    requester = f.requester
    notify(db, requester.id, user, "friend_reject", f"{user.name}님이 친구 요청을 거절했습니다.", "friends", f.id)
    db.delete(f)
    db.commit()
    return done(request, db, user, f"{requester.name}님의 요청을 거절했습니다.")


@router.post("/{fid}/cancel")
def cancel_request(request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(login_required)):
    f = get_friendship(db, fid)
    if f.requester_id != user.id or f.status != "pending":
        raise AppError("취소할 수 있는 요청이 아닙니다.", 403, redirect_to="/friends")
    name = f.addressee.name
    db.delete(f)
    db.commit()
    return done(request, db, user, f"{name}님에게 보낸 요청을 취소했습니다.")


@router.post("/{fid}/remove")
def remove_friend(request: Request, fid: int, db: Session = Depends(get_db), user: User = Depends(login_required)):
    f = get_friendship(db, fid)
    if user.id not in (f.requester_id, f.addressee_id) or f.status != "accepted":
        raise AppError("끊을 수 있는 관계가 아닙니다.", 403, redirect_to="/friends")
    name = f.other(user.id).name
    db.delete(f)
    db.commit()
    return done(request, db, user, f"{name}님과의 사이를 끊었습니다.")


@router.post("/{fid}/label")
def update_label(request: Request, fid: int, label: str = Form("친구"), custom_label: str = Form(""),
                 db: Session = Depends(get_db), user: User = Depends(login_required)):
    f = get_friendship(db, fid)
    if user.id not in (f.requester_id, f.addressee_id):
        raise AppError("수정할 수 있는 관계가 아닙니다.", 403, redirect_to="/friends")
    new_label = label_or_error(label, custom_label)
    if f.requester_id == user.id:
        f.requester_label = new_label
    else:
        f.addressee_label = new_label
    db.commit()
    return done(request, db, user, f"관계 라벨을 '{new_label}'(으)로 바꿨습니다.")
