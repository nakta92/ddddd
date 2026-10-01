import math

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import AppError, flash, get_current_user, login_required, render, wants_json
from ..models import REACTIONS, Comment, Post, Reaction, User, utcnow
from ..notify import notify, snippet
from ..views import build_post_nodes, page_of_post, post_context, post_url, render_post_html

router = APIRouter()

POST_MAX_LEN = 2000
COMMENT_MAX_LEN = 1000


def clean_content(content: str | None, max_len: int, redirect_to: str | None = None) -> str:
    content = (content or "").strip()
    if not content:
        raise AppError("내용을 입력해 주세요.", redirect_to=redirect_to)
    if len(content) > max_len:
        raise AppError(f"{max_len}자 이하로 입력해 주세요.", redirect_to=redirect_to)
    return content


def total_posts(db: Session) -> int:
    return db.scalar(select(func.count(Post.id))) or 0


def post_response(request: Request, db: Session, post: Post, viewer: User,
                  focus: str | None = None, message: str | None = None, extra: dict | None = None):
    """AJAX면 갱신된 글 HTML 조각을, 아니면 해당 글 위치로 리다이렉트를 돌려줍니다."""
    if wants_json(request):
        return JSONResponse(
            {
                "ok": True,
                "post_id": post.id,
                "html": render_post_html(request, db, post, viewer),
                "focus": focus,
                "url": post_url(db, post.id, focus),
                "message": message,
                **(extra or {}),
            }
        )
    if message:
        flash(request, message, "success")
    return RedirectResponse(post_url(db, post.id, focus), status_code=303)


