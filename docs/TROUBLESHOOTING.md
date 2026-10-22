# Troubleshooting

How to find out what went wrong, on the server or locally.

## 1. Where to look

| Source | Command or path |
|---|---|
| Worker log (pipeline, FFmpeg, AI errors) | `docker compose logs -f worker` |
| API log (uploads, requests) | `docker compose logs -f api` |
| Step status, errors and results | workflow page, or `curl http://<server>:8000/api/workflows/<id>` |
| Live events (progress, log lines) | `data/studio.db`, table `events` |
| Everything a workflow produced | `data/work/<id>/` and `data/exports/<id>/` |

Files in `data/work/<id>/`:

| File | Written by | Contains |
|---|---|---|
| `proxies/*.mp4`, `thumbs/*.jpg` | ingest | low resolution SDR copies used for analysis |
| `product.json` | product | product card and whether the product page could be read |
| `analysis.json` | analyze | shots and scored candidate moments per clip (ids like `c2s3`) |
| `labels.json` | understand | what the vision model saw in each moment |
| `plans/variant_N.json` | plan | the exact edit: segments, texts, music, caption |

`data/music/.analysis/` holds the cached beat analysis of each track.

## 2. Reproduce a workflow locally

1. Copy `data/uploads/<id>/` (and `data/music/` if music matters) from the server.
2. Start the app locally (README, Development) with a fresh data folder.
3. Create a workflow with the same product text, prompt and options, upload the clips.
4. Or skip the UI and render a saved plan directly:

   ```bash
   cd backend
   uv run python - <<'EOF'
   from pathlib import Path
   from studio.planning.schema import EditPlan
   from studio.render.video import SourceClip, render_plan
   from studio.media.ffmpeg import probe

   plan = EditPlan.model_validate_json(Path("variant_1.json").read_text())
   clips = {}
   for path in Path("uploads").iterdir():
       p = probe(path)
       clips[path.stem] = SourceClip(path, p["width"], p["height"], p["hdr"])
   render_plan(plan, clips, music=None, out=Path("out.mp4"), scratch=Path("scratch"))
   EOF
   ```

   Upload file names are `<clip id>.<ext>`, which matches `clip_id` in the plan.

## 3. Run again from a step

After fixing something or changing options, there is no need to start over:

```bash
curl -X POST "http://<server>:8000/api/workflows/<id>/rerun?from=plan"
```

`from` can be `ingest`, `product`, `analyze`, `understand`, `plan` or `render`. Earlier steps
keep their results. The "Edit again" button does the same from `product`.

## 4. Look at an output frame by frame

Contact sheet with timestamps (16 frames over the whole video):

```bash
f=data/exports/<id>/variant_1.mp4
d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
ffmpeg -v error -y -i "$f" -vf "fps=16/$d,scale=200:-1,drawtext=text='%{pts\:hms}':x=4:y=4:fontsize=14:fontcolor=yellow:box=1:boxcolor=black,tile=8x2" -frames:v 1 sheet.jpg
```

Single full resolution frame: `ffmpeg -ss 2.5 -i "$f" -frames:v 1 frame.png`

Technical facts and loudness:

```bash
ffprobe -v error -show_entries stream=codec_name,profile,width,height,r_frame_rate,pix_fmt,color_space -of compact "$f"
ffmpeg -hide_banner -i "$f" -af ebur128 -f null - 2>&1 | grep " I:"
```

Check: text readable and not over faces, no repeated clip back to back, cuts on the beat,
colours natural (not grey), length inside the chosen range, loudness about −16 LUFS.

## 5. Common problems

| Symptom | Likely cause | What to do |
|---|---|---|
| Colours look grey and flat | HDR clip not detected | `ffprobe` the upload; `color_transfer` should be `arib-std-b67` or `smpte2084`. Extend `hdr_kind` in `media/ffmpeg.py` with a test |
| Uploaded clips look softer than on the phone | Safari compressed them while picking from Photos | Pick through the Files app, or set iPhone Photos transfer to "Keep Originals" |
| "AI model unavailable" | model server down, wrong URL or key | Settings, Test connection; for Ollama check `OLLAMA_HOST=0.0.0.0` and the firewall |
| Texts do not match the shots | no model configured, or the understand step was skipped | Configure a model, then "Edit again" |
| A local model returns broken JSON | model too small or no JSON mode | Lower "Shots per request"; try a larger model |
| "Not enough usable footage" | clips too short or too dark for the minimum length | Lower the minimum length or add footage |
| Cuts feel off the beat | unusual track (no clear beat, tempo changes) | Check `data/music/.analysis/<track>.json`; turn off "Cut on the beat" for that track |
| Emoji are missing or look like Noto | emoji images not installed | Settings, System, Emoji should say "Apple emoji images"; rebuild the image or run `scripts/fetch-emoji.sh` |
| Workflow stays "Queued" | worker not running | `docker compose ps`; `docker compose logs worker` |
| Disk full | footage and exports pile up | Delete old workflows in the UI; check Settings, System, Storage |

## 6. Reporting a bug

Open an issue with the bug template. Include the workflow id, the failing step, the
error text from the workflow page, the relevant lines of `docker compose logs worker`,
and, for visual problems, a contact sheet of the output.
