from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tabular_analyst.core.config import get_settings
from tabular_analyst.core.db import get_session
from tabular_analyst.domain.models import DemoQuotaRecord


def require_demo_access(
    request: Request,
    session: Session = Depends(get_session),
    x_demo_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if not settings.api_auth_token:
        return
    bearer = authorization.replace("Bearer ", "", 1).strip() if authorization else None
    supplied = x_demo_key or bearer
    if supplied != settings.api_auth_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing demo token.")

    client_host = request.client.host if request.client else "unknown"
    identity_hash = sha256(f"{client_host}:{supplied}".encode("utf-8")).hexdigest()
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
