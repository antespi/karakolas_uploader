# karakolas_uploader

Unattended product loader for [karakolas.net](https://karakolas.net).

Reads a source product CSV, normalizes it into the attributes karakolas.net expects, and drives the karakolas.net web UI to create or update each product. Designed to run headless on a schedule with no human in the loop.

## Goals

- **Unattended**: full pipeline runs end-to-end without user interaction.
- **Idempotent**: re-running the pipeline on the same input is safe. If a product already exists on karakolas.net, it is updated in place; otherwise it is created.
- **Reproducible**: the intermediate normalized CSV is the contract between preprocessing and upload, so each stage can be inspected, diffed, and re-run independently.

## Pipeline

```
[ source CSV ]
      │
      ▼
  preprocess  ──►  [ karakolas.csv ]   (only the columns karakolas.net needs)
      │
      ▼
   uploader   ──►  karakolas.net       (create or update per row)
```

### 1. Preprocess

Reads the raw input CSV (vendor / ERP / spreadsheet export) and emits a clean CSV containing only the attributes karakolas.net actually accepts. Responsibilities:

- Drop unused columns.
- Rename / map columns to karakolas.net field names.
- Normalize types, units, and encodings.
- Validate required fields; reject or flag bad rows before they reach the uploader.

### 2. Discover karakolas.net (one-time / as-needed)

karakolas.net does not (currently) expose a documented API for product upload, so the upload flow is reverse-engineered from the web UI. Two complementary tools drive this phase:

- **[agent-browser](https://github.com/vercel-labs/agent-browser)** — a Rust CLI from Vercel Labs that exposes a real Chromium browser to AI agents and shell scripts. Used here as the *driver* for live exploration and replay:
  - `agent-browser open <url>` / `snapshot` to capture the accessibility tree (with stable `@e1`, `@e2`… refs) of karakolas.net product pages — far more agent-friendly than raw HTML.
  - `agent-browser find role/label/text … click|fill` to interact with the create- and edit-product forms by semantic locators instead of brittle CSS selectors.
  - `agent-browser network har start|stop` and `network requests` to record the actual HTTP calls karakolas.net makes when a product is created or updated, so we can decide whether the uploader should replay HTTP directly or keep driving the UI.
  - `agent-browser eval <js>` and `cookies` / `storage` commands to inspect session state and any client-side validation.
  - `agent-browser batch` to script repeatable multi-step explorations in one process (cheaper than spawning the binary per command).
- **[Scrapling](https://github.com/D4Vinci/Scrapling)** — used as the *parser*: fast, adaptive HTML parsing and resilient selectors over the snapshots and HAR responses agent-browser captures, so small UI changes on karakolas.net don't break the discovery scripts.

Goals of this phase:

- Map the create-product and edit-product flows (URLs, forms, required fields, validation rules).
- Identify how to look up an existing product (the key used for idempotency — SKU, code, slug, etc.).
- Capture the network requests behind each UI action so the uploader can replay them directly when possible.

The output is a spec (selectors, endpoints, payload shapes, idempotency key) that `upload.py` implements. Re-run the discovery scripts whenever karakolas.net changes its UI.

### 3. Upload (idempotent)

For each row in the normalized CSV:

1. Look up the product on karakolas.net by its stable key.
2. If it does not exist → create it.
3. If it exists → diff the current state against the CSV row and update only the changed fields.
4. Log the outcome (`created` / `updated` / `unchanged` / `error`) so re-runs are auditable.

The script must be safe to run repeatedly with the same input and converge to the same end state on karakolas.net.

## Repository layout (planned)

```
granel/
├── README.md
├── scripts/
│   ├── preprocess.py        # raw CSV → karakolas.csv
│   ├── discover.py          # agent-browser / scraping exploration
│   └── upload.py            # idempotent create-or-update against karakolas.net
├── data/
│   ├── input/               # raw source CSVs
│   └── output/              # normalized karakolas.csv files
└── logs/                    # per-run upload logs
```

## Requirements

- Credentials for a karakolas.net account with permission to create/edit products.
- [`agent-browser`](https://github.com/vercel-labs/agent-browser) — Rust CLI that drives a real Chromium for snapshots, semantic-locator interactions, JS eval, and HAR capture. Install with `npm install -g agent-browser && agent-browser install` (downloads Chrome for Testing on first run).
- [`Scrapling`](https://github.com/D4Vinci/Scrapling) for HTML parsing, selector capture, and resilient scraping over the pages/HARs agent-browser produces.
- For the upload phase: either replay the HTTP calls captured during discovery (preferred when feasible) or keep driving the UI through `agent-browser` itself.

## Status

Early scaffolding. Scripts referenced above are to be implemented.
