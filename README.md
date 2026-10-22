# Studio

Self hosted service that turns raw product footage into ready to post TikTok videos in the creator's own aesthetic. Upload clips from the phone, add the product link or description and an optional idea in Persian, and follow every workflow live while it waits in the queue and runs.

See [docs/DESIGN.md](docs/DESIGN.md) for the full design, the reference style analysis and the build phases.

## Status

Working end to end without any AI model:

* Installable web app (PWA) in English that works on phone and desktop. Product text and idea prompt accept English or Persian.
* Workflows with streamed footage upload, product link or description and an idea prompt
* Queue that runs one workflow at a time, with cancel, retry and resume after a restart
* Live progress, step status and logs over WebSocket
* Pipeline: **ingest** (probe, thumbnails, proxies), **analyze** (shot detection, sharpness, exposure, shake, face and subject position), **plan** (three edit plans with a rule based planner) and **render** (1080x1920 TikTok MP4 with styled text overlays, colour emoji, music, a silent copy, cover and post caption)

Known limits of the rule based planner, which the language model planner (next phase) removes:

* It cannot see what a shot shows, so overlay texts are not matched to the content of each shot and the hook shot is chosen by image quality, not by content.
* It cannot translate, so Persian product text and the idea prompt are not used for the overlays.

Music: put royalty free tracks (mp3, m4a, wav) into `data/music`. Each variant uses a different track. Without music the videos are rendered with a silent audio track.

## Run with Docker (home server)

```bash
docker compose up -d --build
```

Open `http://<server-ip>:8000` on the phone or desktop. On the phone use "Add to Home Screen" to install it like an app.

| Variable | Default | Meaning |
|---|---|---|
| `STUDIO_PORT` | `8000` | Port on the host |
| `STUDIO_DATA` | `./data` | Folder on the host for uploads, exports and the database |

Everything lives in the data folder:

```
data/
  studio.db          workflows, steps, events
  uploads/<id>/      original footage
  work/<id>/         thumbnails, proxies, analysis
  exports/<id>/      finished videos
```

## Development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22, FFmpeg.

```bash
# backend API on :8000
cd backend
uv sync
STUDIO_DATA_DIR=../data uv run uvicorn studio.api.main:app --reload

# worker, in a second terminal
cd backend
STUDIO_DATA_DIR=../data uv run studio-worker

# frontend dev server on :5173, proxies /api to :8000
cd frontend
npm install
npm run dev
```

Checks:

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run typecheck
```

## Architecture

```
browser (PWA) ──HTTP/WebSocket──> API (FastAPI) ──> SQLite <── worker ──> FFmpeg
```

The API and the worker are separate processes that share the data folder. The worker writes every progress update as an event into the database, and the API streams those events to the browser. Each pipeline step stores its result, so a failed or interrupted workflow resumes at the step where it stopped.
