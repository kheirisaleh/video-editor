# Aesthetic TikTok Editor: Design

A self hosted service that turns raw product footage into ready to post TikTok videos in the creator's own style. It runs on a home server, is used only inside the home network, and every AI component can be swapped from the UI.

## 1. Goal

The creator receives product samples from TikTok Shop and films them (promo or unboxing). The videos have no voiceover and no original sound, only a background music track, and follow a soft, cozy lifestyle aesthetic.

For each workflow the creator provides:

1. Several footage clips
2. A product description or a product link
3. An optional idea prompt written in Persian

The service understands the footage and the product, plans the best possible edit in the creator's style, and renders **three different variants** so the creator can pick the best one. Uploads and exports are stored on the server.

## 2. Reference style analysis

Four published videos of the creator were analysed (frames, cut times, overlay texts, music, loudness, engagement). This is the style the system must reproduce.

| Video | Product | Length | Cuts | Texts | Views |
|---|---|---|---|---|---|
| 1 | Teddy office chair | 21 s | 10 | 8 | 307k |
| 2 | Pilates board (Part 1) | 57 s | 26 | 17 | 102k |
| 3 | Treadmill (Part 4) | 46 s | 21 | 17 | 66k |
| 4 | Electric toothbrush + flosser | 59 s | 12 | 22 | 2.7k |

### 2.1 Structure
Every video follows the same story arc:

1. **Hook** (0 to 3 s): a "POV:" line or a series title such as "Home gym journey (Part 4)". Often the creator holding the box or opening a door.
2. **Unboxing**: box, packaging, first look.
3. **Feature walk**: one feature per shot, and the shot always **shows** that feature while its text is on screen ("Foldable armrests" while a hand folds the armrest, "135° reclining" while the chair reclines).
4. **Benefit summary**: sometimes a bullet list ("What you can do with it: ...") over a usage shot.
5. **Call to action**: "Link below the video ✨" and, for series, "Follow me and don't miss Part 2!".

### 2.2 Text overlays
* Always present, in **English**, even though the audience is in Germany.
* Short, casual, lowercase friendly sentences with soft emojis: 🤍 ✨ 🧸 👀 🥹 💛 🖤. The emoji color matches the product color.
* White text, small to medium size, centered horizontally, slightly below the middle of the frame, subtle shadow, no background box.
* Fonts: a clean sans serif (TikTok classic look) or an elegant serif for a more premium look. One font per video.
* Each text stays 1 to 3 seconds, one at a time, sometimes with a typewriter reveal.

### 2.3 Visuals and pacing
* Vertical phone footage, natural daylight, warm and neutral tones, no heavy color grading, no flashy transitions, only hard cuts.
* Many close ups with hands demonstrating details, mixed with wider shots of the creator using the product.
* Average shot length about 2 seconds.
* Exported from CapCut, uploaded at 540p to 1080p.

### 2.4 Music and caption
* Music is a trending or soft mood track (for example "cozy nights", Loren Gray), loudness between −20 and −15 LUFS.
* Post caption: one cozy sentence, a short product description, "Link below the video ✨", 4 to 6 hashtags, and the disclosure **"Pr sample, no payment received."**

### 2.5 What performs best
The shortest video (21 s, 8 texts, one feature per shot) has by far the most views. The 59 s video with 22 dense spec texts performs worst. Therefore the default target length is **15 to 25 seconds** with at most about 10 texts, and spec sheets are condensed into a few emotional benefits.

## 3. Scope and constraints

| Topic | Decision |
|---|---|
| Target platform | TikTok only: 1080x1920, 9:16, H.264 + AAC, 30 fps |
| Audio | No voice. Music from the music bank, or a silent export so a trending sound can be added inside TikTok |
| Text | English overlays in the style above, burned into the video |
| Variants | 3 per workflow, each with a different strategy |
| Concurrency | Workflows run one at a time, others wait in a queue |
| Access | Home network only, no login |
| UI language | English; Persian accepted in product text and idea prompt |
| Models | Local, on another machine in the LAN, or external API, configurable per pipeline step |
| Hardware | Unknown yet, so every heavy step must be able to run on a remote machine |
| Priority | Output quality over speed |

## 4. Technology

| Area | Choice | Why |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic | Best ecosystem for video, computer vision and AI |
| Database | SQLite via SQLAlchemy | Single user, zero maintenance, file based backup |
| Queue | Database backed queue with one worker process | Strict one at a time execution, survives restarts, no extra service |
| Live updates | WebSocket | Progress, logs and preview frames in real time |
| Video | FFmpeg with libass | Reliable rendering, high quality text with full typography control |
| Analysis | PySceneDetect, OpenCV, librosa | Shot detection, quality scores, beat detection |
| Scraping | Playwright (headless Chromium) | Handles JavaScript heavy shop pages |
| Model access | Provider layer over Ollama and OpenAI compatible APIs | Any local or remote model without code changes |
| Frontend | React, TypeScript, Vite, Tailwind, installable PWA | Works like an app on phone and desktop |
| Deployment | Docker Compose | One command install on the server; worker image can also run on the gaming PC |
| Quality | pytest, ruff, TypeScript strict mode | Tests and linting from the first phase |

## 5. Architecture

