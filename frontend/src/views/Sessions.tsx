import { useEffect, useMemo, useState } from "react"
import { api, Session } from "../api"

function fmtMs(ms: number | null): string {
  if (ms == null) return "?"
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} с`
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString()
}

export default function Sessions({ sourceId, onOpenSession }: { sourceId: string; onOpenSession: (id: string) => void }) {
  const [sessions, setSessions] = useState<Session[] | null>(null)
  const [onlyErrors, setOnlyErrors] = useState(false)
  const [q, setQ] = useState("")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSessions(null)
    api
      .sessions({ source_id: sourceId, has_errors: onlyErrors ? "true" : undefined, q: q || undefined })
      .then(setSessions)
      .catch((e) => setError(String(e)))
  }, [sourceId, onlyErrors, q])

  const bySession = useMemo(() => {
    const map = new Map<string, Session>()
    sessions?.forEach((s) => map.set(s.id, s))
    return map
  }, [sessions])

  const topLevel = useMemo(() => sessions?.filter((s) => !s.parent_id || !bySession.has(s.parent_id)), [sessions, bySession])
  const childrenOf = (id: string) => sessions?.filter((s) => s.parent_id === id) ?? []

  if (error) return <div className="error-text">{error}</div>

  function renderRow(s: Session, depth: number): JSX.Element {
    return (
      <>
        <tr key={s.id} className="clickable-row" onClick={() => onOpenSession(s.id)}>
          <td style={{ paddingLeft: `${depth * 1.5 + 0.5}rem` }}>
            {depth > 0 && "↳ "}
            {s.title || "(без названия)"}
          </td>
          <td>{fmtDate(s.created_at)}</td>
          <td>{fmtMs(s.duration_ms)}</td>
          <td>{s.model || "—"}</td>
          <td>
            {s.tokens_input}/{s.tokens_output}
          </td>
          <td>{s.tool_calls}</td>
          <td>
            {s.error_count > 0 || s.tool_errors > 0 ? <span className="badge badge-bad">ошибка</span> : null}
            {s.compactions > 0 ? <span className="badge badge-warn">компакция</span> : null}
          </td>
        </tr>
        {childrenOf(s.id).map((c) => renderRow(c, depth + 1))}
      </>
    )
  }

  return (
    <div>
      <div className="toolbar">
        <input placeholder="Поиск по заголовку и содержимому…" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="checkbox-label">
          <input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} />
          Только с ошибками
        </label>
      </div>
      {!sessions ? (
        <div className="center-message">Загрузка…</div>
      ) : sessions.length === 0 ? (
        <div className="empty-state">
          <p>У этого источника пока нет сессий, подходящих под фильтр.</p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Сессия</th>
              <th>Начало</th>
              <th>Длительность</th>
              <th>Модель</th>
              <th>Токены in/out</th>
              <th>Инструменты</th>
              <th>Флаги</th>
            </tr>
          </thead>
          <tbody>{topLevel?.map((s) => renderRow(s, 0))}</tbody>
        </table>
      )}
    </div>
  )
}
