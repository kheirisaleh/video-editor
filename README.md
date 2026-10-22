# Studio

Self hosted service that turns raw product footage into ready to post TikTok videos in the creator's own aesthetic. Upload clips from the phone, add the product link or description and an optional idea (English or Persian), and follow every workflow live while it waits in the queue and runs.

See [docs/DESIGN.md](docs/DESIGN.md) for the full design, the reference style analysis and the build phases.

## Quick start on the home server

Requirements: Docker with the Compose plugin.

```bash
git clone https://github.com/kheirisaleh/video-editor.git
cd video-editor
docker compose up -d --build
```

Open `http://<server-ip>:8000` on the phone or desktop. On the phone use "Add to Home Screen" to install it like an app. Then:

1. **Music**: add a few royalty free tracks (mp3, m4a, wav). They are analysed for tempo and beats on upload.
2. **Settings**: set your default video options once.
3. **New**: choose footage, add the product link or description, adjust the options if needed and start.

Update to a new version with `git pull && docker compose up -d --build`. Data is kept.

| Variable | Default | Meaning |
|---|---|---|
| `STUDIO_PORT` | `8000` | Port on the host |
| `STUDIO_DATA` | `./data` | Folder on the host for uploads, exports, music and the database |

Everything lives in the data folder, so backing it up backs up everything:

```
data/
  studio.db          workflows, steps, events, settings
  uploads/<id>/      original footage
  work/<id>/         thumbnails, proxies, analysis, edit plans
  exports/<id>/      finished videos, silent copies, covers, captions
  music/             music library
  fonts/             optional: Apple Color Emoji.ttc (see below)
```

## What it does

* Installable web app (PWA) in English for phone and desktop
* Queue that runs one workflow at a time, with cancel, retry and resume after a restart
* Live progress, step status and logs
* Pipeline:
  * **ingest**: probe, thumbnails, analysis proxies
  * **analyze**: shot detection, sharpness, exposure, shake, face and subject position
  * **plan**: up to three edit plans (short hook, unboxing story, soft vibe)
  * **render**: 1080x1920 H.264 TikTok video, cover, post caption, optional silent copy

### Options

Defaults are set on the Settings page; every workflow can override them.

| Option | Effect |
|---|---|
| Length (min, max) | Every variant lands inside the range: the short hook near the minimum, the story near the maximum |
| Variants | 1 to 3 videos per workflow |
| Music | On or off, automatic (different track per variant, the fastest for the short hook) or one fixed track |
| Cut on the beat | Cuts land on the music's beats, accurate to the frame |
| Also export without music | Silent copy for adding a trending sound inside TikTok |
| Text on video, emoji, "Link below the video" | Each can be switched off |
| Font | Auto, sans (TikTok Sans) or serif (Source Serif 4 with typewriter reveal) |
| Hashtags, disclosure | Used for the post caption |
| Quality | Best (slower encode) or faster |

### Quality details

* Fonts matched to the creator's reference videos: TikTok Sans and Source Serif 4 SemiBold
* Apple style emoji. The Docker image downloads the Apple emoji images from the `emoji-datasource-apple` package at build time; the artwork belongs to Apple, so it is not stored in this repository. For the highest resolution, copy `Apple Color Emoji.ttc` from a Mac (`/System/Library/Fonts/`) into `data/fonts/`.
* Text stays inside TikTok's safe area, moves away from faces and has a soft double shadow that stays readable on white backgrounds
* Horizontal clips are cropped to 9:16 around the detected face or subject
* Exposure is matched between shots; a gentle, natural grade
* Music starts on a downbeat, is loudness normalised to −16 LUFS and fades out

### Known limits of the rule based planner

These go away with the language model planner (next phase):

* It cannot see what a shot shows, so overlay texts are not matched to the content of each shot and the hook shot is chosen by image quality, not by content.
* It cannot translate, so Persian product text and the idea prompt are not used for the overlays.

## Development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22, FFmpeg.

```bash
# Apple style emoji for local development (once)
scripts/fetch-emoji.sh

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

## Licences

TikTok Sans and Source Serif 4 are under the SIL Open Font License (see `backend/studio/assets/fonts`). Music you add must allow commercial use, because product promotion counts as commercial use.
