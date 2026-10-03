import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.core.exceptions import AppError, ProviderNotConfigured
from app.models.planning import PlanningSession
from app.models.user import LOCAL_USER_ID
from app.providers.http import TIMEOUT
from app.repositories.oauth import OAuthConnectionRepository

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
STATE_TTL = timedelta(minutes=10)
_PLAN_PATH = re.compile(
    r"^/plans/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)


class InvalidGrant(Exception):
    """Google rejected the refresh token."""


class TokenExchangeFailed(Exception):
    """The token endpoint did not return a usable token."""


@dataclass
class TokenBundle:
    refresh_token: str
    access_token: str
    expires_in: int

    def __repr__(self) -> str:
        return "TokenBundle(redacted)"


def hash_state(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


def new_state_nonce() -> str:
    return secrets.token_urlsafe(32)


def normalize_return_path(path: str | None) -> str:
    if path is None or path.strip() == "":
        return "/integrations"
    candidate = path.strip()
    if candidate != path and path is not None:
        # Preserve a deliberate check: surrounding whitespace is not a relative path.
        candidate = path
    if _rejected_path(candidate):
        raise _return_path_error()
    if candidate == "/integrations":
        return candidate
    if _PLAN_PATH.fullmatch(candidate):
        return candidate
    raise _return_path_error()


def _rejected_path(path: str) -> bool:
    if path != path.strip():
        return True
    lowered = path.lower()
    if "\\" in path or "?" in path or "#" in path:
        return True
    if path.startswith("//") or "://" in path:
        return True
    if lowered.startswith("/\\") or lowered.startswith("\\\\"):
        return True
    return False


def _return_path_error() -> AppError:
    return AppError(
        "Choose a return path of /integrations or an existing plan.",
        code="validation_error",
        status_code=422,
    )


async def resolve_return_path(session, path: str | None) -> str:
    normalized = normalize_return_path(path)
    if normalized == "/integrations":
        return normalized
    match = _PLAN_PATH.fullmatch(normalized)
    if match is None:
        raise _return_path_error()
    plan_id = uuid.UUID(match.group(1))
    plan = await session.get(PlanningSession, plan_id)
    if plan is None or plan.user_id != LOCAL_USER_ID:
        raise _return_path_error()
    return normalized


def authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": CALENDAR_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTHORIZE_URL}?{query}"


def browser_redirect(base_url: str, path: str, *, failed: bool) -> str:
    target = f"{base_url.rstrip('/')}{path}"
    if failed:
        return f"{target}?calendar=connect_failed"
    return target


def require_oauth_client(client_id: str, client_secret: str, redirect_uri: str) -> None:
    if not client_id.strip() or not client_secret.strip() or not redirect_uri.strip():
        raise ProviderNotConfigured(
            "Google Calendar is selected but no OAuth client is configured."
        )


async def start_connect(
    repository: OAuthConnectionRepository,
    *,
    user_id: uuid.UUID,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    return_path: str,
    now: datetime,
) -> str:
    require_oauth_client(client_id, client_secret, redirect_uri)
    nonce = new_state_nonce()
    await repository.create_state(
        user_id=user_id,
        state_hash=hash_state(nonce),
        return_path=return_path,
        expires_at=now + STATE_TTL,
    )
    return authorization_url(client_id=client_id, redirect_uri=redirect_uri, state=nonce)


async def exchange_authorization_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> TokenBundle:
    return await _token_request(
        client,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        require_refresh=True,
    )


async def refresh_access_token(
    client: httpx.AsyncClient,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> TokenBundle:
    bundle = await _token_request(
        client,
        {
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
        require_refresh=False,
    )
    if not bundle.refresh_token:
        bundle = TokenBundle(
            refresh_token=refresh_token,
            access_token=bundle.access_token,
            expires_in=bundle.expires_in,
        )
    return bundle


async def _token_request(
    client: httpx.AsyncClient,
    data: dict[str, str],
    *,
    require_refresh: bool,
) -> TokenBundle:
    try:
        response = await client.post(GOOGLE_TOKEN_URL, data=data, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise TokenExchangeFailed() from exc
    if response.status_code != 200:
        if _error_code(response) == "invalid_grant":
            raise InvalidGrant()
        raise TokenExchangeFailed()
    try:
        payload = response.json()
    except ValueError as exc:
        raise TokenExchangeFailed() from exc
    if not isinstance(payload, dict):
        raise TokenExchangeFailed()
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not isinstance(access_token, str) or not access_token:
        raise TokenExchangeFailed()
    if require_refresh and (not isinstance(refresh_token, str) or not refresh_token):
        raise TokenExchangeFailed()
    expires_raw = payload.get("expires_in") or 3600
    try:
        expires_in = int(expires_raw)
    except (TypeError, ValueError) as exc:
        raise TokenExchangeFailed() from exc
    stored_refresh = refresh_token if isinstance(refresh_token, str) else ""
    return TokenBundle(
        refresh_token=stored_refresh,
        access_token=access_token,
        expires_in=expires_in,
    )


def _error_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, str):
        return error
    return None


async def finish_callback(
    repository: OAuthConnectionRepository,
    client: httpx.AsyncClient,
    *,
    code: str | None,
    state: str | None,
    error: str | None,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    base_url: str,
    now: datetime,
) -> str:
    """Exchange the code and return a browser redirect. The URL has no code or token."""
    fallback = browser_redirect(base_url, "/integrations", failed=True)
    if not state:
        return fallback
    row = await repository.consume_state(hash_state(state), now=now)
    if row is None:
        return fallback
    failure = browser_redirect(base_url, row.return_path, failed=True)
    if error or not code:
        return failure
    try:
        require_oauth_client(client_id, client_secret, redirect_uri)
        bundle = await exchange_authorization_code(
            client,
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
    except (ProviderNotConfigured, InvalidGrant, TokenExchangeFailed, httpx.HTTPError):
        return failure
    await repository.save_connection(
        user_id=row.user_id,
        refresh_token=bundle.refresh_token,
        access_token=bundle.access_token,
        access_token_expires_at=now + timedelta(seconds=bundle.expires_in),
        scopes=[CALENDAR_SCOPE],
        now=now,
    )
    return browser_redirect(base_url, row.return_path, failed=False)
