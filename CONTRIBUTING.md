# Contributing

Short version of the rules in [CLAUDE.md](CLAUDE.md), which apply to everyone.

## Setup

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22, FFmpeg with
`zscale` and `libx265` (Debian and Ubuntu packages have both).

```bash
scripts/fetch-emoji.sh                     # Apple style emoji, once
cd backend && uv sync                      # Python dependencies
cd ../frontend && npm install              # frontend dependencies
```

Run it locally as described in the README (API, worker and the Vite dev server).

## Workflow

1. Create a branch from `main`: `fix/short-name` for bugs, `feat/short-name` for features.
2. Make the change with tests (see below).
3. Run the checks:

   ```bash
   cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
   cd frontend && npm run typecheck && npm run build
   ```

4. If the change affects how videos look or sound, render a real workflow and look at the
   frames ([docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)).
5. Open a pull request with the template filled in. Merge only when CI is green.

## Fixing a bug

1. Reproduce it and find the failing step (logs, `data/work/<id>/`).
2. Write a test that fails because of the bug.
3. Fix the cause, then make the test pass without weakening it.
4. Describe bug, cause and fix in the commit message.

## Tests

* `tests/test_workflows.py`: API, queue and full pipeline with generated clips
* `tests/test_planning.py`: timing, beats, length range, texts
* `tests/test_ai.py` with `tests/fake_ai.py`: Claude and OpenAI compatible providers,
  fallbacks, product page reading
* `tests/test_media.py`, `tests/test_render_text.py`: HDR conversion, overlay drawing
* `tests/test_settings.py`: options, music library

Media for tests is generated with FFmpeg inside the tests. Do not commit footage or music.

## Code style

* Python formatted and linted with ruff; TypeScript in strict mode.
* Comments in English. UI strings in English in `frontend/src/i18n.ts`.
* Keep functions small and names clear; explain why in comments, not what.
