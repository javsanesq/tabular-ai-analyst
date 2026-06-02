from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tabular_analyst.core.config import get_settings
from tabular_analyst.core.db import get_session
from tabular_analyst.domain.models import DemoQuotaRecord


@dataclass(frozen=True)
class AuthContext:
    owner_hash: str
    client_ip: str


def require_demo_access(
    request: Request,
    session: Session = Depends(get_session),
    x_demo_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> AuthContext:
    settings = get_settings()
    if not settings.api_auth_token:
        if settings.app_env == "test":
            return AuthContext(owner_hash="test-owner", client_ip=_client_ip(request))
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Demo access token is not configured.")
    bearer = authorization.replace("Bearer ", "", 1).strip() if authorization else None
    supplied = x_demo_key or bearer
    if not supplied or not compare_digest(supplied, settings.api_auth_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing demo token.")

    client_host = _client_ip(request)
    identity_hash = sha256(f"{client_host}:{supplied}".encode()).hexdigest()
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
    session.execute(
        delete(DemoQuotaRecord)
        .where(DemoQuotaRecord.created_at < cutoff)
        .execution_options(synchronize_session=False)
    )
    event_count = session.scalar(
        select(func.count())
        .select_from(DemoQuotaRecord)
        .where(DemoQuotaRecord.identity_hash == identity_hash)
        .where(DemoQuotaRecord.created_at >= cutoff)
    )
    if int(event_count or 0) >= settings.demo_daily_request_limit:
        session.commit()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Daily demo quota exceeded.")
    session.add(DemoQuotaRecord(id=str(uuid4()), identity_hash=identity_hash))
    session.commit()
    return AuthContext(owner_hash=identity_hash, client_ip=client_host)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"
