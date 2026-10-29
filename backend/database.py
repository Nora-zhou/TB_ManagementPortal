from pathlib import Path
from typing import Generator

from sqlmodel import Session

from db_migrate import init_db, make_engine

# 库文件固定在后端目录下，不依赖进程当前工作目录。
# （旧实现用 "sqlite:///./tasks.db"，从仓库根目录启动会在根目录凭空建一个空 tasks.db）
DB_PATH = Path(__file__).resolve().parent / "tasks.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = make_engine(DB_PATH)


def create_db_and_tables() -> None:
    """建表 + 执行增量迁移。幂等，可重复调用。"""
    init_db(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
