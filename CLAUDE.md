# Rules for working on this repository

These rules apply to every change, by a person or an AI assistant. Read them fully before
the first edit. `CONTRIBUTING.md` has the same workflow in short form for people;
`docs/DESIGN.md` explains why the product works the way it does.

## 1. What this is

Studio is a self hosted service on the creator's home server. It turns raw phone footage of
TikTok Shop product samples into finished, voiceless TikTok videos in the creator's own
aesthetic (soft, cozy lifestyle; English overlay texts; music only). One creator uses it,
only inside the home network, mostly from an iPhone.

The single most important goal is **output quality**. A change that makes the videos look
or feel worse is a regression, even if all tests pass.

## 2. Map of the code

```
backend/studio/
  api/            FastAPI routes: workflows, uploads, settings, music, live events
  worker/         queue worker; pipeline.py runs the steps in order
    steps/        ingest, product, analyze, understand, plan, render
  media/ffmpeg.py probe, proxies, thumbnails, HDR to SDR conversion
  analysis/       footage.py (shots, quality, faces), beats.py (music beats)
  planning/       schema.py (EditPlan), baseline.py (timeline, texts, rule based planner)
  render/         text.py (overlay images, fonts, emoji), video.py (FFmpeg command)
  ai/             settings, client (Claude SDK and OpenAI compatible), product card,
                  shot labels (vision), director (edit scripts)
  options.py      user options and defaults
  models.py db.py SQLite tables; a tiny forward migration adds new nullable columns
  assets/fonts/   TikTok Sans and Source Serif 4 (OFL); emoji images are downloaded, not committed
backend/tests/    pytest; fake_ai.py imitates the Claude API and OpenAI compatible servers
frontend/src/     React + TypeScript PWA: pages/, components/, api.ts, i18n.ts, live.tsx
docs/             DESIGN.md (product and style), TROUBLESHOOTING.md (finding bugs)
scripts/          fetch-emoji.sh
```

Data flow of one workflow: upload, then the worker runs
`ingest -> product -> analyze -> understand -> plan -> render`. Every step stores its result
(database row plus files in `data/work/<id>/`), so a failed workflow resumes at the failed
step and `rerun` can restart from any step.

## 3. Architecture rules (do not break these)

1. **The AI decides, the code renders.** Models only return JSON decisions (product card,
   shot labels, shot order and texts). Timing, beat sync, length range, text placement and
   the FFmpeg render stay deterministic in `planning/` and `render/`. Never let a model
   produce timestamps, filter graphs or file paths that are used unchecked.
2. **Everything works without a model.** Each AI step must fall back to the rule based
   path, unless the user turned on "Require the model". New AI features need a fallback.
3. **One workflow at a time.** The queue is a database table; the worker is a separate
   process. Do not add a second worker or background threads that render.
4. **Steps are resumable.** A step must be safe to run again: clear its own old output
   first, write results at the end, never depend on in memory state of another step.
5. **The API never blocks on long work.** Uploads stream to disk; heavy work belongs in
   the worker. Long running database sessions are not allowed during uploads.
6. **Secrets stay on the server.** The AI key is never returned by the API, logged or put
   in events. Never commit keys, `.env` files, footage, music or the emoji images.
7. **Options have one home.** New user facing switches go into `RenderOptions` with a safe
   default, the options form in the UI, and the README options table.
8. **Database changes are additive.** Only add nullable columns or new tables, so existing
   databases keep working through `_add_missing_columns`. Never rename or drop columns.

## 4. Quality rules for anything that changes the video

The reference style is documented in `docs/DESIGN.md` section 2. Keep it.

* Output: 1080x1920, 30 fps, H.264 high profile, yuv420p, BT.709, AAC 44.1 kHz, faststart.
* Length always inside the user's min and max; cuts on the frame grid and, with music, on
  the beat.
* Text: TikTok Sans or Source Serif 4, white with the double soft shadow, inside the safe
  area, never over a detected face, readable duration (`readable()` in baseline.py).
