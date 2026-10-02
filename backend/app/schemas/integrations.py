from typing import Literal

from pydantic import BaseModel


class ProviderStatus(BaseModel):
    key: str
    label: str
    mode: str
    status: Literal["ready", "unavailable"]
    detail: str


class IntegrationsResponse(BaseModel):
    event_provider: ProviderStatus
    place_provider: ProviderStatus
    calendar_provider: ProviderStatus
    openai_configured: bool
    timezone: str
    demo_mode: bool
