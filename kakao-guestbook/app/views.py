"""방명록 화면용 뷰 모델 생성. 한 페이지의 댓글·반응을 한 번에 조회해 N+1 쿼리를 피합니다."""

from collections import defaultdict

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .deps import templates
from .models import REACTIONS, Comment, Post, Reaction, User


def reaction_summary(reactions: list[Reaction], viewer_id: int | None) -> list[dict]:
    by_kind: dict[str, list[Reaction]] = defaultdict(list)
    for r in reactions:
        by_kind[r.kind].append(r)
    summary = []
    for kind, (emoji, label) in REACTIONS.items():
        rs = by_kind.get(kind, [])
        summary.append(
            {
                "kind": kind,
                "emoji": emoji,
                "label": label,
                "count": len(rs),
                "names": ", ".join(r.user.name for r in rs),
                "mine": viewer_id is not None and any(r.user_id == viewer_id for r in rs),
            }
        )
    return summary


def build_post_nodes(db: Session, posts: list[Post], viewer: User | None) -> list[dict]:
    if not posts:
        return []
    viewer_id = viewer.id if viewer else None
    post_ids = [p.id for p in posts]

    comments = db.scalars(
        select(Comment).where(Comment.post_id.in_(post_ids)).order_by(Comment.id)
    ).all()
    comment_ids = [c.id for c in comments]

    conds = [Reaction.post_id.in_(post_ids)]
    if comment_ids:
        conds.append(Reaction.comment_id.in_(comment_ids))
    reactions = db.scalars(select(Reaction).where(or_(*conds)).order_by(Reaction.id)).all()

    post_reactions: dict[int, list[Reaction]] = defaultdict(list)
    comment_reactions: dict[int, list[Reaction]] = defaultdict(list)
    for r in reactions:
        if r.post_id is not None:
            post_reactions[r.post_id].append(r)
        else:
            comment_reactions[r.comment_id].append(r)

    comment_nodes: dict[int, dict] = {}
    top_level: dict[int, list[dict]] = defaultdict(list)
    comment_count: dict[int, int] = defaultdict(int)
    for c in comments:
        node = {"c": c, "reactions": reaction_summary(comment_reactions[c.id], viewer_id), "replies": []}
        comment_nodes[c.id] = node
        comment_count[c.post_id] += 1
        if c.parent_id is None:
            top_level[c.post_id].append(node)
        elif c.parent_id in comment_nodes:
            comment_nodes[c.parent_id]["replies"].append(node)

    return [
        {
            "p": p,
            "reactions": reaction_summary(post_reactions[p.id], viewer_id),
            "comments": top_level[p.id],
            "comment_count": comment_count[p.id],
        }
        for p in posts
    ]


def post_context(db: Session, viewer: User | None) -> dict:
    """_post.html 렌더링에 필요한 공통 컨텍스트(버전이 올라가며 친구 관계 등이 추가됩니다)."""
    return {}


def render_post_html(request: Request, db: Session, post: Post, viewer: User | None) -> str:
    node = build_post_nodes(db, [post], viewer)[0]
    ctx = {"request": request, "user": viewer, "node": node}
    ctx.update(post_context(db, viewer))
    return templates.get_template("_post.html").render(ctx)


def page_of_post(db: Session, post_id: int) -> int:
    newer = db.scalar(select(func.count(Post.id)).where(Post.id > post_id)) or 0
    return newer // settings.posts_per_page + 1


def post_url(db: Session, post_id: int, anchor: str | None = None) -> str:
    """글이 있는 페이지로 이동하는 URL. 앵커를 주면 해당 요소를 강조, 없으면 글 위치로만 이동합니다."""
    page = page_of_post(db, post_id)
    if anchor:
        return f"/?page={page}&highlight={anchor}#{anchor}"
    return f"/?page={page}#post-{post_id}"
