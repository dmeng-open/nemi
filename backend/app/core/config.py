from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.ranking import RankingWeights


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nemi"
    event_provider: Literal["mock", "ticketmaster"] = "mock"
    place_provider: Literal["mock", "google"] = "mock"
    calendar_provider: Literal["local", "google"] = "local"
    app_timezone: str = "America/Chicago"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    log_level: str = "INFO"

    ticketmaster_api_key: SecretStr = SecretStr("")
    google_places_api_key: SecretStr = SecretStr("")
    google_client_id: SecretStr = SecretStr("")
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: str = ""

    rank_weight_preference: float = 0.35
    rank_weight_schedule: float = 0.25
    rank_weight_distance: float = 0.15
    rank_weight_price: float = 0.10
    rank_weight_quality: float = 0.15

    auto_create_schema: bool = False

    @field_validator("app_timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key.get_secret_value().strip())

    @property
    def ranking_weights(self) -> RankingWeights:
        return RankingWeights(
            preference=self.rank_weight_preference,
            schedule=self.rank_weight_schedule,
            distance=self.rank_weight_distance,
            price=self.rank_weight_price,
            quality=self.rank_weight_quality,
        )

    def zone(self):
        from zoneinfo import ZoneInfo

        return ZoneInfo(self.app_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
