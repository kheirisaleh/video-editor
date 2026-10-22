"""User facing options: global defaults in the settings page, overridable per workflow."""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from studio.models import AppSetting

DEFAULT_HASHTAGS = ["#tiktokmademebuyit", "#tiktokshopmademebuyit"]


class RenderOptions(BaseModel):
    variants: int = Field(default=3, ge=1, le=3)
    min_duration: float = Field(default=12.0, ge=5, le=180)
    max_duration: float = Field(default=30.0, ge=5, le=180)
    music: bool = True
    music_track: str | None = Field(default=None, description="file name, empty for automatic")
    beat_sync: bool = True
    texts: bool = True
    emoji: bool = True
    call_to_action: bool = True
    text_style: Literal["auto", "sans", "serif"] = "auto"
    silent_copy: bool = True
    quality: Literal["standard", "high"] = "high"
    hashtags: list[str] = Field(default_factory=lambda: list(DEFAULT_HASHTAGS))
    disclosure: str = Field(default="Pr sample, no payment received.", max_length=300)

    @model_validator(mode="after")
    def _range(self) -> "RenderOptions":
        if self.min_duration > self.max_duration:
            raise ValueError("minimum length must not be longer than maximum length")
        self.hashtags = [
            h if h.startswith("#") else f"#{h}" for h in (t.strip() for t in self.hashtags) if h
        ]
        if self.music_track == "":
            self.music_track = None
        return self


DEFAULTS_KEY = "render_defaults"


def load_defaults(session: Session) -> RenderOptions:
    row = session.get(AppSetting, DEFAULTS_KEY)
    if row is None:
        return RenderOptions()
    try:
        return RenderOptions.model_validate(row.value)
    except ValueError:
        return RenderOptions()


def save_defaults(session: Session, options: RenderOptions) -> None:
    row = session.get(AppSetting, DEFAULTS_KEY)
    if row is None:
        session.add(AppSetting(key=DEFAULTS_KEY, value=options.model_dump()))
    else:
        row.value = options.model_dump()


def merge(base: RenderOptions, overrides: dict[str, Any] | None) -> RenderOptions:
    data = base.model_dump()
    data.update(overrides or {})
    return RenderOptions.model_validate(data)


def workflow_options(session: Session, stored: dict[str, Any] | None) -> RenderOptions:
    """Options of a workflow; older workflows without stored options use the defaults."""
    return merge(load_defaults(session), stored)
