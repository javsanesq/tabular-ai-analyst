import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from tabular_analyst.core import security
from tabular_analyst.domain.models import Base, DemoQuotaRecord


class TestSettings:
    api_auth_token = "demo-token"
    demo_daily_request_limit = 1
    app_env = "development"


def _request() -> Request:
    return Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []})


def test_demo_quota_is_persisted_without_storing_raw_token(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(security, "get_settings", lambda: TestSettings())

    with Session() as session:
        security.require_demo_access(_request(), session, x_demo_key="demo-token", authorization=None)
        records = session.scalars(select(DemoQuotaRecord)).all()
        assert len(records) == 1
        assert records[0].identity_hash != "127.0.0.1:demo-token"

        with pytest.raises(HTTPException) as exc:
            security.require_demo_access(_request(), session, x_demo_key="demo-token", authorization=None)
        assert exc.value.status_code == 429


def test_demo_auth_rejects_wrong_token_before_quota(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(security, "get_settings", lambda: TestSettings())

    with Session() as session:
        with pytest.raises(HTTPException) as exc:
            security.require_demo_access(_request(), session, x_demo_key="wrong", authorization=None)
        assert exc.value.status_code == 401
