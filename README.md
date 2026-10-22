# Studio

Self hosted service that turns raw product footage into ready to post TikTok videos in the creator's own aesthetic. Upload clips from the phone, add the product link or description and an optional idea in Persian, and follow every workflow live while it waits in the queue and runs.

See [docs/DESIGN.md](docs/DESIGN.md) for the full design, the reference style analysis and the build phases.

## Status

Phase 0 is done:

* Installable web app (PWA) in Persian, right to left, works on phone and desktop
* Create workflows with footage upload (streamed, with per file progress), product link, product text and idea prompt
* Queue that runs one workflow at a time, with cancel, retry and resume after a restart
* Live progress, step status and logs over WebSocket
* Ingest step: probes every clip, creates thumbnails and low resolution proxies for analysis

Rendering, footage analysis, AI planning, product scraping and the music bank follow in the next phases.

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
