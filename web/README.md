# Aadesh frontend

A Next.js + TypeScript + Tailwind console over the local Aadesh JSON API. It is **not** an AQI
dashboard: the primary screen answers *"what is happening at my site and what do I need to
do?"*, not *"what is today's AQI?"*.

## Architecture

The frontend imports none of the deterministic core. It talks to the local JSON API
(`services/aadesh_web/server.py`), which is itself a thin adapter over `aadesh_core`:

```
browser ──▶ Next.js (/api/* rewrite) ──▶ aadesh_web ──▶ aadesh_core  (no model, no network)
```

`next.config.mjs` proxies `/api/:path*` to `http://127.0.0.1:8787` (override with
`AADESH_API_URL`), so the browser stays same-origin. There is no second source of truth: the
stage, the obligations, the Cedar denials and the verification result all come from the same
core the CLI and `make verify` use.

## Run it

Two shells, from the repository root:

```bash
make api      # Aadesh JSON API on http://127.0.0.1:8787
make web      # Next.js on http://localhost:3000 (runs npm install on first use)
```

Or directly:

```bash
python -m aadesh_web.server --port 8787     # needs PYTHONPATH=services, i.e. `make api`
cd web && npm install && npm run dev
```

## Screens

| Route | Principal | What it answers |
|---|---|---|
| `/` | — | Product framing and role entry points |
| `/supervisor` | Supervisor | Invoked stage, cited obligations, Standing Order, worker impact, QR grid |
| `/worker` | Worker | Mobile-first parchi screen, Hindi/English, explicit acknowledgement |
| `/cedar` | — | Real Cedar evaluation: a supervisor cannot acknowledge a worker's parchi |
| `/facilitator` | Facilitator | Redacted assist view under live consent; `ViewParchi` denied |
| `/verify` | — | `make verify` PASS and the tamper check failing on purpose |

## Design

Tokens and layout follow an operational-console direction (Swiss/minimal, dense, grid-based,
high contrast; Fira Sans + Fira Code). Status is never colour alone — every pill carries a
word. No map, no charts, no AQI gauge, no animated pollution graphics, no chat interface.

## Three honesty decisions worth knowing

- **The Stage III shown by default is a historical replay.** The shipped corpus records
  exactly one invoked stage (Stage III, 16 Jan 2026) and CAQM **revoked** it on 22 Jan 2026.
  There is no verified current invocation, so the screen labels the invocation as a replay and
  says it is not in force. It never presents a revoked order as the live stage.
- **The station reading is a synthetic placeholder.** No live ingest exists yet, so the
  reading is labelled `synthetic` on screen rather than passed off as a measurement.
- **No monetary amount is shown.** The verified corpus establishes none, so the worker-impact
  panel reports *workers documented* and *claim readiness* (a registration/documentation
  count), never rupees and never `worker_count × amount`.

Additionally, the amber warning the brief asks for is driven by the real engine: switch the
station reading to **Divergent** and the implied stage (Stage IV) diverges from the official
one (Stage III) exactly as `StageStatus` reports it.
