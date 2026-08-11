import { useEffect, useRef, useState } from "react"
import { api, Part, SessionDetail as SessionDetailData, TodoSnapshot } from "../api"

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "?"
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} с`
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`
}

function levelClass(level: string): string {
  return level === "bad" ? "badge-bad" : level === "warn" ? "badge-warn" : "badge-info"
}

function PartRow({ part }: { part: Part }) {
  const [open, setOpen] = useState(false)
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
          {part.text && <pre className="feed-pre">{part.text}</pre>}
          {part.input_json && (
            <>
              <div className="muted">Вход:</div>
              <pre className="feed-pre">{part.input_json}</pre>
            </>
          )}
          {part.output_text && (
            <>
              <div className="muted">Выход:</div>
              <pre className="feed-pre">{part.output_text}</pre>
            </>
          )}
          {part.error && <div className="error-text">Ошибка: {part.error}</div>}
        </div>
      )}
    </div>
  )
}

function TodoHistory({ snapshots }: { snapshots: TodoSnapshot[] }) {
  if (snapshots.length === 0) return <p className="muted">Todo-снимков не было.</p>
  return (
    <div>
      {snapshots.map((snap, i) => {
        const items: { content: string; status: string; id?: string }[] = JSON.parse(snap.items_json)
        return (
          <div key={snap.id} className="todo-snapshot">
            <div className="muted">
              Снимок {i + 1} · {snap.captured_at ?? "?"}
            </div>
            <ul>
              {items.map((it, idx) => (
                <li key={idx}>
                  [{it.status === "completed" ? "x" : it.status === "in_progress" ? "." : " "}] {it.content}
                  {!it.id && <span className="muted"> (без id)</span>}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}

export default function SessionDetail({ sessionId, onBack }: { sessionId: string; onBack: () => void }) {
  const [data, setData] = useState<SessionDetailData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [toolFilter, setToolFilter] = useState<string | null>(null)
  const [copyStatus, setCopyStatus] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  function load() {
    api
      .session(sessionId)
      .then(setData)
      .catch((e) => setError(String(e)))
  }

  useEffect(() => {
    load()
    const es = new EventSource(api.streamUrl(sessionId), { withCredentials: true })
    es.addEventListener("update", () => load())
    esRef.current = es
    return () => es.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  if (error) return <div className="error-text">{error}</div>
  if (!data) return <div className="center-message">Загрузка…</div>

  const { session, messages, parts, detections, todo_snapshots, tool_stats, context_attribution } = data
  const visibleParts = toolFilter ? parts.filter((p) => p.tool_name === toolFilter) : parts

  async function copyFullLog() {
    const md = await api.exportMarkdown(sessionId)
    await navigator.clipboard.writeText(md)
    setCopyStatus("Скопировано в буфер обмена")
    setTimeout(() => setCopyStatus(null), 2500)
  }

  return (
    <div>
      <div className="toolbar">
        <button onClick={onBack}>← Назад</button>
        <div className="spacer" />
        <button onClick={copyFullLog}>Скопировать полный лог</button>
        <a className="button-link" href={api.exportUrl(sessionId)} download={`${sessionId}.md`}>
          Скачать .md
        </a>
      </div>
      {copyStatus && <div className="toast">{copyStatus}</div>}

      <h1>{session.title || "(без названия)"}</h1>

      <div className="summary-grid">
        <div>
          <div className="stat-label">Длительность</div>
          <div className="stat-value">{fmtMs(session.duration_ms)}</div>
        </div>
        <div>
          <div className="stat-label">Не покрыто событиями</div>
          <div className="stat-value">
            {fmtMs(session.unaccounted_ms)}
            {session.duration_ms ? ` (${Math.round((session.unaccounted_ms / session.duration_ms) * 100)}%)` : ""}
          </div>
        </div>
        <div>
          <div className="stat-label">Инструменты</div>
          <div className="stat-value">
            {session.tool_calls} ({session.tool_errors} ошибок)
          </div>
        </div>
        <div>
          <div className="stat-label">Компакции</div>
          <div className="stat-value">{session.compactions}</div>
        </div>
        <div>
          <div className="stat-label">Токены in/out/reasoning</div>
          <div className="stat-value">
            {session.tokens_input}/{session.tokens_output}/{session.tokens_reasoning}
          </div>
        </div>
        <div>
          <div className="stat-label">Cache read/write</div>
          <div className="stat-value">
            {session.tokens_cache_read}/{session.tokens_cache_write}
          </div>
        </div>
        <div>
          <div className="stat-label">Модель</div>
          <div className="stat-value">{session.model || "—"}</div>
        </div>
        <div>
          <div className="stat-label">Проект</div>
          <div className="stat-value">{session.project || "—"}</div>
        </div>
      </div>

      <section>
        <h2>Что видно сразу</h2>
        {detections.length === 0 ? (
          <p className="muted">Детекторы ничего не нашли.</p>
        ) : (
          <div className="detection-list">
            {detections.map((d) => (
              <div key={d.id} className="detection-card">
                <span className={`badge ${levelClass(d.level)}`}>{d.level}</span>
                <strong>{d.kind}</strong>
                <p>{d.message}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2>Шаги модели</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Роль</th>
              <th>Всего</th>
              <th>В инструментах</th>
              <th>У модели</th>
              <th>Input</th>
              <th>Output</th>
              <th>Cache read</th>
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
        <h2>Waterfall</h2>
        <div className="waterfall">
          {parts
            .filter((p) => p.duration_ms)
            .map((p) => {
              const maxDuration = Math.max(...parts.map((x) => x.duration_ms || 0), 1)
              const widthPct = Math.max(1, ((p.duration_ms || 0) / maxDuration) * 100)
              const estimated = !p.started_at || !p.ended_at
              return (
                <div key={p.id} className="waterfall-row" title={`${p.type} ${p.tool_name ?? ""} — ${fmtMs(p.duration_ms)}`}>
                  <span className="waterfall-label">
                    #{p.seq} {p.tool_name || p.type}
                  </span>
                  <div className="waterfall-track">
                    <div
                      className={`waterfall-bar ${p.type === "tool" ? "bar-tool" : "bar-model"} ${estimated ? "bar-estimated" : ""}`}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <span className="muted">{fmtMs(p.duration_ms)}</span>
                </div>
              )
            })}
        </div>
        {session.unaccounted_ms > 0 && (
          <div className="unaccounted-banner">нет событий: {fmtMs(session.unaccounted_ms)}</div>
        )}
      </section>

      <section>
        <h2>Инструменты</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>Инструмент</th>
              <th>Вызовов</th>
              <th>Ошибок</th>
              <th>Всего</th>
              <th>Среднее</th>
              <th>≈токенов вывода</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(tool_stats).map(([name, s]) => (
              <tr key={name} className="clickable-row" onClick={() => setToolFilter(toolFilter === name ? null : name)}>
                <td>
                  {name}
                  {toolFilter === name && <span className="badge badge-info"> фильтр активен</span>}
                </td>
                <td>{s.calls}</td>
                <td>{s.errors}</td>
                <td>{fmtMs(s.total_ms)}</td>
                <td>{fmtMs(s.total_ms / s.calls)}</td>
                <td>≈{s.tokens_est}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section>
        <h2>Чем заполнялся контекст</h2>
        {context_attribution.length === 0 ? (
          <p className="muted">Нет данных.</p>
        ) : (
          <ul>
            {context_attribution.map((c) => (
              <li key={c.part_id}>
                шаг {c.seq} · {c.tool_name || "?"} · ≈{c.output_tokens_est} токенов
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>История плана</h2>
        <TodoHistory snapshots={todo_snapshots} />
      </section>

      <section>
        <h2>
          Лента шагов {toolFilter && <button onClick={() => setToolFilter(null)}>сбросить фильтр «{toolFilter}»</button>}
        </h2>
        <div className="feed">
          {visibleParts.map((p) => (
            <PartRow key={p.id} part={p} />
          ))}
        </div>
      </section>
    </div>
  )
}
