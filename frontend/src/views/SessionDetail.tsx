import { useEffect, useMemo, useRef, useState } from "react"
import { api, Detection, Message, Part, SessionDetail as SessionDetailData, TodoSnapshot } from "../api"
import { useLocale, Locale, TranslationKey } from "../i18n"
import { detectorDoc } from "../detectorDocs"
import FullValueModal from "../components/FullValueModal"

const FULL_VALUE_THRESHOLD = 2000
const CLEARED_MARKER = "[Old tool result content cleared]"

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "?"
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} с`
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`
}

function fmtBytes(n: number, t: (k: TranslationKey) => string): string {
  if (n < 1024) return `${n} ${t("unit.b")}`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} ${t("unit.kb")}`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} ${t("unit.mb")}`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} ${t("unit.gb")}`
}

function levelClass(level: string): string {
  return level === "bad" ? "badge-bad" : level === "warn" ? "badge-warn" : "badge-info"
}

function toMs(iso: string | null | undefined): number | null {
  return iso ? new Date(iso).getTime() : null
}

function DetectionCard({ d, locale }: { d: Detection; locale: Locale }) {
  const [open, setOpen] = useState(false)
  const doc = detectorDoc(d.kind, locale)
  return (
    <div className="detection-card">
      <span className={`badge ${levelClass(d.level)}`}>{d.level}</span>
      <strong>{d.kind}</strong>
      {doc && (
        <button className="info-toggle" onClick={() => setOpen((o) => !o)} aria-label="info">
          ⓘ
        </button>
      )}
      <p>{d.message}</p>
      {open && doc && <div className="detection-explain">{doc}</div>}
    </div>
  )
}

function PartRow({ part, onOpenSession, onShowFull }: { part: Part; onOpenSession: (id: string) => void; onShowFull: (title: string, value: string) => void }) {
  const { t } = useLocale()
  const [open, setOpen] = useState(false)

  function longButton(label: string, value: string) {
    if (value.length <= FULL_VALUE_THRESHOLD) return null
    return (
      <button className="button-link" onClick={() => onShowFull(label, value)}>
        {t("feed.show_full")} ({value.length})
      </button>
    )
  }

  return (
    <div className="feed-item">
      <div className="feed-row" onClick={() => setOpen((v) => !v)}>
        <span className="feed-seq">#{part.seq}</span>
        <span className="feed-type">{part.type}</span>
        {part.tool_name && <span className="feed-tool">{part.tool_name}</span>}
        {part.status && <span className={`badge ${part.status === "error" ? "badge-bad" : "badge-muted"}`}>{part.status}</span>}
        <span className="feed-duration">{fmtMs(part.duration_ms)}</span>
        {part.output_tokens_est ? <span className="muted">≈{part.output_tokens_est} ток</span> : null}
      </div>
      {open && (
        <div className="feed-detail">
          {part.text && (
            <>
              <pre className="feed-pre">{part.text.slice(0, FULL_VALUE_THRESHOLD)}</pre>
              {longButton(part.type, part.text)}
            </>
          )}
          {part.input_json && (
            <>
              <div className="muted">{t("feed.input_label")}</div>
              <pre className="feed-pre">{part.input_json.slice(0, FULL_VALUE_THRESHOLD)}</pre>
              {longButton(t("feed.input_label"), part.input_json)}
            </>
          )}
          {part.output_text && (
            <>
              <div className="muted">{t("feed.output_label")}</div>
              <pre className="feed-pre">{part.output_text.slice(0, FULL_VALUE_THRESHOLD)}</pre>
              {longButton(t("feed.output_label"), part.output_text)}
            </>
          )}
          {part.error && (
            <div className="error-text">
              {t("feed.error_label")} {part.error}
            </div>
          )}
          {part.linked_session_id && (
            <div>
              <button onClick={() => onOpenSession(part.linked_session_id!)}>{t("feed.open_subagent_session")}</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function groupPartsByMessage(parts: Part[], messages: Message[]) {
  const messageById = new Map(messages.map((m) => [m.id, m]))
  const groups = new Map<string, Part[]>()
  const order: string[] = []
  for (const p of parts) {
    const mid = p.message_id || "_none"
    if (!groups.has(mid)) {
      groups.set(mid, [])
      order.push(mid)
    }
    groups.get(mid)!.push(p)
  }
  order.sort((a, b) => {
    const ma = messageById.get(a)?.seq ?? groups.get(a)![0]?.seq ?? 0
    const mb = messageById.get(b)?.seq ?? groups.get(b)![0]?.seq ?? 0
    return ma - mb
  })
  return order.map((mid) => ({ message: messageById.get(mid) || null, parts: groups.get(mid)! }))
}

function StepGroup({
  message,
  parts,
  onOpenSession,
  onShowFull,
}: {
  message: Message | null
  parts: Part[]
  onOpenSession: (id: string) => void
  onShowFull: (title: string, value: string) => void
}) {
  const { t } = useLocale()
  const finish = parts.find((p) => p.type === "step-finish")
  const finishMeta = finish?.metadata_json ? JSON.parse(finish.metadata_json) : null
  const bodyParts = parts.filter((p) => p.type !== "step-start" && p.type !== "step-finish")

  return (
    <div className="step-group">
      <div className="step-group-header">
        <span>
          {t("feed.step_label")} {message?.seq ?? "?"}
          {message?.role ? ` · ${message.role}` : ""}
          {message?.elapsed_ms != null ? ` · ${fmtMs(message.elapsed_ms)}` : ""}
        </span>
        {finishMeta && (
          <span className="muted">
            {t("feed.finish_label")}: {finishMeta.reason || "?"} · +{finishMeta.tokens_output ?? 0}
          </span>
        )}
      </div>
      <div className="step-group-body">
        {bodyParts.length === 0 ? (
          <div className="muted">—</div>
        ) : (
          bodyParts.map((p) => <PartRow key={p.id} part={p} onOpenSession={onOpenSession} onShowFull={onShowFull} />)
        )}
      </div>
    </div>
  )
}

function TodoHistory({ snapshots }: { snapshots: TodoSnapshot[] }) {
  const { t } = useLocale()
  if (snapshots.length === 0) return <p className="muted">{t("todo.empty")}</p>
  return (
    <div>
      {snapshots.map((snap, i) => {
        const items: { content: string; status: string; id?: string }[] = JSON.parse(snap.items_json)
        return (
          <div key={snap.id} className="todo-snapshot">
            <div className="muted">
              {i + 1} · {snap.captured_at ?? "?"}
            </div>
            <ul>
              {items.map((it, idx) => (
                <li key={idx}>
                  [{it.status === "completed" ? "x" : it.status === "in_progress" ? "." : " "}] {it.content}
                  {!it.id && <span className="muted"> ({t("todo.no_id")})</span>}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

function Waterfall({ session, messages }: { session: SessionDetailData["session"]; messages: Message[] }) {
  const { t } = useLocale()
  const sessionStart = toMs(session.created_at)
  const sessionEnd = toMs(session.completed_at)

  const withTimes = messages
    .map((m) => ({ m, start: toMs(m.started_at), end: toMs(m.completed_at) }))
    .filter((x): x is { m: Message; start: number; end: number } => x.start != null && x.end != null)
    .sort((a, b) => a.start - b.start)

  if (sessionStart == null || sessionEnd == null || sessionEnd <= sessionStart) {
    return <p className="muted">{t("context_attrib.empty")}</p>
  }
  const totalSpan = sessionEnd - sessionStart

  type Item = { kind: "gap"; ms: number } | { kind: "message"; m: Message; start: number; end: number }
  const items: Item[] = []
  let cursor = sessionStart
  for (const w of withTimes) {
    if (w.start > cursor) items.push({ kind: "gap", ms: w.start - cursor })
    items.push({ kind: "message", m: w.m, start: w.start, end: w.end })
    cursor = Math.max(cursor, w.end)
  }
  if (sessionEnd > cursor) items.push({ kind: "gap", ms: sessionEnd - cursor })

  return (
    <div>
      <div className="waterfall-legend">
        <span>
          <span className="legend-swatch" style={{ background: "var(--accent)" }} />
          {t("waterfall.legend_model")}
        </span>
        <span>
          <span className="legend-swatch" style={{ background: "#16a34a" }} />
          {t("waterfall.legend_tool")}
        </span>
      </div>
      <div className="waterfall">
        {items.map((item, i) => {
          const widthPct = Math.max(0.5, ((item.kind === "gap" ? item.ms : item.end - item.start) / totalSpan) * 100)
          if (item.kind === "gap") {
            return (
              <div key={i} className="waterfall-row">
                <span className="waterfall-label muted">{t("waterfall.gap_label")}</span>
                <div className="waterfall-track">
                  <div className="waterfall-bar bar-gap" style={{ width: `${widthPct}%` }} />
                </div>
                <span className="muted">{fmtMs(item.ms)}</span>
              </div>
            )
          }
          const elapsed = item.end - item.start
          const toolMs = item.m.tool_time_ms || 0
          const toolPct = elapsed > 0 ? Math.min(100, (toolMs / elapsed) * 100) : 0
          return (
            <div key={i} className="waterfall-row" title={`#${item.m.seq} · ${fmtMs(elapsed)}`}>
              <span className="waterfall-label">
                #{item.m.seq} {item.m.role}
              </span>
              <div className="waterfall-track">
                <div className="waterfall-bar-container" style={{ width: `${widthPct}%` }}>
                  <div className="waterfall-bar bar-model" style={{ width: `${100 - toolPct}%` }} />
                  <div className="waterfall-bar bar-tool" style={{ width: `${toolPct}%` }} />
                </div>
              </div>
              <span className="muted">{fmtMs(elapsed)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ContextGrowth({ messages, parts }: { messages: Message[]; parts: Part[] }) {
  const { t } = useLocale()
  const assistantSteps = useMemo(() => messages.filter((m) => m.role === "assistant"), [messages])
  const [selectedId, setSelectedId] = useState<string | null>(assistantSteps.length ? assistantSteps[assistantSteps.length - 1].id : null)
  const maxInput = Math.max(1, ...assistantSteps.map((m) => m.tokens_input))

  const eligibleMessageIds = useMemo(() => {
    if (!selectedId) return new Set<string>()
    const idx = messages.findIndex((m) => m.id === selectedId)
    return new Set(messages.slice(0, idx + 1).map((m) => m.id))
  }, [selectedId, messages])

  const breakdown = useMemo(() => {
    const map = new Map<string, { tokens: number; bytes: number; cleared: number }>()
    for (const p of parts) {
      if (p.type !== "tool" || !p.message_id || !eligibleMessageIds.has(p.message_id)) continue
      const isCleared = !!p.output_text?.includes(CLEARED_MARKER)
      const key = p.tool_name || "?"
      const entry = map.get(key) || { tokens: 0, bytes: 0, cleared: 0 }
      if (isCleared) entry.cleared += p.output_tokens_est || 0
      else {
        entry.tokens += p.output_tokens_est || 0
        entry.bytes += p.output_bytes || 0
      }
      map.set(key, entry)
    }
    return Array.from(map.entries()).sort((a, b) => b[1].tokens - a[1].tokens)
  }, [eligibleMessageIds, parts])

  if (assistantSteps.length === 0) return <p className="muted">{t("context_attrib.empty")}</p>

  const selectedSeq = messages.find((m) => m.id === selectedId)?.seq

  return (
    <div>
      <p className="muted">{t("context_growth.hint")}</p>
      <div className="waterfall">
        {assistantSteps.map((m) => (
          <div key={m.id} className="waterfall-row" onClick={() => setSelectedId(m.id)} style={{ cursor: "pointer" }}>
            <span className="waterfall-label">#{m.seq}</span>
            <div className="waterfall-track">
              <div
                className="waterfall-bar bar-model"
                style={{ width: `${Math.max(1, (m.tokens_input / maxInput) * 100)}%`, opacity: m.id === selectedId ? 1 : 0.45 }}
              />
            </div>
            <span className="muted">{m.tokens_input}</span>
          </div>
        ))}
      </div>
      {selectedId && (
        <div>
          <h3>
            {t("context_growth.breakdown_title")} #{selectedSeq}
          </h3>
          {breakdown.length === 0 ? (
            <p className="muted">{t("context_attrib.empty")}</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("tools.col_tool")}</th>
                  <th>{t("tools.col_tokens_est")}</th>
                  <th>{t("context_growth.cleared_label")}</th>
                </tr>
              </thead>
              <tbody>
                {breakdown.map(([name, b]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>
                      ≈{b.tokens} ({fmtBytes(b.bytes, t)})
                    </td>
                    <td>{b.cleared > 0 ? `≈${b.cleared}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

type ToolSortKey = "name" | "calls" | "errors" | "total_ms" | "avg_ms" | "tokens_est"

export default function SessionDetail({
  sessionId,
  onOpenSession,
  onBack,
}: {
  sessionId: string
  onOpenSession: (id: string) => void
  onBack: () => void
}) {
  const { t, locale } = useLocale()
  const [data, setData] = useState<SessionDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toolFilter, setToolFilter] = useState<string | null>(null)
  const [copyStatus, setCopyStatus] = useState<string | null>(null)
  const [connected, setConnected] = useState(true)
  const [fullValue, setFullValue] = useState<{ title: string; value: string } | null>(null)
  const [notes, setNotes] = useState("")
  const [toolSort, setToolSort] = useState<{ key: ToolSortKey; dir: 1 | -1 }>({ key: "total_ms", dir: -1 })
  const esRef = useRef<EventSource | null>(null)
  const feedRef = useRef<HTMLDivElement>(null)

  function load() {
    api
      .session(sessionId)
      .then((d) => {
        setData(d)
        setNotes(d.session.notes || "")
      })
      .catch((e) => setError(String(e)))
  }

  useEffect(() => {
    load()
    const es = new EventSource(api.streamUrl(sessionId), { withCredentials: true })
    es.addEventListener("connected", () => setConnected(true))
    es.addEventListener("update", () => {
      load()
      setConnected(true)
    })
    es.onerror = () => setConnected(false)
    esRef.current = es
    return () => es.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  if (error) return <div className="error-text">{error}</div>
  if (!data) return <div className="center-message">{t("common.loading")}</div>

  const { session, messages, parts, detections, todo_snapshots, tool_stats, context_attribution } = data
  const visibleParts = toolFilter ? parts.filter((p) => p.tool_name === toolFilter) : parts
  const stepGroups = groupPartsByMessage(visibleParts, messages)

  async function copyFullLog() {
    const md = await api.exportMarkdown(sessionId)
    await navigator.clipboard.writeText(md)
    setCopyStatus(t("session.copied"))
    setTimeout(() => setCopyStatus(null), 2500)
  }

  async function saveNotes() {
    await api.updateSessionNotes(sessionId, notes || null)
  }

  function toggleSort(key: ToolSortKey) {
    setToolSort((prev) => (prev.key === key ? { key, dir: (prev.dir * -1) as 1 | -1 } : { key, dir: key === "name" ? 1 : -1 }))
  }

  function sortArrow(key: ToolSortKey) {
    return toolSort.key === key ? <span className="sort-arrow">{toolSort.dir === 1 ? "▲" : "▼"}</span> : null
  }

  const sortedTools = Object.entries(tool_stats)
    .map(([name, s]) => ({ name, ...s, avg_ms: s.calls ? s.total_ms / s.calls : 0 }))
    .sort((a, b) => {
      const av = a[toolSort.key]
      const bv = b[toolSort.key]
      if (typeof av === "string" || typeof bv === "string") return toolSort.dir * String(av).localeCompare(String(bv))
      return toolSort.dir * ((av as number) - (bv as number))
    })

  function selectTool(name: string) {
    setToolFilter((prev) => (prev === name ? null : name))
    feedRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  return (
    <div>
      {fullValue && <FullValueModal title={fullValue.title} value={fullValue.value} onClose={() => setFullValue(null)} />}
      <div className="toolbar">
        <button onClick={onBack}>{t("common.back")}</button>
        <div className="spacer" />
        <button onClick={copyFullLog}>{t("session.copy_full_log")}</button>
        <a className="button-link" href={api.exportUrl(sessionId)} download={`${sessionId}.md`}>
          {t("session.download_md")}
        </a>
      </div>
      {copyStatus && <div className="toast">{copyStatus}</div>}
      {!connected && <div className="disconnected-banner">{t("session.disconnected")}</div>}

      <h1>{session.title || t("sessions.unnamed")}</h1>

      <textarea
        className="notes-field"
        value={notes}
        placeholder={t("session.notes_placeholder")}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={saveNotes}
      />

      <div className="summary-grid">
        <div>
          <div className="stat-label">{t("summary.duration")}</div>
          <div className="stat-value">{fmtMs(session.duration_ms)}</div>
        </div>
        <div>
          <div className="stat-label">{t("summary.unaccounted")}</div>
          <div className="stat-value">
            {fmtMs(session.unaccounted_ms)}
            {session.duration_ms ? ` (${Math.round((session.unaccounted_ms / session.duration_ms) * 100)}%)` : ""}
          </div>
        </div>
        <div>
          <div className="stat-label">{t("summary.tools")}</div>
          <div className="stat-value">
            {session.tool_calls} ({session.tool_errors} {t("summary.errors_suffix")})
          </div>
        </div>
        <div>
          <div className="stat-label">{t("summary.compactions")}</div>
          <div className="stat-value">{session.compactions}</div>
        </div>
        <div>
          <div className="stat-label">{t("summary.tokens")}</div>
          <div className="stat-value">
            {session.tokens_input}/{session.tokens_output}/{session.tokens_reasoning}
          </div>
        </div>
        <div>
          <div className="stat-label">{t("summary.cache")}</div>
          <div className="stat-value">
            {session.tokens_cache_read}/{session.tokens_cache_write}
          </div>
        </div>
        <div>
          <div className="stat-label">{t("summary.model")}</div>
          <div className="stat-value">{session.model || "—"}</div>
        </div>
        <div>
          <div className="stat-label">{t("summary.project")}</div>
          <div className="stat-value">{session.project || "—"}</div>
        </div>
      </div>

      <section>
        <h2>{t("detections.title")}</h2>
        <p className="muted">{t("detections.subtitle")}</p>
        {detections.length === 0 ? (
          <p className="muted">{t("detections.empty")}</p>
        ) : (
          <div className="detection-list">
            {detections.map((d) => (
              <DetectionCard key={d.id} d={d} locale={locale} />
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>{t("messages_table.title")}</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("messages_table.col_seq")}</th>
              <th title={t("messages_table.role_help")}>{t("messages_table.col_role")}</th>
              <th>{t("messages_table.col_total")}</th>
              <th>{t("messages_table.col_tool_time")}</th>
              <th>{t("messages_table.col_model_time")}</th>
              <th>{t("messages_table.col_input")}</th>
              <th>{t("messages_table.col_output")}</th>
              <th title={t("messages_table.cache_help")}>{t("messages_table.col_cache_read")}</th>
            </tr>
          </thead>
          <tbody>
            {messages.map((m) => (
              <tr key={m.id}>
                <td>{m.seq}</td>
                <td>{m.role}</td>
                <td>{fmtMs(m.elapsed_ms)}</td>
                <td>{fmtMs(m.tool_time_ms)}</td>
                <td>{fmtMs(m.model_time_ms)}</td>
                <td>{m.tokens_input}</td>
                <td>{m.tokens_output}</td>
                <td>{m.tokens_cache_read}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>{t("waterfall.title")}</h2>
        <Waterfall session={session} messages={messages} />
        {session.unaccounted_ms > 0 && (
          <div className="unaccounted-banner">
            {t("waterfall.gap_label")}: {fmtMs(session.unaccounted_ms)}
          </div>
        )}
      </section>

      <section>
        <h2>{t("tools.title")}</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th className="sortable-th" onClick={() => toggleSort("name")}>
                {t("tools.col_tool")} {sortArrow("name")}
              </th>
              <th className="sortable-th" onClick={() => toggleSort("calls")}>
                {t("tools.col_calls")} {sortArrow("calls")}
              </th>
              <th className="sortable-th" onClick={() => toggleSort("errors")}>
                {t("tools.col_errors")} {sortArrow("errors")}
              </th>
              <th className="sortable-th" onClick={() => toggleSort("total_ms")}>
                {t("tools.col_total")} {sortArrow("total_ms")}
              </th>
              <th className="sortable-th" onClick={() => toggleSort("avg_ms")}>
                {t("tools.col_avg")} {sortArrow("avg_ms")}
              </th>
              <th className="sortable-th" onClick={() => toggleSort("tokens_est")}>
                {t("tools.col_tokens_est")} {sortArrow("tokens_est")}
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedTools.map((s) => (
              <tr key={s.name} className={`clickable-row ${toolFilter === s.name ? "clickable-row-active" : ""}`} onClick={() => selectTool(s.name)}>
                <td>{s.name}</td>
                <td>{s.calls}</td>
                <td>{s.errors}</td>
                <td>{fmtMs(s.total_ms)}</td>
                <td>{fmtMs(s.avg_ms)}</td>
                <td>≈{s.tokens_est}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>{t("context_attrib.title")}</h2>
        {context_attribution.length === 0 ? (
          <p className="muted">{t("context_attrib.empty")}</p>
        ) : (
          <ul>
            {context_attribution.map((c) => (
              <li key={c.part_id}>
                {c.seq} · {c.tool_name || "?"} · ≈{c.output_tokens_est}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>{t("context_growth.title")}</h2>
        <ContextGrowth messages={messages} parts={parts} />
      </section>

      <section>
        <h2>{t("todo.title")}</h2>
        <TodoHistory snapshots={todo_snapshots} />
      </section>

      <section ref={feedRef}>
        <h2>{t("feed.title")}</h2>
        {toolFilter && (
          <div className="filter-banner">
            <span>
              {t("tools.filter_banner_prefix")} «{toolFilter}»
            </span>
            <button onClick={() => setToolFilter(null)}>{t("tools.filter_reset")}</button>
          </div>
        )}
        <div className="feed">
          {stepGroups.map((g, i) => (
            <StepGroup key={g.message?.id || i} message={g.message} parts={g.parts} onOpenSession={onOpenSession} onShowFull={(title, value) => setFullValue({ title, value })} />
          ))}
        </div>
      </section>
    </div>
  )
}
