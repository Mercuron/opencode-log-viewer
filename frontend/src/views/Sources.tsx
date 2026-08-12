import { useEffect, useState } from "react"
import { api, Source } from "../api"
import { useLocale } from "../i18n"

const ENV_SNIPPET = `OPENCODE_LOG_VIEWER_URL=http://<адрес-этого-вьювера>:8080
OPENCODE_LOG_VIEWER_SECRET=<ingest secret из .env вьювера>`

function RenameableSourceName({ source, onRenamed }: { source: Source; onRenamed: (displayName: string | null) => void }) {
  const { t } = useLocale()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(source.display_name ?? "")

  async function save() {
    const trimmed = value.trim()
    await api.renameSource(source.id, trimmed || null)
    onRenamed(trimmed || null)
    setEditing(false)
  }

  if (editing) {
    return (
      <input
        autoFocus
        value={value}
        placeholder={t("sources.rename_placeholder")}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter") save()
          if (e.key === "Escape") setEditing(false)
        }}
        onClick={(e) => e.stopPropagation()}
      />
    )
  }

  return (
    <span
      className="editable-label"
      title={t("sources.rename_hint")}
      onClick={(e) => {
        e.stopPropagation()
        setEditing(true)
      }}
    >
      <strong>{source.display_name || source.name}</strong>
      <span className="edit-pencil">✎</span>
    </span>
  )
}

export default function Sources({ onOpenSource }: { onOpenSource: (id: string) => void }) {
  const { t } = useLocale()
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .sources()
      .then(setSources)
      .catch((e) => setError(String(e)))
  }, [])

  function timeAgo(iso: string | null): string {
    if (!iso) return t("sources.time_never")
    const ms = Date.now() - new Date(iso).getTime()
    const min = Math.floor(ms / 60000)
    if (min < 1) return t("sources.time_now")
    if (min < 60) return `${min} ${t("sources.time_min_ago")}`
    const hours = Math.floor(min / 60)
    if (hours < 24) return `${hours} ${t("sources.time_hours_ago")}`
    return `${Math.floor(hours / 24)} ${t("sources.time_days_ago")}`
  }

  if (error) return <div className="error-text">{error}</div>
  if (!sources) return <div className="center-message">{t("common.loading")}</div>

  if (sources.length === 0) {
    return (
      <div className="empty-state">
        <h2>{t("sources.empty_title")}</h2>
        <p>{t("sources.empty_body")}</p>
        <pre>{ENV_SNIPPET}</pre>
        <p>{t("sources.empty_import_hint")}</p>
      </div>
    )
  }

  function updateLocal(id: string, displayName: string | null) {
    setSources((prev) => prev && prev.map((s) => (s.id === id ? { ...s, display_name: displayName } : s)))
  }

  return (
    <div>
      <h1>{t("sources.title")}</h1>
      <table className="data-table">
        <thead>
          <tr>
            <th>{t("sources.col_source")}</th>
            <th>{t("sources.col_sessions")}</th>
            <th>{t("sources.col_last_activity")}</th>
            <th>{t("sources.col_status")}</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id} className="clickable-row" onClick={() => onOpenSource(s.id)}>
              <td>
                <RenameableSourceName source={s} onRenamed={(v) => updateLocal(s.id, v)} />
                <div className="muted">
                  {s.name} · {s.hostname}
                </div>
              </td>
              <td>{s.session_count}</td>
              <td>{timeAgo(s.last_session_at)}</td>
              <td>{s.active_count > 0 ? <span className="badge badge-active">{t("sources.active")}</span> : <span className="muted">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
