# Aesthetic TikTok Editor: Design

A self hosted service that turns raw product footage into ready to post TikTok videos in a chosen aesthetic. It runs on a home server, is used only inside the home network, and every AI component can be swapped from the UI.

## 1. Goal

The user receives product samples from TikTok Shop and films them (promo or unboxing). The videos have no voiceover and no original sound, only a background music track, and follow a visual aesthetic such as Clean Girl, Coquette, Grunge or Y2K.

For each workflow the user provides:

1. Several footage clips
2. A product description or a product link
3. An optional idea prompt written in Persian

The service understands the footage and the product, plans the best possible edit for the chosen aesthetic, and renders **three different variants** so the user can pick the best one. Uploads and exports are stored on the server.

## 2. Scope and constraints

| Topic | Decision |
|---|---|
| Target platform | TikTok only: 1080x1920, 9:16, H.264 + AAC, 30 fps |
| Audio | No voice, only music from the built in music bank |
| Variants | 3 per workflow, each with a different strategy |
| Concurrency | Workflows run one at a time, others wait in a queue |
| Access | Home network only, no login required at first |
| Models | Local, on another machine in the LAN, or external API, configurable per pipeline step |
| Hardware | Unknown yet, so every heavy step must be able to run on a remote machine |
| Priority | Output quality over speed |

## 3. Architecture

```
 Browser (phone / desktop, PWA)
        |  HTTP + WebSocket
        v
 +------------------+       +-------------------+
 |  API server      |<----->|  Database         |
 |  FastAPI         |       |  SQLite (Postgres |
 |                  |       |  later if needed) |
 +--------+---------+       +-------------------+
          | job queue (one job at a time)
          v
 +------------------+      model providers (HTTP)
 |  Worker          |----> * Ollama / vLLM on gaming PC
 |  pipeline steps  |----> * OpenAI compatible API
 |  FFmpeg render   |----> * local model path on server
 +--------+---------+
          v
   /data/uploads   /data/exports   /data/music
```

Components:

* **Frontend**: React + Vite, installable as a PWA so it feels like an app on the phone. Pages: new workflow, queue and live status, workflow detail with the 3 variants, music bank, settings.
* **API server**: Python + FastAPI. REST for CRUD, WebSocket for live progress events.
* **Worker**: separate process that takes the next queued workflow and runs the pipeline. Progress events (step, percent, log line, preview frame) are pushed to the UI.
* **Storage**: plain folders under one data directory, mounted as a Docker volume.
* **Deployment**: Docker Compose. One command to start everything.

## 4. Pipeline

Each workflow passes through these steps. Every step writes its result to the database, so a failed workflow can be resumed from the failed step instead of starting over.

### 4.1 Ingest
Probe each clip with ffprobe (resolution, rotation, fps, duration), create low resolution proxies for fast analysis, and extract thumbnails for the UI.

### 4.2 Product understanding
* If a link is given, open it with a headless browser (Playwright) and extract name, price, key features, images and reviews. TikTok Shop pages are heavy JavaScript pages and sometimes block bots, so the scraper uses a real browser and falls back to the text description when it fails.
* An LLM turns the raw page into a structured product card: name, category, 3 to 5 selling points, target audience, fitting aesthetic.

### 4.3 Footage analysis
Classic computer vision first, AI second. This keeps quality high even with smaller models.

* Shot boundary detection (PySceneDetect)
* Per shot quality scores: sharpness, exposure, camera shake, duplicate detection
* Subject tracking for smart reframing of horizontal clips into 9:16
* Vision language model describes sampled frames of each good shot: what is visible, shot type (close up, hands, packaging, product in use, reveal moment), dominant colors, mood

Result: a shot catalog with timestamps, scores and descriptions.

### 4.4 Aesthetic selection
The aesthetic is chosen by the user or detected automatically from the product, the footage colors and the Persian prompt. Each aesthetic is a **preset** stored as data, not code:

| Field | Example (Clean Girl) |
|---|---|
| Color grade | LUT file, soft warm neutrals, lifted shadows |
| Pacing | average shot length, cut on beat or every second beat |
| Transitions | hard cuts, occasional soft dissolve |
| Text style | font, size, color, position, animation |
| Effects | light grain, slight vignette, no flashy effects |
| Music mood tags | calm, soft, lofi, acoustic |

Built in presets: Clean Girl, Coquette, Grunge, Y2K. New presets can be created and edited in the UI.

