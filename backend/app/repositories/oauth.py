import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth import OAuthConnection, OAuthState
from app.services.calendar.time import as_utc


class OAuthConnectionRepository:
    """Only read path for stored Google tokens. Callers must not log the row."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> OAuthConnection | None:
        stmt = select(OAuthConnection).where(OAuthConnection.user_id == user_id)
        return await self.session.scalar(stmt)

    async def save_connection(
        self,
        *,
        user_id: uuid.UUID,
        refresh_token: str,
        access_token: str,
        access_token_expires_at: datetime,
        scopes: list[str],
        now: datetime,
    ) -> OAuthConnection:
        row = await self.get(user_id)
        if row is None:
            row = OAuthConnection(
                user_id=user_id,
                provider="google_calendar",
                refresh_token=refresh_token,
                access_token=access_token,
                access_token_expires_at=access_token_expires_at,
                scopes=list(scopes),
                account_email=None,
                status="connected",
                connected_at=now,
                updated_at=now,
            )
            self.session.add(row)
        else:
            row.provider = "google_calendar"
            row.refresh_token = refresh_token
            row.access_token = access_token
            row.access_token_expires_at = access_token_expires_at
            row.scopes = list(scopes)
            row.account_email = None
            row.status = "connected"
            row.updated_at = now
        await self.session.flush()
        return row

    async def update_access_token(
        self,
        row: OAuthConnection,
        *,
        refresh_token: str,
        access_token: str,
        access_token_expires_at: datetime,
        now: datetime,
    ) -> None:
        row.refresh_token = refresh_token
        row.access_token = access_token
        row.access_token_expires_at = access_token_expires_at
        row.status = "connected"
        row.updated_at = now
        await self.session.flush()

    async def mark_revoked(self, user_id: uuid.UUID, *, now: datetime) -> None:
        row = await self.get(user_id)
        if row is None:
            return
        row.status = "revoked"
        row.access_token = None
        row.access_token_expires_at = None
        row.updated_at = now
        await self.session.flush()

    async def delete(self, user_id: uuid.UUID) -> None:
        row = await self.get(user_id)
        if row is not None:
            await self.session.delete(row)
            await self.session.flush()

    async def create_state(
        self,
        *,
        user_id: uuid.UUID,
        state_hash: str,
        return_path: str,
        expires_at: datetime,
    ) -> OAuthState:
        row = OAuthState(
            user_id=user_id,
            state_hash=state_hash,
            return_path=return_path,
            expires_at=expires_at,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def consume_state(self, state_hash: str, *, now: datetime) -> OAuthState | None:
        stmt = select(OAuthState).where(OAuthState.state_hash == state_hash)
        row = await self.session.scalar(stmt)
        if row is None or row.consumed_at is not None or as_utc(row.expires_at) <= as_utc(now):
            return None
        row.consumed_at = now
        await self.session.flush()
        return row
