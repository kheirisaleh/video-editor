from typing import Any, Protocol

from studio.ai.client import AiClient, AiError, make_client
from studio.ai.settings import AiSettings, load_ai
from studio.db import session_scope
from studio.worker.context import StepContext


class StepError(RuntimeError):
    """A failure with a message that is meant to be shown to the user."""


class Step(Protocol):
    name: str

    def run(self, ctx: StepContext) -> dict[str, Any]: ...


def skipped(reason: str) -> dict[str, Any]:
    """Result of a step that had nothing to do; the pipeline marks it as skipped."""
    return {"skipped": reason}


def ai_client(ctx: StepContext) -> tuple[AiSettings, AiClient | None]:
    with session_scope() as s:
        settings = load_ai(s)
    try:
        return settings, make_client(settings)
    except AiError as exc:
        ai_failed(ctx, settings, exc)
        return settings, None


def ai_failed(ctx: StepContext, settings: AiSettings, exc: Exception) -> None:
    """Stop when the AI is required, otherwise warn and let the caller fall back."""
    if settings.required:
        raise StepError(f"AI model unavailable: {exc}. Retry when it is reachable.") from exc
    ctx.log(f"AI model unavailable ({exc}), using the rule based fallback", "warning")
