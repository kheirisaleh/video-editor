from typing import Any, Protocol

from studio.worker.context import StepContext


class StepError(RuntimeError):
    """A failure with a message that is meant to be shown to the user."""


class Step(Protocol):
    name: str

    def run(self, ctx: StepContext) -> dict[str, Any]: ...
