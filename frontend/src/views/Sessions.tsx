import { useEffect, useMemo, useState } from "react"
import { api, Session } from "../api"
import { useLocale } from "../i18n"
import { fmtMs } from "../format"

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString()
}

export default function Sessions({ sourceId, onOpenSession }: { sourceId: string; onOpenSession: (id: string) => void }) {
  const { t } = useLocale()
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
            {depth > 0 && s.agent && <span className="subagent-badge">{s.agent}</span>}
            {s.title || t("sessions.unnamed")}
          </td>
          <td>{fmtDate(s.created_at)}</td>
          <td>{fmtMs(s.duration_ms)}</td>
          <td>{s.model || "—"}</td>
          <td>
            {s.tokens_input}/{s.tokens_output}
          </td>
          <td>{s.tool_calls}</td>
          <td>
            {s.error_count > 0 || s.tool_errors > 0 ? <span className="badge badge-bad">{t("sessions.badge_error")}</span> : null}
            {s.compactions > 0 ? <span className="badge badge-warn">{t("sessions.badge_compaction")}</span> : null}
          </td>
          <td className="notes-cell" title={s.notes || ""}>
            {s.notes || ""}
          </td>
        </tr>
        {childrenOf(s.id).map((c) => renderRow(c, depth + 1))}
      </>
    )
  }

  return (
    <div>
      <div className="toolbar">
        <input placeholder={t("sessions.search_placeholder")} value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="checkbox-label">
          <input type="checkbox" checked={onlyErrors} onChange={(e) => setOnlyErrors(e.target.checked)} />
          {t("sessions.only_errors")}
        </label>
      </div>
      {!sessions ? (
        <div className="center-message">{t("common.loading")}</div>
      ) : sessions.length === 0 ? (
        <div className="empty-state">
          <p>{t("sessions.empty")}</p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("sessions.col_session")}</th>
              <th>{t("sessions.col_start")}</th>
              <th>{t("sessions.col_duration")}</th>
              <th>{t("sessions.col_model")}</th>
              <th>{t("sessions.col_tokens")}</th>
              <th>{t("sessions.col_tools")}</th>
              <th>{t("sessions.col_flags")}</th>
              <th>{t("sessions.col_notes")}</th>
            </tr>
          </thead>
          <tbody>{topLevel?.map((s) => renderRow(s, 0))}</tbody>
        </table>
      )}
    </div>
  )
}