```
 Browser (phone / desktop, PWA)
        |  HTTP + WebSocket
        v
 +------------------+       +-------------------+
 |  API server      |<----->|  SQLite           |
 |  FastAPI         |       |                   |
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

## 6. Pipeline

Each workflow passes through these steps. Every step stores its result, so a failed workflow resumes from the failed step instead of starting over.

### 6.1 Ingest
Probe each clip with ffprobe (resolution, rotation, fps, duration), create low resolution proxies for fast analysis, and extract thumbnails for the UI.

### 6.2 Product understanding
* If a link is given, open it with Playwright and extract name, price, features, images and reviews. When the page blocks the scraper, fall back to the text description.
* An LLM turns the raw data into a **product card**: name, 3 to 5 emotional benefits, key specs, matching emoji and color mood, suggested hook lines.

### 6.3 Footage analysis
Classic computer vision first, AI second, so quality stays high even with smaller models.

* Shot boundary detection
* Per shot quality scores: sharpness, exposure, camera shake, duplicates
* Vision language model describes sampled frames of each good shot and labels it: hook candidate, box, unboxing, close up detail, hands demonstrating, creator using product, wide product shot
* **Feature matching**: each shot is linked to the product feature it demonstrates. This is what makes the text match the picture, the core of the creator's style.

### 6.4 Music selection
Pick tracks from the music bank that match the product mood and the planned length, then compute the beat grid so cuts land on beats.

### 6.5 Edit planning
An LLM receives the product card, the shot catalog with feature links, the style profile, the beat grid and the Persian prompt, and returns **three edit plans** in a strict JSON schema, for example:

1. **Short hook**: 15 to 20 s, POV hook, best 4 to 5 features, strongest shot first
2. **Unboxing story**: 25 to 35 s, box to first use, more texts
3. **Benefit focus**: 15 to 25 s, lifestyle and usage shots, summary list, different music

The plan is validated against the schema and against reality (timestamps exist, text durations are readable, total length fits). Invalid plans go back to the model with the error for repair.

```json
{
  "strategy": "short_hook",
  "music": { "track_id": "m_042", "start": 12.0 },
  "duration": 18.5,
  "style": "cozy_sans",
  "segments": [
    { "clip": "c1", "in": 3.2, "out": 5.0, "speed": 1.0 }
  ],
  "texts": [
    { "text": "POV: your office chair is officially your favorite seat in the house 🧸🤍",
      "start": 0.3, "end": 3.0, "animation": "typewriter" }
  ],
  "post_caption": "Work, relax & repeat 🧸🤍 ... Pr sample, no payment received."
}
```

### 6.6 Render
The plan is rendered deterministically with FFmpeg: trim, reframe to 9:16 when needed, speed, light color balance, text overlays as ASS subtitles with emoji support, music with fades, loudness normalization to about −16 LUFS. The AI only decides; FFmpeg builds the video. Results are reproducible, and an edited plan can be re rendered without running the models again.

### 6.7 Quality review
A vision model checks frames of each rendered variant: text over the product, text not matching the shot, blurry or dark shot, awkward first frame. Detected issues trigger one automatic plan revision.

### 6.8 Output
Per variant: the MP4, a silent MP4 (for adding a TikTok sound in the app), a cover frame, and the ready to paste post caption with hashtags and the PR disclosure.

## 7. Style profiles

The creator's look is stored as editable **style profiles**, not code. A profile holds font, size, color, shadow, position, text animation, maximum texts, target length, pacing, color balance and music mood. Two built in profiles derived from the reference videos:

* **Cozy Sans**: clean sans serif text, like the office chair video
* **Soft Serif**: elegant serif text with typewriter reveal, like the toothbrush video

Further aesthetics (Clean Girl, Coquette, Grunge, Y2K) can be added as profiles from the UI.

## 8. Model providers

Every AI step talks to a **provider interface**, never to a specific model. Providers are configured in the settings page.

| Provider type | Use case |
|---|---|
| `ollama` | Ollama on the server or on the gaming PC, by URL |
| `openai_compatible` | vLLM, LM Studio, llama.cpp server, or any external API with a key |
| `local_path` | A model folder on disk, loaded in process |

Each pipeline step (vision, planning, copywriting, quality review, music tagging) is assigned a provider and a model. A **Test connection** button checks that the provider answers. If a remote machine such as the gaming PC is offline, the workflow waits in the queue with a clear status instead of failing.

## 9. Music bank

* Tracks live in `/data/music` with metadata: title, artist, license, source, BPM, duration, mood tags.
* Importers for sources with an API and clear licenses, filtered to licenses that allow commercial use, plus manual upload.
* New tracks are tagged automatically: BPM and energy with librosa, mood with an audio embedding model.
* The license of every track is stored and shown, because product promotion counts as commercial use.

## 10. Data layout

```
/data
  uploads/<workflow_id>/clip_01.mp4
  work/<workflow_id>/proxies, frames, analysis.json, plans/
  exports/<workflow_id>/variant_1.mp4, variant_1_silent.mp4, variant_1.txt
  music/<track_id>.mp3
  fonts/
```

## 11. Settings in the UI

* Model providers and per step model assignment
* Export: resolution, fps, bitrate, target length, number of variants, silent export on or off
* Style profiles: create, edit, duplicate
* Default hashtags and disclosure text
* Music bank sources and import
* Storage: data path, automatic cleanup of work files

## 12. Build phases

| Phase | Result |
|---|---|
| 0 | Project skeleton: Docker Compose, API, worker, queue, upload, live progress in the UI |
| 1 | Render engine: edit plan JSON to finished TikTok video with styled texts, music and both exports |
| 2 | Footage analysis: shot detection, quality scores |
| 3 | Provider layer and settings page, vision model shot labels and feature matching |
| 4 | LLM edit planner with 3 variants, validation and repair, post caption |
| 5 | Product link scraper and product card |
| 6 | Music bank with import, auto tagging and beat sync |
| 7 | Quality review step, style profile editor |

Each phase ends with something that runs end to end, so the system is usable early and improves step by step.

Progress: all phases are built. The model steps (product card, shot understanding, edit planning) run as soon as a model is configured in the settings page; until then the rule based planner is used. The UI is in English; Persian is accepted in the product text and the idea prompt.
