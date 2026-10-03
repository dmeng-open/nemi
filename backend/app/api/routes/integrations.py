from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_settings
from app.core.config import Settings
from app.core.exceptions import ProviderNotConfigured
from app.models.user import LOCAL_USER_ID
from app.providers.health import InMemoryProviderHealth, get_provider_health
from app.providers.http import TIMEOUT
from app.repositories.oauth import OAuthConnectionRepository
from app.repositories.users import ensure_local_user
from app.schemas.integrations import ConnectRequest, ConnectResponse, IntegrationsResponse
from app.services.integrations_status import CalendarConnection, build_integrations_response
from app.services.oauth import finish_callback, resolve_return_path, start_connect

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _health(request: Request) -> InMemoryProviderHealth:
    health = getattr(request.app.state, "provider_health", None)
    if isinstance(health, InMemoryProviderHealth):
        return health
    return get_provider_health()


@router.get("", response_model=IntegrationsResponse)
async def read_integrations(
    request: Request,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> IntegrationsResponse:
    # Settings and the health cache only. This route does not call upstream APIs.
    await ensure_local_user(session)
    calendar = None
    if settings.calendar_provider == "google":
        row = await OAuthConnectionRepository(session).get(LOCAL_USER_ID)
        if row is not None:
            calendar = CalendarConnection(
                status=row.status,
                has_refresh_token=bool(row.refresh_token),
                account_email=row.account_email,
            )
    return build_integrations_response(settings, _health(request), calendar)


@router.post("/google/calendar/connect", response_model=ConnectResponse)
async def connect_google_calendar(
    body: ConnectRequest,
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ConnectResponse:
    await ensure_local_user(session)
    client_id = settings.google_client_id.get_secret_value()
    client_secret = settings.google_client_secret.get_secret_value()
    if not client_id.strip() or not client_secret.strip() or not settings.google_redirect_uri.strip():
        raise ProviderNotConfigured(
            "Google Calendar is selected but no OAuth client is configured."
        )
    return_path = await resolve_return_path(session, body.return_path)
    url = await start_connect(
        OAuthConnectionRepository(session),
        user_id=LOCAL_USER_ID,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=settings.google_redirect_uri,
        return_path=return_path,
        now=datetime.now(UTC),
    )
    return ConnectResponse(authorization_url=url)


@router.get("/google/calendar/callback")
async def google_calendar_callback(
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    await ensure_local_user(session)
    client = httpx.AsyncClient(timeout=TIMEOUT)
    try:
        target = await finish_callback(
            OAuthConnectionRepository(session),
            client,
            code=code,
            state=state,
            error=error,
            client_id=settings.google_client_id.get_secret_value(),
            client_secret=settings.google_client_secret.get_secret_value(),
            redirect_uri=settings.google_redirect_uri,
            base_url=settings.app_base_url,
            now=datetime.now(UTC),
        )
    finally:
        await client.aclose()
    return RedirectResponse(target, status_code=302)


@router.delete("/google/calendar/disconnect", status_code=204)
async def disconnect_google_calendar(session: AsyncSession = Depends(get_db)) -> Response:
    await ensure_local_user(session)
    await OAuthConnectionRepository(session).delete(LOCAL_USER_ID)
    return Response(status_code=204)