* Apple style emoji only; never fall back silently to boxes or monochrome glyphs.
* iPhone HDR must be tone mapped (`sdr_filter`); check colours, not just "it runs".
* Music: starts on a downbeat, loudness about −16 LUFS, fades out.

**Visual verification is mandatory** for changes in `render/`, `planning/`,
`analysis/` or `media/`: render a real workflow and look at the frames, not only the
tests. The commands are in `docs/TROUBLESHOOTING.md` ("Look at an output frame by frame").
Compare before and after on the same footage and say what changed.

## 5. AI provider rules

* Claude is called only through the official `anthropic` SDK (`ai/client.py`), never
  through an OpenAI compatible shim. Default model `claude-opus-5-5`; do not change the
  default model or effort without the user asking.
* Use structured outputs (`output_config.format` with a JSON schema whose objects have
  `additionalProperties: false` and list every property in `required`). Validate the
  result with Pydantic anyway.
* Keep `fallbacks: "default"` with the `server-side-fallback-2026-07-01` beta for models in
  `FALLBACK_MODELS`, and handle `stop_reason` `refusal` and `max_tokens` before reading
  content.
* Local models (Ollama and others) go through `OpenAICompatibleClient`; it must keep
  working with servers that only support `json_object`.
* Every AI failure becomes an `AiError` with a message a non programmer understands.
* Prompts live next to the code that uses them (`ai/product.py`, `ai/shots.py`,
  `ai/director.py`). When changing a prompt, explain why in the commit and test the
  result with `tests/fake_ai.py` for format and, when available, with a real model for
  quality.
* Never send footage anywhere except the configured model provider.

## 6. Code style

* Python 3.12, typed, formatted and linted with ruff (line length 100). TypeScript strict.
* Comments and docstrings in **English only**. No Persian in code comments.
* The UI is in **English**. Persian is accepted only as user input (product text, idea
  prompt) and is handled by the models. All UI strings live in `frontend/src/i18n.ts`.
* Match the surrounding code: small functions, clear names, comments that explain why,
  not what. No dead code, no commented out code, no debug prints.
* User facing error messages explain what happened and what to do next.
* New dependencies only when they clearly pay off; pin them through `uv add` or `npm`
  and make sure the Docker image still builds.

## 7. How to fix a bug

1. **Reproduce first.** Use the logs and the files in `data/work/<id>/`
   (`docs/TROUBLESHOOTING.md`). Find the step and the exact input that fails.
2. **Write a failing test** that shows the bug (`backend/tests/`). For media bugs, generate
   the smallest possible clip with FFmpeg in the test (see `conftest.py`) instead of
   committing footage.
3. Fix the root cause, not the symptom. No `try/except: pass`, no skipped or weakened
   tests, no larger tolerances just to get green.
4. Run all checks (section 9). For output related bugs also do the visual check.
5. Commit with a message that names the bug, the cause and the fix.

## 8. How to add a feature

1. Check `docs/DESIGN.md`; if the feature changes the design, update the document in the
   same change.
2. Keep the fallback path (no model) and the resumable step rules.
3. Add tests: unit tests for the logic, an API or worker test for the flow, fake AI tests
   for anything that talks to a model.
4. Update the README (options table, setup steps) when users see the change.

## 9. Checks before every commit

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
cd frontend && npm run typecheck && npm run build
```

All must pass. CI runs the same checks plus a Docker build on every push and pull request.
If a check fails, fix it; do not skip it. When the Docker setup changes, build the image
and run one workflow in it (`docker compose up -d --build`).

## 10. Git

* Never push to `main` directly. Work on a branch, open a pull request, merge when CI is
  green.
* Small, focused commits. Message: a short imperative subject line (max 72 characters),
  a blank line, then what changed and why.
* Do not rewrite published history.

## 11. Talking to the user

The creator lives in Germany and is training as a software developer (Ausbildung).
Answer in **Persian**. In Persian text put Latin words, code and commands on their own
lines so right to left and left to right text do not mix. Do not use dash characters in
prepared prose. Be honest about what was tested and what was not; say clearly when
something could not be verified.
