import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import app.models  # noqa: F401
import pytest
from app.core.clock import FrozenClock
from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_engine, create_session_factory
from app.repositories.users import ensure_local_user
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

CHICAGO = ZoneInfo("America/Chicago")
FROZEN_NOW = datetime(2026, 10, 2, 15, 0, tzinfo=CHICAGO)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'nemi.db'}",
        openai_api_key="",
        auto_create_schema=True,
        app_timezone="America/Chicago",
    )


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(FROZEN_NOW)


@pytest.fixture
async def session_factory(settings: Settings) -> async_sessionmaker[AsyncSession]:
    engine = create_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    async with factory() as session:
        await ensure_local_user(session)
        await session.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
def plan_id() -> uuid.UUID:
    return uuid.uuid4()
