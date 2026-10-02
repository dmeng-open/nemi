from typing import Literal

from pydantic import BaseModel

ConnectionState = Literal[
    "mock",
    "local",
    "not_configured",
    "configured",
    "oauth_required",
    "connected",
    "unhealthy",
]


class ProviderStatus(BaseModel):
    key: str
    label: str
    mode: str
    status: Literal["ready", "unavailable"]
    connection: ConnectionState
    detail: str
    account_email: str | None = None


class IntegrationsResponse(BaseModel):
    event_provider: ProviderStatus
    place_provider: ProviderStatus
    calendar_provider: ProviderStatus
    openai_configured: bool
    timezone: str
    demo_mode: bool


class ConnectRequest(BaseModel):
    return_path: str | None = None


class ConnectResponse(BaseModel):
    authorization_url: str
