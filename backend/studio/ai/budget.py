"""AI spending: record what every model call cost and stop before a limit is crossed.

Two limits from the settings page: a monthly budget and a budget per workflow. Before a
call the expected cost is checked against what is left; after the call the real token
counts from the provider are recorded. When a limit would be crossed the call raises
`BudgetExceeded`, an `AiError`, so the step falls back to the rule based editor.

The check happens before each call, so the real spend can pass a limit by at most the
difference between one call's estimate and its real cost. For a hard guarantee set a
spend limit in the provider's console as well.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from studio.ai.client import AiClient, AiError, Image, Part, Usage
from studio.ai.settings import AiSettings
from studio.db import session_scope
from studio.models import AiUsage

# US dollars per million tokens: input, output. Cache reads cost a tenth of input,
# cache writes a quarter more than input.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
UNKNOWN_CLAUDE_PRICE = (10.0, 50.0)  # be conservative with models not in the table

# Expected size of one answer, thinking included, used for the check before a call.
EXPECTED_OUTPUT_TOKENS = 2500
IMAGE_TOKENS = 400  # a 384 px wide frame is about 350 tokens


class BudgetExceeded(AiError):
    pass


def price(provider: str, model: str) -> tuple[float, float]:
    if provider != "anthropic":
        return (0.0, 0.0)  # local or self hosted models cost no API money
    return PRICES.get(model, UNKNOWN_CLAUDE_PRICE)


def cost(provider: str, usage: Usage) -> float:
    inp, out = price(provider, usage.model)
    return (
        usage.input_tokens * inp
        + usage.cache_read_tokens * inp * 0.1
        + usage.cache_write_tokens * inp * 1.25
        + usage.output_tokens * out
    ) / 1_000_000


def estimate(provider: str, model: str, system: str, parts: list[Part]) -> float:
    images = sum(1 for p in parts if isinstance(p, Image))
    chars = len(system) + sum(len(p) for p in parts if isinstance(p, str))
    usage = Usage(
        model, input_tokens=images * IMAGE_TOKENS + chars // 3, output_tokens=EXPECTED_OUTPUT_TOKENS
    )
    return cost(provider, usage)


def month_start() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC).replace(tzinfo=None)


def spent(workflow_id: str | None = None, since: datetime | None = None) -> float:
    with session_scope() as s:
        q = select(func.coalesce(func.sum(AiUsage.cost_usd), 0.0))
        if workflow_id is not None:
            q = q.where(AiUsage.workflow_id == workflow_id)
        if since is not None:
            q = q.where(AiUsage.created_at >= since)
        return float(s.scalar(q) or 0.0)


def summary(settings: AiSettings) -> dict[str, Any]:
    with session_scope() as s:
        calls = s.scalar(select(func.count(AiUsage.id)).where(AiUsage.created_at >= month_start()))
    month = spent(since=month_start())
    return {
        "month_spent": round(month, 6),
        "month_budget": settings.monthly_budget_usd,
        "month_calls": int(calls or 0),
        "workflow_budget": settings.workflow_budget_usd,
    }


class BudgetedClient:
    """Wraps a client: checks the limits before a call and records the cost after it."""

    def __init__(
        self, inner: AiClient, settings: AiSettings, workflow_id: str | None, step: str
    ) -> None:
        self.inner = inner
        self.settings = settings
        self.workflow_id = workflow_id
        self.step = step
        self.name = inner.name

    def json(
        self,
        *,
        system: str,
        parts: list[Part],
        schema: dict[str, Any],
        vision: bool = False,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        provider = self.settings.provider
        model = self.settings.model_for(vision)
        expected = estimate(provider, model, system, parts)
        if provider == "anthropic":
            self._check(expected)
        try:
            return self.inner.json(
                system=system, parts=parts, schema=schema, vision=vision, max_tokens=max_tokens
            )
        finally:
            usage = getattr(self.inner, "last_usage", None)
            if usage is not None:
                self._record(usage)
                self.inner.last_usage = None  # type: ignore[attr-defined]

    def _check(self, expected: float) -> None:
        monthly = self.settings.monthly_budget_usd
        if monthly > 0:
            left = monthly - spent(since=month_start())
            if expected > left:
                raise BudgetExceeded(
                    f"the monthly AI budget of ${monthly:.2f} is used up "
                    f"(${max(left, 0):.2f} left); raise it in Settings or wait for next month"
                )
        per_workflow = self.settings.workflow_budget_usd
        if per_workflow > 0 and self.workflow_id is not None:
            left = per_workflow - spent(workflow_id=self.workflow_id)
            if expected > left:
                raise BudgetExceeded(
                    f"this video reached its AI budget of ${per_workflow:.2f}; "
                    f"the rest is edited without AI"
                )

    def _record(self, usage: Usage) -> None:
        with session_scope() as s:
            s.add(AiUsage(
                workflow_id=self.workflow_id, step=self.step, provider=self.settings.provider,
                model=usage.model, input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens, cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens,
                cost_usd=round(cost(self.settings.provider, usage), 6),
            ))  # fmt: skip
