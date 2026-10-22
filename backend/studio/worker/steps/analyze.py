import json
from typing import Any

from studio.analysis.footage import analyze_clip
from studio.db import session_scope
from studio.models import Clip
from studio.worker.context import StepContext
from studio.worker.steps import StepError

ANALYSIS_FILE = "analysis.json"


class AnalyzeStep:
    """Find shots and score candidate segments of every clip."""

    name = "analyze"

    def run(self, ctx: StepContext) -> dict[str, Any]:
        with session_scope() as s:
            clips = [
                (c.id, c.original_name, c.proxy, c.probe)
                for c in s.query(Clip)
                .filter_by(workflow_id=ctx.workflow_id)
                .order_by(Clip.position)
            ]
        if not clips:
            raise StepError("no clips to analyze")

        results = []
        for index, (clip_id, name, proxy, probe) in enumerate(clips):
            ctx.check_cancel()
            if not proxy:
                raise StepError(f"{name}: proxy missing, run ingest again")
            ctx.progress(index / len(clips), f"clip {index + 1}/{len(clips)}: {name}")

            def report(fraction: float, index: int = index) -> None:
                ctx.progress((index + fraction) / len(clips))

            analysis = analyze_clip(clip_id, ctx.settings.data_dir / proxy, report)
            data = analysis.to_dict()
            data["name"] = name
            data["source_width"] = (probe or {}).get("width", analysis.width)
            data["source_height"] = (probe or {}).get("height", analysis.height)
            results.append(data)
            ctx.log(
                f"{name}: {len(analysis.shots)} shot(s), {len(analysis.segments)} usable "
                f"segment(s), best score {max((s.score for s in analysis.segments), default=0):.2f}"
            )

        (ctx.work_dir / ANALYSIS_FILE).write_text(json.dumps({"clips": results}, indent=1))
        usable = sum(len(c["segments"]) for c in results)
        if usable == 0:
            raise StepError("no usable moments found in the footage (too short or too dark)")
        return {"clips": len(results), "segments": usable}
