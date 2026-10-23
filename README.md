# Studio

Self hosted service that turns raw product footage into ready to post TikTok videos in the creator's own aesthetic. Upload clips from the phone, add the product link or description and an optional idea (English or Persian), and watch the videos being made live. Finished videos are saved to the phone with one tap.

Documentation:

* [docs/DESIGN.md](docs/DESIGN.md): design, reference style analysis, pipeline
* [CLAUDE.md](CLAUDE.md): rules for developing and fixing bugs (for people and AI assistants)
* [CONTRIBUTING.md](CONTRIBUTING.md): short development workflow
* [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): finding and reporting bugs

## Quick start on the home server

Requirements: Docker with the Compose plugin.

```bash
git clone https://github.com/kheirisaleh/video-editor.git
cd video-editor
docker compose up -d --build
```

Open `http://<server-ip>:8000` on the phone or desktop. On the phone use "Add to Home Screen" to install it like an app. The app has three tabs:

* **Videos**: every project with its cover, live progress and how many videos are ready. Open one to play the versions, **Save video** (on iPhone this opens the share sheet, so the video goes straight to Photos), **Copy caption**, or **Make new versions**.
* **Create**: four simple steps. Add your clips, the product link or a description, your idea in any language (optional), then pick the look (Mix, Clean, Elegant), the length (Short, Medium, Long) and whether you want music and text. **More options** has every setting from the table below.
* **Settings**: the AI assistant with its spending limits, the music library (add a few royalty free mp3, m4a or wav tracks; tempo and beats are analysed on upload), default video settings and storage.

## Connecting an AI model

The model watches your shots, picks the opening moment, matches every overlay text to the shot that shows it, writes in your style and understands Persian. Configure it on the Settings page:

| Provider | Server URL | Models |
|---|---|---|
| Claude API | (empty) | Default `claude-opus-5-5` for text and vision; API key from console.anthropic.com |
| Ollama on the gaming PC | `http://<pc-ip>:11434/v1` | A vision model such as `qwen2.5vl:7b` and a text model such as `qwen3:14b` |
| LM Studio, vLLM, llama.cpp | their OpenAI compatible `/v1` URL | as served |

For Ollama on another machine, start it so it listens on the network (`OLLAMA_HOST=0.0.0.0 ollama serve`) and pull the models first. Small local models work better with fewer **Shots per request**.

If the model is not configured or not reachable, the video is still made with the rule based editor and the project details say so. Turn on **Require the model** to fail instead; **Retry** then continues once the model is back. **Make new versions** on a finished project plans and renders again with the current options and model, without preparing the footage again.

### Spending limits

Claude is paid per use, so Settings has two limits: **per month** (default $10) and **per video** (default $1). Every model call is recorded with its real token cost, and before each call the expected cost is checked against what is left. When a limit would be crossed, the AI stops and the video is finished by the rule based editor, so a video is never lost because of the budget. Settings shows what was spent this month; the details of every project show its AI cost. A typical video with 8 clips costs about $0.20 with the default model and medium effort. Local models cost nothing and have no limit. For a hard guarantee, also set a spend limit in the Anthropic console.

The API key is stored on the server only and never sent back to the browser. Instead of the settings page it can also be given as the `STUDIO_AI_API_KEY` environment variable.

Update to a new version with `git pull && docker compose up -d --build`. Data is kept.

| Variable | Default | Meaning |
|---|---|---|
| `STUDIO_PORT` | `8000` | Port on the host |
| `STUDIO_BIND` | `0.0.0.0` | Host address to listen on; `127.0.0.1` when a reverse proxy such as Caddy is in front |
| `STUDIO_DATA` | `./data` | Folder on the host for uploads, exports, music and the database |
| `STUDIO_WORKER_CPUS` | `2` | CPU cores the render worker may use; it also runs with lower priority than other containers |
| `STUDIO_WORKER_MEMORY` | `6g` | Memory limit of the render worker (a 9 clip workflow peaked at about 3.2 GB) |
| `STUDIO_API_MEMORY` | `1g` | Memory limit of the web server |

Put them in a `.env` file next to `docker-compose.yml`.

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
  * **ingest**: probe, thumbnails, analysis proxies; iPhone HDR (HLG, Dolby Vision) is converted to natural SDR
  * **product**: reads the product link and builds an English product card from page, text and idea
  * **analyze**: shot detection, sharpness, exposure, shake, face and subject position
  * **understand** (AI): the vision model describes every usable moment and the feature it shows
  * **plan**: up to three edits (short hook, unboxing story, soft vibe); the model chooses shots, order and texts, the planner keeps timing, beats and length
  * **render**: 1080x1920 H.264 TikTok video, cover, post caption, optional silent copy

### Options

Defaults are set on the Settings page; every video can override them under **More options**.

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

### Without a model

The rule based editor cannot see what a shot shows, so overlay texts are not matched to the content of each shot and the opening shot is chosen by image quality. It cannot translate, so Persian product text and the idea prompt are not used for the overlays.

### Notes for the first run

* iPhone Safari may compress videos picked from the Photos library. If the uploaded clips look softer than the originals, pick them through the Files app instead, or set Settings, Photos, Transfer to Mac or PC to "Keep Originals".
* Without HTTPS the browser allows "Add to Home Screen" but not offline caching, and the copy button for captions may not work; the caption text can still be selected.
* There is no login. Keep port 8000 inside the home network.

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
