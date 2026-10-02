from fastapi import APIRouter

from app.api.routes import calendar, integrations, plans, preferences

api_router = APIRouter()
api_router.include_router(plans.router)
api_router.include_router(preferences.router)
api_router.include_router(calendar.router)
api_router.include_router(integrations.router)
