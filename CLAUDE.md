# CLAUDE.md

Project-specific conventions for whoever (human or agent) works on this repo next.

## Migrations

Numbered `.sql` files in `migrations/`, applied in order and tracked via `PRAGMA user_version`
(see `viewer/migrations.py`). Only additive changes belong here (`ALTER TABLE ... ADD COLUMN`,
new tables/indexes) — `sessions`/`messages`/`parts`/`todo_snapshots`/`detections` are a derived
index rebuilt from the `events` table by `viewer/indexer.py::reindex_session`, which is called
both at ingest time and by `viewer reindex`. Any column meant to hold **human-entered** state
(e.g. `sources.display_name`, `sessions.notes`) must be left out of both the `INSERT` column list
and the `ON CONFLICT ... SET` clause in the indexer's session/source upserts — otherwise a reindex
silently wipes it, since those upserts only ever write columns *derived from events*.

## Internationalization (RU | ENG)

All frontend UI chrome (labels, headers, buttons, empty states, help text) goes through `t()`
from `frontend/src/i18n.tsx` — add a key to **both** the `ru` and `en` blocks whenever you add new
visible copy; nothing renders if a key is missing from the active locale (falls back to `ru`, then
to the raw key itself, so a mismatch is visible immediately rather than silently wrong).

**What does NOT get translated**: anything the backend generates or the agent produced — detector
`message` text (`viewer/detectors/*.py`), the content of sessions/tool output/errors, and the
markdown export. Those are factual records in whatever language they were produced in, not
interface copy. Don't "fix" them into `t()` calls.

`frontend/src/detectorDocs.ts` holds the bilingual explanation shown behind the "ⓘ" on each
detection card. It's a manually-maintained mirror of the actual thresholds in
`viewer/detectors/*.py` — when you change a detector's threshold, update this file in the same
change, nothing enforces the two staying in sync automatically.

The active locale lives in a React context (`LocaleProvider` in `i18n.tsx`) persisted to
`localStorage`. Hash-based routing never triggers a full page reload, so the locale survives
navigation between views without extra plumbing — don't reintroduce anything that reads
`localStorage` on every render or that would remount `LocaleProvider`.

## `/root/codeanal/docs/*.md`

If you go looking at the `mvk-codeqa` agent deployment this viewer is connected to, note that
`docs/viewer-plan.md` and `docs/viewer-plugin-plan.md` in that repo describe a **different,
never-implemented** design for an OpenCode observability viewer (plain Node.js, `node:sqlite`,
encrypted push over AES-256-GCM, no build step). It predates or was explored in parallel with this
actual implementation (Python/FastAPI/SQLite backend + React/Vite frontend, bearer-token ingest
auth) and has no bearing on this codebase - don't reconcile the two or treat that doc as a spec for
this repo.

## Subagent ("scout") sessions

A `task` call to a named subagent produces two independent signals in the event stream: a
`message.part.updated` part with `type: "subtask"` (`agent`/`prompt`/`description`, no session id)
in the parent's own message stream, and a separate `session.created` with `parentID` pointing at
the parent. Nothing in the raw events names which child session a given `subtask` part spawned —
`viewer/routes.py::get_session` links them heuristically at request time (same agent name,
chronological order within that agent), exposed as `linked_session_id` /
`linked_session_match: "heuristic"` on the part. This is correct only if same-named subagents run
sequentially rather than concurrently; don't upgrade the "heuristic" label to something stronger
without an actual session id to key on.
