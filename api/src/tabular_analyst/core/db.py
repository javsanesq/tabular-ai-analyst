from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tabular_analyst.core.config import get_settings

settings = get_settings()
engine_kwargs = {"future": True, "pool_pre_ping": True}
if settings.database_url == "sqlite+pysqlite:///:memory:":
    engine_kwargs.update({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool})
engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
