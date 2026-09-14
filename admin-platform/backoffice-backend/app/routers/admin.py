from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import APP_SERVER_URL

router = APIRouter()


class User(BaseModel):
    id: int
    username: str
    email: str
    status: Literal["active", "banned"]
    created_at: datetime


class UserStatusUpdate(BaseModel):
    status: Literal["active", "banned"]


class NoticeRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


# 외부 DB 없이 동작하도록 메모리에 가짜 데이터를 둔다
_now = datetime.now(timezone.utc)
_users: dict[int, User] = {
    1: User(id=1, username="alice", email="alice@example.com", status="active", created_at=_now),
    2: User(id=2, username="bob", email="bob@example.com", status="active", created_at=_now),
    3: User(id=3, username="charlie", email="charlie@example.com", status="banned", created_at=_now),
}


async def _app_server_request(method: str, path: str, **kwargs) -> dict:
    async with httpx.AsyncClient(base_url=APP_SERVER_URL, timeout=3.0) as client:
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()


@router.get("/dashboard")
async def dashboard():
    try:
        stats = await _app_server_request("GET", "/api/stats")
        app_server = {"status": "up", **stats}
    except httpx.HTTPError:
        app_server = {"status": "down"}

    return {
        "appServer": app_server,
        "users": {
            "total": len(_users),
            "active": sum(1 for u in _users.values() if u.status == "active"),
            "banned": sum(1 for u in _users.values() if u.status == "banned"),
        },
    }


@router.get("/users", response_model=list[User])
def list_users():
    return list(_users.values())


@router.get("/users/{user_id}", response_model=User)
def get_user(user_id: int):
    user = _users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/users/{user_id}/status", response_model=User)
def update_user_status(user_id: int, body: UserStatusUpdate):
    user = _users.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = body.status
    return user


@router.post("/notices")
async def send_notice(body: NoticeRequest):
    try:
        result = await _app_server_request("POST", "/api/broadcast", json={"message": body.message})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="app-server unavailable") from exc
    return {"sent": True, "delivered": result.get("delivered", 0)}
