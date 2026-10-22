from typing import Any

from studio.db import session_scope
from studio.media import ffmpeg
from studio.models import Clip
from studio.worker.context import StepContext
from studio.worker.steps import StepError


class IngestStep:
    """Probe every clip, create a thumbnail and a low resolution proxy for analysis."""

    name = "ingest"

    def run(self, ctx: StepContext) -> dict[str, Any]:
        with session_scope() as s:
            clips = [
                (c.id, c.original_name, c.filename)
                for c in s.query(Clip)
                .filter_by(workflow_id=ctx.workflow_id)
                .order_by(Clip.position)
            ]
        if not clips:
            raise StepError("no clips uploaded")

        thumbs_dir = ctx.work_dir / "thumbs"
        proxies_dir = ctx.work_dir / "proxies"
        thumbs_dir.mkdir(exist_ok=True)
        proxies_dir.mkdir(exist_ok=True)

        probes: dict[str, dict[str, Any]] = {}
        for clip_id, original_name, filename in clips:
            ctx.check_cancel()
            try:
                probes[clip_id] = ffmpeg.probe(ctx.upload_dir / filename)
            except ffmpeg.FFmpegError as exc:
                raise StepError(f"{original_name}: not a readable video ({exc})") from exc
            p = probes[clip_id]
            ctx.log(
                f"{original_name}: {p['width']}x{p['height']}, {p['duration']:.1f}s, "
                f"{p['fps']} fps, {p['orientation']}"
                + (f", HDR {p['hdr'].upper()} converted to SDR" if p["hdr"] else "")
            )

        total = sum(max(p["duration"], 0.1) for p in probes.values())
        done = 0.0
        for index, (clip_id, original_name, filename) in enumerate(clips, start=1):
            ctx.check_cancel()
            src = ctx.upload_dir / filename
            p = probes[clip_id]
            weight = max(p["duration"], 0.1)
            ctx.progress(done / total, f"clip {index}/{len(clips)}: {original_name}")

            thumb = thumbs_dir / f"{clip_id}.jpg"
            ffmpeg.thumbnail(src, thumb, at_seconds=min(1.0, p["duration"] * 0.1), hdr=p["hdr"])

            proxy = proxies_dir / f"{clip_id}.mp4"
            base = done

            def report(fraction: float, base: float = base, weight: float = weight) -> None:
                ctx.progress((base + fraction * weight) / total)

            ffmpeg.make_proxy(
                src,
                proxy,
                p["duration"],
                ctx.settings.proxy_height,
                on_progress=report,
                should_cancel=ctx.should_cancel,
                hdr=p["hdr"],
            )
            done += weight

            with session_scope() as s:
                clip = s.get(Clip, clip_id)
                if clip is not None:
                    clip.probe = p
                    clip.thumbnail = ctx.relative(thumb)
                    clip.proxy = ctx.relative(proxy)

        return {
            "clips": len(clips),
            "total_duration": round(total, 2),
            "vertical": sum(1 for p in probes.values() if p["orientation"] == "vertical"),
        }
