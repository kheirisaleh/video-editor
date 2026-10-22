import json
from pathlib import Path
from typing import Any

from studio import music as library
from studio.config import Settings
from studio.db import session_scope
from studio.models import Workflow
from studio.options import RenderOptions, workflow_options
from studio.planning.baseline import STRATEGIES, MusicChoice, ProductInfo, plan_variants
from studio.planning.schema import EditPlan, PlanMusic
from studio.worker.context import StepContext
from studio.worker.steps import StepError
from studio.worker.steps.analyze import ANALYSIS_FILE


def plans_dir(work_dir: Path) -> Path:
    path = work_dir / "plans"
    path.mkdir(exist_ok=True)
    return path


def load_plans(work_dir: Path) -> list[EditPlan]:
    return [
        EditPlan.model_validate_json(p.read_text())
        for p in sorted(plans_dir(work_dir).glob("variant_*.json"))
    ]


def music_choices(
    settings: Settings, options: RenderOptions, ctx: StepContext
) -> list[MusicChoice]:
    """Tracks for the variants: the chosen one, or the library ordered by energy.

    With several tracks the short hook gets the fastest one and the soft vibe the
    calmest, which suits each strategy.
    """
    if not options.music:
        return []
    if options.music_track:
        path = library.find(settings.music_dir, options.music_track)
        if path is None:
            raise StepError(f"music track '{options.music_track}' is not in the library")
        paths = [path]
    else:
        paths = library.tracks(settings.music_dir)
    if not paths:
        ctx.log("music library is empty, videos are rendered without music", "warning")
        return []

    choices = []
    for path in paths:
        ctx.check_cancel()
        info = library.beat_info(path)
        if info is None:
            ctx.log(
                f"{path.name}: could not analyse beats, cuts will not follow the music", "warning"
            )
        choices.append(MusicChoice(
            PlanMusic(path=path.relative_to(settings.data_dir).as_posix(), title=path.stem),
            info,
        ))  # fmt: skip
    if len(choices) > 1:
        by_tempo = sorted(choices, key=lambda c: c.beats.tempo if c.beats else 0, reverse=True)
        wanted = {"hook": 0, "story": len(by_tempo) // 2, "vibe": len(by_tempo) - 1}
        choices = [by_tempo[wanted[s.key]] for s in STRATEGIES[: options.variants]]
        if len({c.music.path for c in choices}) < len(choices):
            choices = by_tempo  # fall back to rotation when the spread picks duplicates
    for c in choices[: options.variants]:
        if c.beats:
            ctx.log(f"music {c.music.title}: {c.beats.tempo:.0f} BPM")
    return choices


class PlanStep:
    """Turn the analysis, the music and the product info into edit plans."""

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
            options = workflow_options(s, wf.options)

        ctx.progress(0.1, "analysing music")
        music = music_choices(ctx.settings, options, ctx)
        ctx.progress(0.7, "planning edits")
        try:
            plans = plan_variants(analysis, info, options, music)
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
