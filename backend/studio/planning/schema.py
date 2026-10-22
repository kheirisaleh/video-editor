"""The edit plan: everything the renderer needs, nothing it has to guess.

Planners (rule based now, language models later) produce this structure; the renderer
turns it into a video deterministically.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TextStyle = Literal["sans", "serif"]
TextAnimation = Literal["fade", "typewriter", "none"]


class PlanSegment(BaseModel):
    clip_id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    crop_x: float = Field(default=0.5, ge=0, le=1, description="horizontal centre of the 9:16 crop")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    gamma: float = Field(default=1.0, ge=0.6, le=1.6, description="exposure match to other shots")

    @property
    def duration(self) -> float:
        return (self.end - self.start) / self.speed

    @model_validator(mode="after")
    def _ordered(self) -> "PlanSegment":
        if self.end <= self.start:
            raise ValueError("segment end must be after start")
        return self


class PlanText(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    y: float = Field(default=0.58, ge=0.05, le=0.95, description="vertical centre, 0 top, 1 bottom")
    animation: TextAnimation = "fade"


class PlanMusic(BaseModel):
    path: str
    start: float = 0.0
    title: str = ""


class EditPlan(BaseModel):
    strategy: str
    label: str
    style: TextStyle = "sans"
    segments: list[PlanSegment] = Field(min_length=1)
    texts: list[PlanText] = Field(default_factory=list)
    music: PlanMusic | None = None
    caption: str = ""
    notes: list[str] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.segments)

    @model_validator(mode="after")
    def _texts_inside(self) -> "EditPlan":
        total = self.duration
        for text in self.texts:
            if text.end <= text.start:
                raise ValueError(f"text '{text.text[:20]}' ends before it starts")
            if text.start >= total:
                raise ValueError(f"text '{text.text[:20]}' starts after the video ends")
            text.end = min(text.end, total)
        return self