def get_post_or_404(db: Session, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise AppError("글을 찾을 수 없습니다. 삭제되었을 수 있어요.", 404, redirect_to="/")
    return post


def get_comment_or_404(db: Session, comment_id: int) -> Comment:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise AppError("댓글을 찾을 수 없습니다. 삭제되었을 수 있어요.", 404)
    return comment


def ensure_owner(owner_id: int, user: User, what: str, redirect_to: str | None = None) -> None:
    if owner_id != user.id:
        raise AppError(f"본인이 작성한 {what}만 수정·삭제할 수 있습니다.", 403, redirect_to=redirect_to)


def toggle_reaction(db: Session, user: User, kind: str, *, post_id: int | None = None,
                    comment_id: int | None = None) -> Reaction | None:
    """같은 반응을 다시 누르면 취소, 다른 반응을 누르면 교체합니다(사용자당 1개)."""
    if kind not in REACTIONS:
        raise AppError("알 수 없는 반응입니다.")
    stmt = select(Reaction).where(Reaction.user_id == user.id)
    stmt = stmt.where(Reaction.post_id == post_id) if post_id else stmt.where(Reaction.comment_id == comment_id)
    existing = db.scalar(stmt)
    if existing and existing.kind == kind:
        db.delete(existing)
        db.commit()
        return None
    if existing:
        existing.kind = kind
        existing.created_at = utcnow()
        reaction = existing
    else:
        reaction = Reaction(user_id=user.id, post_id=post_id, comment_id=comment_id, kind=kind)
        db.add(reaction)
    db.commit()
    return reaction


@router.get("/")
def index(request: Request, page: int = 1, db: Session = Depends(get_db),
          user: User | None = Depends(get_current_user)):
    per_page = settings.posts_per_page
    total = total_posts(db)
    pages = max(1, math.ceil(total / per_page))
    page = min(max(1, page), pages)
    posts = db.scalars(
        select(Post).order_by(Post.id.desc()).offset((page - 1) * per_page).limit(per_page)
    ).all()
    return render(
        request, "index.html", user, db,
        nodes=build_post_nodes(db, list(posts), user),
        page=page, pages=pages, total=total,
        **post_context(db, user),
    )


@router.get("/posts/{post_id}")
def post_permalink(post_id: int, db: Session = Depends(get_db)):
    get_post_or_404(db, post_id)
    return RedirectResponse(post_url(db, post_id), status_code=303)


@router.post("/posts")
def create_post(request: Request, content: str = Form(""), db: Session = Depends(get_db),
                user: User = Depends(login_required)):
    content = clean_content(content, POST_MAX_LEN, redirect_to="/")
    post = Post(user_id=user.id, content=content)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post_response(request, db, post, user, focus=f"post-{post.id}", extra={"total": total_posts(db)})


@router.post("/posts/{post_id}/edit")
def edit_post(request: Request, post_id: int, content: str = Form(""), db: Session = Depends(get_db),
              user: User = Depends(login_required)):
    post = get_post_or_404(db, post_id)
    ensure_owner(post.user_id, user, "글", redirect_to=post_url(db, post.id))
    post.content = clean_content(content, POST_MAX_LEN, redirect_to=post_url(db, post.id))
    post.updated_at = utcnow()
    db.commit()
    return post_response(request, db, post, user, focus=f"post-{post.id}")


@router.post("/posts/{post_id}/delete")
def delete_post(request: Request, post_id: int, db: Session = Depends(get_db),
                user: User = Depends(login_required)):
    post = get_post_or_404(db, post_id)
    ensure_owner(post.user_id, user, "글", redirect_to=post_url(db, post.id))
    page = page_of_post(db, post.id)
    db.delete(post)  # 댓글·반응은 ON DELETE CASCADE로 함께 삭제
    db.commit()
    if wants_json(request):
        return JSONResponse(
            {"ok": True, "removed": f"post-{post_id}", "message": "글을 삭제했습니다.", "total": total_posts(db)}
        )
    flash(request, "글을 삭제했습니다.", "success")
    return RedirectResponse(f"/?page={page}", status_code=303)


@router.post("/posts/{post_id}/comments")
def create_comment(request: Request, post_id: int, content: str = Form(""), parent_id: str = Form(""),
                   db: Session = Depends(get_db), user: User = Depends(login_required)):
    post = get_post_or_404(db, post_id)
    content = clean_content(content, COMMENT_MAX_LEN, redirect_to=post_url(db, post.id))
    parent = None
    if parent_id.strip():
        parent = db.get(Comment, int(parent_id)) if parent_id.strip().isdigit() else None
        if parent is None or parent.post_id != post.id:
            raise AppError("답글을 달 댓글을 찾을 수 없습니다.", 404, redirect_to=post_url(db, post.id))
        if parent.parent_id is not None:  # 대댓글은 1단계까지만: 대댓글에 단 답글은 원 댓글 아래로
            parent = db.get(Comment, parent.parent_id)
    comment = Comment(post_id=post.id, user_id=user.id, parent_id=parent.id if parent else None, content=content)
    db.add(comment)
    db.flush()
    # 알림: 대댓글이면 원 댓글 작성자에게, 그리고 글 작성자에게(중복·본인 제외)
    notified = {user.id}
    if parent is not None and parent.user_id not in notified:
        notify(db, parent.user_id, user, "reply",
               f"{user.name}님이 회원님의 댓글에 답글을 남겼습니다: “{snippet(content)}”", "comment", comment.id)
        notified.add(parent.user_id)
    if post.user_id not in notified:
        notify(db, post.user_id, user, "comment",
               f"{user.name}님이 회원님의 글에 댓글을 남겼습니다: “{snippet(content)}”", "comment", comment.id)
    db.commit()
    db.refresh(comment)
    return post_response(request, db, post, user, focus=f"comment-{comment.id}")


@router.post("/comments/{comment_id}/edit")
def edit_comment(request: Request, comment_id: int, content: str = Form(""), db: Session = Depends(get_db),
                 user: User = Depends(login_required)):
    comment = get_comment_or_404(db, comment_id)
    anchor = f"comment-{comment.id}"
    ensure_owner(comment.user_id, user, "댓글", redirect_to=post_url(db, comment.post_id, anchor))
    comment.content = clean_content(content, COMMENT_MAX_LEN, redirect_to=post_url(db, comment.post_id, anchor))
    comment.updated_at = utcnow()
    db.commit()
    return post_response(request, db, get_post_or_404(db, comment.post_id), user, focus=anchor)


@router.post("/comments/{comment_id}/delete")
def delete_comment(request: Request, comment_id: int, db: Session = Depends(get_db),
                   user: User = Depends(login_required)):
    comment = get_comment_or_404(db, comment_id)
    ensure_owner(comment.user_id, user, "댓글", redirect_to=post_url(db, comment.post_id, f"comment-{comment.id}"))
    post = get_post_or_404(db, comment.post_id)
    db.delete(comment)  # 대댓글·반응도 함께 삭제
    db.commit()
    return post_response(request, db, post, user, message="댓글을 삭제했습니다.")


@router.post("/posts/{post_id}/react")
def react_post(request: Request, post_id: int, kind: str = Form(""), db: Session = Depends(get_db),
               user: User = Depends(login_required)):
    post = get_post_or_404(db, post_id)
    if toggle_reaction(db, user, kind, post_id=post.id):
        emoji, label = REACTIONS[kind]
        notify(db, post.user_id, user, "reaction",
               f"{user.name}님이 회원님의 글에 {emoji} {label} 반응을 남겼습니다: “{snippet(post.content)}”",
               "post", post.id, dedupe=True)
        db.commit()
    return post_response(request, db, post, user)


@router.post("/comments/{comment_id}/react")
def react_comment(request: Request, comment_id: int, kind: str = Form(""), db: Session = Depends(get_db),
                  user: User = Depends(login_required)):
    comment = get_comment_or_404(db, comment_id)
    if toggle_reaction(db, user, kind, comment_id=comment.id):
        emoji, label = REACTIONS[kind]
        notify(db, comment.user_id, user, "reaction",
               f"{user.name}님이 회원님의 댓글에 {emoji} {label} 반응을 남겼습니다: “{snippet(comment.content)}”",
               "comment", comment.id, dedupe=True)
        db.commit()
    post = get_post_or_404(db, comment.post_id)
    return post_response(request, db, post, user)