### 4.5 Music selection
Pick tracks from the music bank that match the aesthetic mood tags and the planned length, then compute the beat grid (librosa) so cuts land on beats.

### 4.6 Edit planning
An LLM receives the product card, the shot catalog, the aesthetic preset, the beat grid and the translated user prompt, and returns **three edit plans** in a strict JSON schema, each with a different strategy, for example:

1. Hook first: strongest reveal in the first second
2. Story: packaging, unboxing, detail shots, product in use
3. Fast: short shots on every beat, a different music track

The plan is validated against the schema and against reality (timestamps exist, total length fits the music). Invalid plans are sent back to the model with the error for repair.

Edit plan shape (simplified):

```json
{
  "strategy": "hook_first",
  "music": { "track_id": "m_042", "start": 12.0 },
  "duration": 14.5,
  "grade": "clean_girl",
  "segments": [
    { "clip": "c1", "in": 3.2, "out": 4.4, "speed": 1.0,
      "crop": "auto", "transition_in": "cut" }
  ],
  "texts": [
    { "text": "my new everyday essential", "start": 0.3, "end": 2.5,
      "style": "clean_girl_title" }
  ]
}
```

### 4.7 Render
The plan is rendered deterministically with FFmpeg: trim, reframe to 9:16, speed, transitions, LUT grade, effects, text overlays (ASS subtitles for good typography), music with fade in and out, loudness normalization to TikTok levels. The AI only decides; FFmpeg builds the video. This makes results reproducible and lets the user edit a plan and re render without running the models again.

### 4.8 Quality review (optional)
A vision model looks at frames of the rendered variant and checks for problems: bad crop, text over the product, blurry shot, wrong mood. Detected issues trigger one automatic plan revision.

### 4.9 Output
Three MP4 files plus, for each variant, a suggested TikTok caption and hashtags. Everything is stored under the workflow folder.

## 5. Model providers

Every AI step talks to a **provider interface**, never to a specific model. Providers are configured in the settings page.

| Provider type | Use case |
|---|---|
| `ollama` | Ollama on the server or on the gaming PC, by URL |
| `openai_compatible` | vLLM, LM Studio, llama.cpp server, or any external API with a key |
| `local_path` | A model folder on disk, loaded in process |

Each pipeline step (vision, planning, translation, quality review, music tagging) is assigned a provider and a model name. A **Test connection** button in the UI checks that the provider is reachable and the model answers. If a remote machine such as the gaming PC is offline, the workflow waits in the queue with a clear status instead of failing.

## 6. Music bank

* Tracks live in `/data/music` with metadata in the database: title, artist, license, source URL, BPM, duration, mood and aesthetic tags.
* Importers for sources that offer an API and clear licenses (for example Jamendo or Freesound, filtered to licenses that allow commercial use), plus manual upload from the UI.
* New tracks are tagged automatically: BPM and energy with librosa, mood with an audio embedding model.
* The license of every track is stored and shown, because these videos promote products and therefore count as commercial use.

## 7. Data layout

```
/data
  uploads/<workflow_id>/clip_01.mp4
  work/<workflow_id>/proxies, frames, analysis.json, plans/
  exports/<workflow_id>/variant_1.mp4, variant_2.mp4, variant_3.mp4
  music/<track_id>.mp3
  presets/luts/*.cube
```

## 8. Settings available in the UI

* Model providers and per step model assignment
* Export: resolution, fps, bitrate, max duration, number of variants
* Aesthetic presets: create, edit, duplicate
* Text overlays on or off, language, font
* Music bank sources and import
* Storage: data path, automatic cleanup of work files

## 9. Build phases

| Phase | Result |
|---|---|
| 0 | Project skeleton: Docker Compose, API, worker, queue, upload, live progress in the UI |
| 1 | Render engine: hand written edit plan JSON to finished TikTok video, aesthetic presets with LUTs |
| 2 | Footage analysis: shot detection, quality scores, smart reframing |
| 3 | Provider layer and settings page, vision model shot descriptions |
| 4 | LLM edit planner with 3 variants, validation and repair |
| 5 | Product link scraper and product card |
| 6 | Music bank with import, auto tagging and beat sync |
| 7 | Quality review step, caption and hashtag suggestions |

Each phase ends with something that runs end to end, so the system is usable early and improves step by step.

## 10. Open questions

1. Text overlays: should videos contain text, and in which language (German, English, Persian)?
2. UI language: Persian (right to left) or English?
3. Reference videos: a few example TikToks of the desired look would help to tune the presets.
