"""앱 시작 시 실행되는 경량 마이그레이션.

`create_all`은 새 테이블만 만들고 기존 테이블에 추가된 컬럼은 반영하지 않습니다.
그래서 모델에는 있는데 DB에는 없는 컬럼을 찾아 `ALTER TABLE ... ADD COLUMN`으로 추가합니다.
"""

import logging

from sqlalchemy import DateTime, MetaData, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import Column

from .models import utcnow

logger = logging.getLogger(__name__)


def _literal(value) -> str | None:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _default_sql(col: Column) -> str | None:
    if col.server_default is not None:
        arg = getattr(col.server_default, "arg", None)
        if isinstance(arg, str):
            return _literal(arg)
        if arg is not None and hasattr(arg, "text"):
            return arg.text
    if col.default is not None and getattr(col.default, "is_scalar", False):
        return _literal(col.default.arg)
    return None


def _column_ddl(col: Column, engine: Engine) -> str:
    parts = [f'"{col.name}"', col.type.compile(dialect=engine.dialect)]
    default = _default_sql(col)
    if default is not None:
        parts.append(f"DEFAULT {default}")
        if not col.nullable:
            parts.append("NOT NULL")
    # 기본값이 없는 NOT NULL 컬럼은 기존 행 때문에 추가할 수 없으므로 NULL 허용으로 추가합니다.
    return " ".join(parts)


def add_missing_columns(engine: Engine, metadata: MetaData) -> list[str]:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    added: list[str] = []

    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_cols = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing_cols:
                    continue
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {_column_ddl(col, engine)}'))
                # utcnow 같은 함수 기본값은 DDL로 줄 수 없으니 기존 행을 현재 시각으로 채웁니다.
                if isinstance(col.type, DateTime) and col.default is not None and col.default.is_callable:
                    conn.execute(table.update().where(col.is_(None)).values({col.name: utcnow()}))
                added.append(f"{table.name}.{col.name}")
            # 새로 추가된 컬럼의 인덱스(UNIQUE 포함)는 ALTER로 못 만드니 인덱스로 생성
            for index in table.indexes:
                try:
                    with conn.begin_nested():
                        index.create(conn, checkfirst=True)
                except Exception as e:  # 기존 데이터가 UNIQUE를 위반하는 경우 등
                    logger.warning("마이그레이션: 인덱스 %s 생성 실패: %s", index.name, e)

    for name in added:
        logger.info("마이그레이션: 컬럼 추가 %s", name)
    return added


def init_db(engine: Engine) -> list[str]:
    from .database import Base

    Base.metadata.create_all(engine)
    return add_missing_columns(engine, Base.metadata)
