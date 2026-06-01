from time import time

from fastapi import Header, HTTPException, Request, status

from tabular_analyst.core.config import get_settings

_quota_window: dict[str, list[float]] = {}


def require_demo_access(
    request: Request,
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

    identity = f"{request.client.host if request.client else 'unknown'}:{supplied}"
    now = time()
    cutoff = now - 24 * 60 * 60
    events = [stamp for stamp in _quota_window.get(identity, []) if stamp >= cutoff]
    if len(events) >= settings.demo_daily_request_limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Daily demo quota exceeded.")
    events.append(now)
    _quota_window[identity] = events

