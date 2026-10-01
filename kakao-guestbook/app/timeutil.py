from datetime import datetime, timedelta, timezone

# 한국은 서머타임이 없으므로 고정 오프셋을 씁니다(컨테이너에 tzdata가 없어도 동작).
KST = timezone(timedelta(hours=9), "KST")


def to_kst(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:  # DB에 저장된 값은 tz 없는 UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def format_kst(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    local = to_kst(dt)
    return local.strftime(fmt) if local else ""
