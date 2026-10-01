"""기존 DB 호환: 앱 시작 시 누락 컬럼을 자동으로 추가하는지 검증합니다."""

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database import make_engine
from app.migrations import init_db
from app.models import User


def test_adds_missing_columns_to_old_db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/old.db")
    # 초기 버전처럼 컬럼이 적은 users 테이블
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, kakao_id BIGINT, nickname VARCHAR(100))"))
        conn.execute(text("INSERT INTO users (kakao_id, nickname) VALUES (42, '예전 사용자')"))

    added = init_db(engine)

    assert "users.profile_image" in added
    assert "users.created_at" in added
    assert {"users.display_name", "users.bio", "users.is_admin", "users.username"} <= set(added)
    index_names = {i["name"] for i in inspect(engine).get_indexes("users")}
    assert "ix_users_username" in index_names
    model_cols = {c.name for c in User.__table__.columns}
    db_cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert model_cols <= db_cols
    assert "posts" in inspect(engine).get_table_names()  # 새 테이블은 create_all로 생성

    with Session(engine) as db:
        user = db.get(User, 1)
        assert user.nickname == "예전 사용자"
        assert user.created_at is not None  # 함수 기본값 컬럼은 현재 시각으로 채움
        assert user.is_admin is False  # 스칼라 기본값은 DEFAULT로 채움(v2.0)
        assert user.name == "예전 사용자"

    assert init_db(engine) == []  # 두 번째 실행은 변경 없음
    engine.dispose()
