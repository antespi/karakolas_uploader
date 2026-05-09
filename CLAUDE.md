# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Early scaffolding. Only `README.md` exists so far. The scripts described below (`scripts/preprocess.py`, `scripts/discover.py`, `scripts/upload.py`) are **planned, not implemented** — assume nothing exists on disk and confirm before referencing any code path.

## Purpose

Unattended product loader for [karakolas.net](https://karakolas.net). karakolas.net has no documented product API, so uploads are driven through the web UI by automation. The pipeline must run headless on a schedule and must be **idempotent** — re-running on the same input creates missing products and updates existing ones to match the CSV, never duplicating.

## Pipeline architecture

Three stages connected by a CSV contract:

1. **Preprocess** (`scripts/preprocess.py`) — raw vendor/ERP CSV → `karakolas.csv` containing only the columns karakolas.net accepts. Drops unused columns, renames to karakolas.net field names, normalizes types/units/encodings, validates required fields. The normalized CSV is the boundary between stages, so it can be inspected and diffed independently.

2. **Discover** (`scripts/discover.py`) — reverse-engineers the karakolas.net web flows. This stage is run *as needed* (not every pipeline run) and produces a spec that `upload.py` consumes: selectors, endpoints, payload shapes, and the idempotency key (SKU / code / slug — to be confirmed during discovery). Re-run whenever karakolas.net's UI changes.

3. **Upload** (`scripts/upload.py`) — for each row in `karakolas.csv`: look up by idempotency key → create if missing, diff and patch if present → log `created` / `updated` / `unchanged` / `error`. Must converge to the same end state on repeated runs.

## Tooling roles (important to keep distinct)

- **[agent-browser](https://github.com/vercel-labs/agent-browser)** — Vercel Labs Rust CLI that drives a real Chromium. Used as the *driver* in the discover phase and (potentially) the upload phase. Key commands the project relies on:
  - `agent-browser open <url>` and `snapshot` — capture accessibility tree with stable `@e1`, `@e2`… refs (agent-friendly; prefer over raw HTML).
  - `agent-browser find role|label|text|placeholder <…> click|fill|type` — semantic locators that survive cosmetic UI changes; preferred over CSS selectors.
  - `agent-browser network har start|stop` and `network requests` — record the HTTP traffic behind a UI action so the uploader can replay HTTP directly when feasible.
  - `agent-browser eval <js>`, `cookies`, `storage` — inspect session/state and client-side validation.
  - `agent-browser batch` — chain multi-step flows in one process; cheaper than spawning the binary per command.
- **[Scrapling](https://github.com/D4Vinci/Scrapling)** — used as the *parser* on top of what agent-browser captures (snapshots, HAR responses). Provides resilient, adaptive selectors so small UI changes don't break discovery scripts.

When extending discovery or upload, default to: agent-browser drives the browser → Scrapling parses what comes out. Don't reach for a separate Playwright/Puppeteer stack unless agent-browser can't express the interaction.

## Idempotency rule

This is the load-bearing invariant of the project. Every change to `upload.py` (or anything it calls) must preserve it:

- Lookup-before-write: never POST a create without first checking existence by the idempotency key.
- On update, diff current state against the CSV row and patch **only changed fields** — don't blindly overwrite.
- Log per-row outcome so re-runs are auditable.

If the idempotency key for a product type is unclear, that's a discovery task — do not guess in `upload.py`.

## Planned layout (per README)

```
granel/
├── scripts/      # preprocess.py, discover.py, upload.py
├── data/
│   ├── input/    # raw source CSVs
│   └── output/   # normalized karakolas.csv files
└── logs/         # per-run upload logs
```

## Requirements

- karakolas.net account with permission to create/edit products.
- `agent-browser` installed globally: `npm install -g agent-browser && agent-browser install` (downloads Chrome for Testing on first run; on Linux use `agent-browser install --with-deps`).
- `Scrapling` available in the Python environment used by the scripts.

## Commands

No build/test/lint commands defined yet — there is no code, no `package.json`, no `pyproject.toml`. Add this section once the first script lands.
