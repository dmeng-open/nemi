from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def health_db(request: Request) -> dict[str, str]:
    factory = request.app.state.session_factory
    async with factory() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ok"}
