from typing import Any

from studio.db import session_scope
from studio.media.ffmpeg import probe
from studio.models import Clip, Workflow
from studio.options import workflow_options
from studio.render.video import SourceClip, cover, render_plan, strip_audio
from studio.worker.context import StepContext
from studio.worker.steps import StepError
from studio.worker.steps.plan import load_plans


class RenderStep:
    """Render every plan to a finished TikTok video plus cover and caption."""

    name = "render"

    def run(self, ctx: StepContext) -> dict[str, Any]:
        plans = load_plans(ctx.work_dir)
        if not plans:
            raise StepError("no edit plans found, run the plan step again")

        with session_scope() as s:
            clips = {
                c.id: SourceClip(
                    ctx.upload_dir / c.filename,
                    (c.probe or {}).get("width", 0),
                    (c.probe or {}).get("height", 0),
                )
                for c in s.query(Clip).filter_by(workflow_id=ctx.workflow_id)
            }
            wf = s.get(Workflow, ctx.workflow_id)
            options = workflow_options(s, wf.options if wf else None)

        export = ctx.export_dir
        for old in export.glob("variant_*"):
            old.unlink()

        outputs = []
        for i, plan in enumerate(plans, start=1):
            ctx.check_cancel()
            ctx.progress((i - 1) / len(plans), f"variant {i}/{len(plans)}: {plan.label}")
            missing = {s.clip_id for s in plan.segments} - clips.keys()
            if missing:
                raise StepError(f"plan {i} uses unknown clips {sorted(missing)}")
            music = ctx.settings.data_dir / plan.music.path if plan.music else None
            if music is not None and not music.is_file():
                ctx.log(
                    f"music file {plan.music.path} missing, rendering without music",  # type: ignore[union-attr]
                    "warning",
                )
                music = None

            video = export / f"variant_{i}.mp4"

            def report(fraction: float, i: int = i) -> None:
                ctx.progress((i - 1 + fraction * 0.95) / len(plans))

            render_plan(
                plan,
                clips,
                music,
                video,
                ctx.work_dir / "render" / f"v{i}",
                quality=options.quality,
                on_progress=report,
                should_cancel=ctx.should_cancel,
            )
            silent = None
            if music is not None and options.silent_copy:
                silent = export / f"variant_{i}_silent.mp4"
                strip_audio(video, silent)
            cover(video, export / f"variant_{i}.jpg")
            (export / f"variant_{i}.txt").write_text(plan.caption + "\n")

            info = probe(video)
            outputs.append(
                {
                    "index": i,
                    "label": plan.label,
                    "strategy": plan.strategy,
                    "duration": info["duration"],
                    "video": video.name,
                    "silent": silent.name if silent else None,
                    "cover": f"variant_{i}.jpg",
                    "caption": plan.caption,
                    "music": plan.music.title if plan.music and music else None,
                    "size_bytes": video.stat().st_size,
                }
            )
            ctx.log(
                f"variant {i} rendered: {info['duration']:.1f}s, "
                f"{video.stat().st_size / 1e6:.1f} MB"
            )
        return {"outputs": outputs}
