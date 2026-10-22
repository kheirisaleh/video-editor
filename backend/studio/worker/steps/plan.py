import json
from pathlib import Path
from typing import Any

from studio.config import Settings
from studio.db import session_scope
from studio.models import Workflow
from studio.planning.baseline import ProductInfo, plan_variants
from studio.planning.schema import EditPlan, PlanMusic
from studio.worker.context import StepContext
from studio.worker.steps import StepError
from studio.worker.steps.analyze import ANALYSIS_FILE

MUSIC_EXTENSIONS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"}


def music_library(settings: Settings) -> list[PlanMusic]:
    if not settings.music_dir.is_dir():
        return []
    return [
        PlanMusic(path=p.relative_to(settings.data_dir).as_posix(), title=p.stem)
        for p in sorted(settings.music_dir.iterdir())
        if p.suffix.lower() in MUSIC_EXTENSIONS
    ]


def plans_dir(work_dir: Path) -> Path:
    path = work_dir / "plans"
    path.mkdir(exist_ok=True)
    return path


def load_plans(work_dir: Path) -> list[EditPlan]:
    return [
        EditPlan.model_validate_json(p.read_text())
        for p in sorted(plans_dir(work_dir).glob("variant_*.json"))
    ]


class PlanStep:
    """Turn the analysis and the product info into three edit plans."""

    name = "plan"

    def run(self, ctx: StepContext) -> dict[str, Any]:
        analysis_path = ctx.work_dir / ANALYSIS_FILE
        if not analysis_path.is_file():
            raise StepError("analysis missing, run the analyze step again")
        analysis = json.loads(analysis_path.read_text())

        with session_scope() as s:
            wf = s.get(Workflow, ctx.workflow_id)
            assert wf is not None
            info = ProductInfo(wf.title, wf.product_text, wf.product_url, wf.prompt)

        music = music_library(ctx.settings)
        if not music:
            ctx.log("music library is empty, videos are rendered without music", "warning")
        try:
            plans = plan_variants(analysis, info, music)
        except ValueError as exc:
            raise StepError(str(exc)) from exc

        target = plans_dir(ctx.work_dir)
        for old in target.glob("variant_*.json"):
            old.unlink()
        for i, plan in enumerate(plans, start=1):
            (target / f"variant_{i}.json").write_text(plan.model_dump_json(indent=1))
            ctx.log(
                f"variant {i} ({plan.label}): {len(plan.segments)} shots, "
                f"{plan.duration:.1f}s, {len(plan.texts)} texts"
            )
        for note in dict.fromkeys(n for p in plans for n in p.notes):
            ctx.log(note, "warning")
        return {
            "planner": "rule based",
            "variants": [
                {"label": p.label, "duration": round(p.duration, 2), "shots": len(p.segments)}
                for p in plans
            ],
        }
