from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import text
from typing import Generator
from models import ProductSKUCost  # noqa: F401 — ensures table is registered on startup

DATABASE_URL = "sqlite:///./tasks.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)

    # 008-multi-store: Add store column to all affected tables (idempotent)
    with engine.connect() as conn:
        for table in ("order", "suborder", "purchaseorder", "product", "pricesnapshot"):
            try:
                conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN store INTEGER DEFAULT 1'))
                conn.commit()
            except Exception:
                pass  # Column already exists — skip silently


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
