import json
from pathlib import Path
from typing import Any

from studio.ai.client import AiError
from studio.ai.product import ProductCard
from studio.ai.shots import ShotLabel, label_shots
from studio.db import session_scope
from studio.models import Clip
from studio.planning.baseline import candidates_from
from studio.worker.context import StepContext
from studio.worker.steps import ai_client, ai_failed, skipped
from studio.worker.steps.analyze import ANALYSIS_FILE
from studio.worker.steps.product import load_card

LABELS_FILE = "labels.json"


def load_labels(work_dir: Path) -> dict[str, ShotLabel]:
    path = work_dir / LABELS_FILE
    if not path.is_file():
        return {}
    return {k: ShotLabel.model_validate(v) for k, v in json.loads(path.read_text()).items()}


class UnderstandStep:
    """Let the vision model describe every candidate moment."""

    name = "understand"

    def run(self, ctx: StepContext) -> dict[str, Any]:
        (ctx.work_dir / LABELS_FILE).unlink(missing_ok=True)
        settings, client = ai_client(ctx)
        if client is None:
            return skipped("no AI model configured" if not settings.enabled else "AI unavailable")

        analysis = json.loads((ctx.work_dir / ANALYSIS_FILE).read_text())
        with session_scope() as s:
            proxies = {
                c.id: ctx.settings.data_dir / c.proxy
                for c in s.query(Clip).filter_by(workflow_id=ctx.workflow_id)
                if c.proxy
            }
        shots = [
            {"id": c.id, "proxy": proxies[c.clip_id], "start": c.start, "end": c.end}
            for c in candidates_from(analysis)
            if c.clip_id in proxies
        ]
        card = load_card(ctx.work_dir) or ProductCard(name="product")
        ctx.progress(0.02, f"{len(shots)} moments, {client.name}")
        try:
            labels = label_shots(
                client, shots, card, settings.shots_per_request,
                on_progress=lambda f: ctx.progress(f), should_cancel=ctx.should_cancel,
            )  # fmt: skip
        except AiError as exc:
            ai_failed(ctx, settings, exc)
            return skipped(f"AI unavailable: {exc}")
        ctx.check_cancel()
        (ctx.work_dir / LABELS_FILE).write_text(
            json.dumps({k: v.model_dump() for k, v in labels.items()}, indent=1)
        )
        for label in sorted(labels.values(), key=lambda v: v.id):
            feature = f", shows {label.feature}" if label.feature else ""
            ctx.log(
                f"{label.id}: {label.shot_type}, appeal {label.appeal}{feature}: "
                f"{label.description}"
            )
        return {"model": client.name, "labelled": len(labels), "moments": len(shots)}
