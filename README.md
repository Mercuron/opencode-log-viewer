# opencode-log-viewer

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**English** | [Русский](README.ru.md)

A trace viewer for [OpenCode](https://opencode.ai) agents. Receives events from
[opencode-log-plugin](https://www.npmjs.com/package/opencode-log-plugin), stores them in SQLite, and
gives you a web UI to answer, for one specific session: how long did it take, where did the time
go, which tools were called and with what, and where did the agent go wrong.

This is a diagnostic tool, not an agent control panel. The viewer never talks to the agent — the
connection is `plugin → viewer`, one-way, over HTTP.

## Stack, and why

- **Backend:** Python 3.12+, FastAPI, uvicorn, a single worker (`--workers 1`) — SQLite doesn't
  tolerate concurrent writes from multiple processes.
- **Storage:** SQLite in WAL mode, one file on a Docker volume (`/data/viewer.db`), accessed via
  the standard library's `sqlite3` — no ORM, the queries are analytical and hand-written. The
  normalized tables (`sessions`, `messages`, `parts`, …) are a rebuildable index on top of the
  `events` table, which is the actual source of truth. `viewer reindex` rebuilds the index from
  scratch at any time.
- **Frontend: React + Vite.** Chosen over a server-rendered alternative (e.g. Jinja2 + HTMX)
  because the step feed is genuinely interactive — expanding items, filtering by tool, a
  waterfall view, live updates over SSE — and that's simpler to write directly in React than to
  layer on top of server-side rendering. The frontend is built at Docker build time
  (`node:22-alpine`) and served by the same app via `StaticFiles` — no Node needed at runtime.
- **CLI:** a `console_scripts` entry point named `viewer` (`import`, `import-inference`,
  `reindex`, `prune`) — see below.

Ingestion is designed to never block the event loop: the HTTP handler puts the batch on an
`asyncio.Queue` and awaits the result from a single background writer task (`IngestWorker`), which
performs the actual write via `asyncio.to_thread`. That gives both "single writer process" and
non-blocking ingestion at the same time.

## Quick start

```bash
cp .env.example .env    # change INGEST_SECRET and UI_PASSWORD before doing anything else
docker compose up -d --build
```

Open `http://localhost:8080`. Empty is expected until the first event arrives from the plugin, or
until you run the one-time history import (Settings → "Import existing sessions" in the UI).

Exactly one public port is required: 8080. Data survives `docker compose down && docker compose up`
(named volume `viewer-data`).

### Connecting an agent

See [opencode-log-plugin](https://www.npmjs.com/package/opencode-log-plugin) — installing it is
one line in the agent's `opencode.json` (it's published on npm), plus two environment variables
pointing at this viewer:

```env
OPENCODE_LOG_VIEWER_URL=http://<this-viewer-host>:8080
OPENCODE_LOG_VIEWER_SECRET=<same value as INGEST_SECRET below>
```

## Importing existing history

A one-time action: pulls in sessions the agent accumulated before the plugin was connected. New
sessions after that arrive on their own via the plugin — you don't need to run this again (and
it's safe to: idempotent on `event_id`, re-running never creates duplicates).

From the UI: Settings → "Import existing sessions" — give it a path (mounted read-only into the
container) and a source name.

From the CLI, inside the container:

```bash
docker compose exec viewer viewer import --path /import/opencode --source my-agent
```

Both OpenCode storage layouts are supported, auto-detected:
- a tree of JSON files, `storage/session|message|part|todo`;
- a SQLite `opencode.db` (the layout OpenCode's core actually used at the time this was written,
  verified directly against OpenCode's source).

Mount the agent's storage into `docker-compose.yml`:

```yaml
volumes:
  - ${HOME}/.local/share/opencode:/import/opencode:ro
```

## Correlating with inference server logs

```bash
docker compose exec viewer viewer import-inference --format llama-server --file /import/llama.log --source my-agent
```

Parses `prompt eval time` / `eval time` / `n_past` out of `llama-server` logs and matches them to
the source's most recent session's model steps, in chronological order. Where no match is found,
the feed says exactly that — "no inference data" — rather than making up a number.

## CLI

```
viewer import --path <dir|file> --source <name>          # one-time history import
viewer import-inference --format llama-server --file <log> --source <name> [--session-id <id>]
viewer reindex [--session <id>]                           # rebuild the index from raw events
viewer prune                                               # run retention right now
```

## Retention

```env
RETENTION_DAYS=90
RETENTION_MAX_GB=20
```

A background task runs daily and deletes the oldest sessions whole (raw events + the entire
derived index) once either threshold is crossed. This is on by default and can only be turned off
with `VIEWER_DISABLE_RETENTION=1` (used by the test suite) — having no retention policy at all is
treated as a defect, not an option.

## Security

Two independent secrets:

```env
INGEST_SECRET=...        # for every plugin instance on every agent host
UI_PASSWORD=...          # for a human logging into the UI
SESSION_COOKIE_KEY=...   # signs the UI session cookie
```

`INGEST_SECRET` cannot double as a human password: it has to live on every agent host, so if it
were also the UI password, anyone with access to any agent host could read every other source's
sessions — and sessions can contain production database output.

**The viewer stores excerpts from production logs by design.** By default only obvious passwords
and secret-looking tokens are redacted (`REDACT_PATTERNS` in `.env.example`) — aggressively
stripping tool output would defeat the point of the tool. Restrict network access to it, and
**don't expose it publicly.**

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -q          # no network, no running agent - runs against fixtures
cd frontend && npm install && npm run dev   # proxies to localhost:8080, see vite.config.ts
```

Tests run against `tests/fixtures/` (a copy of `opencode-log-plugin/fixtures/`) — the viewer is
developed and tested without a live agent.

## Docker: connecting an agent

Logging **needs no inbound port on the agent** — the plugin only ever makes outbound connections.

- agent and viewer on the same Docker network: `OPENCODE_LOG_VIEWER_URL=http://viewer:8080`
- viewer on the host: `http://host.docker.internal:8080` (Linux: add
  `extra_hosts: ["host.docker.internal:host-gateway"]` to the agent's compose file)
- viewer on another machine: `http://192.168.x.x:8080` or HTTPS

A viewer → agent connection does not exist in any of these scenarios — see
[opencode-log-plugin](https://www.npmjs.com/package/opencode-log-plugin)'s README for the full
picture from the agent's side.

## Data model and event contract

`schema/event.v1.json` is the same file used by opencode-log-plugin, kept in sync by hand — a
divergence between the two is a reason to bump `schema_version`. The full table schema lives in
`migrations/0001_init.sql`.

## License

[MIT](LICENSE)
