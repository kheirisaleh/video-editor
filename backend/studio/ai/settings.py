"""Which AI model the pipeline talks to. Configured in the settings page."""

import os
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from studio.models import AppSetting

AI_KEY = "ai"
CLAUDE_DEFAULT_MODEL = "claude-opus-5-5"

Provider = Literal["none", "anthropic", "openai"]


class AiSettings(BaseModel):
    provider: Provider = "none"
    base_url: str = Field(
        default="",
        description="openai: e.g. http://192.168.1.20:11434/v1 for Ollama; anthropic: empty",
    )
    api_key: str = ""
    text_model: str = ""
    vision_model: str = ""
    # medium keeps thinking, and so cost, moderate; it is enough for these short tasks.
    effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    shots_per_request: int = Field(default=4, ge=1, le=12)
    timeout: float = Field(default=300.0, ge=10, le=3600)
    required: bool = Field(
        default=False,
        description="fail the workflow when the model is unreachable instead of falling back",
    )
    monthly_budget_usd: float = Field(default=10.0, ge=0, le=10_000, description="0 = no limit")
    workflow_budget_usd: float = Field(default=1.0, ge=0, le=1_000, description="0 = no limit")

    @property
    def enabled(self) -> bool:
        return self.provider != "none"

    def model_for(self, vision: bool) -> str:
        chosen = (self.vision_model if vision else self.text_model) or self.text_model
        if chosen:
            return chosen
        if self.provider == "anthropic":
            return CLAUDE_DEFAULT_MODEL
        return self.vision_model

    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.provider == "anthropic":
            return os.environ.get("STUDIO_AI_API_KEY") or None  # SDK also reads ANTHROPIC_API_KEY
        return os.environ.get("STUDIO_AI_API_KEY") or None


class AiSettingsOut(BaseModel):
    """What the browser sees: the key itself never leaves the server."""

    provider: Provider
    base_url: str
    api_key_set: bool
    text_model: str
    vision_model: str
    effort: str
    shots_per_request: int
    timeout: float
    required: bool
    monthly_budget_usd: float
    workflow_budget_usd: float


class AiSettingsIn(BaseModel):
    provider: Provider = "none"
    base_url: str = ""
    api_key: str | None = Field(default=None, description="None keeps the stored key")
    text_model: str = ""
    vision_model: str = ""
    effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    shots_per_request: int = Field(default=4, ge=1, le=12)
    timeout: float = Field(default=300.0, ge=10, le=3600)
    required: bool = False
    monthly_budget_usd: float = Field(default=10.0, ge=0, le=10_000)
    workflow_budget_usd: float = Field(default=1.0, ge=0, le=1_000)


def load_ai(session: Session) -> AiSettings:
    row = session.get(AppSetting, AI_KEY)
    if row is None:
        return AiSettings()
    try:
        return AiSettings.model_validate(row.value)
    except ValueError:
        return AiSettings()


def save_ai(session: Session, incoming: AiSettingsIn) -> AiSettings:
    current = load_ai(session)
    data = incoming.model_dump()
    if incoming.api_key is None:
        data["api_key"] = current.api_key
    data["base_url"] = data["base_url"].strip().rstrip("/")
    settings = AiSettings.model_validate(data)
    row = session.get(AppSetting, AI_KEY)
    if row is None:
        session.add(AppSetting(key=AI_KEY, value=settings.model_dump()))
    else:
        row.value = settings.model_dump()
    return settings


def public(settings: AiSettings) -> AiSettingsOut:
    return AiSettingsOut(
        **settings.model_dump(exclude={"api_key"}),
        api_key_set=bool(settings.resolved_api_key()),
    )
