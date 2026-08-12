import { useEffect, useState } from "react"
import { api, ApiError, RedactPattern } from "../api"
import { useLocale } from "../i18n"
import { fmtBytes } from "../format"

function RedactPatternsSection() {
  const { t } = useLocale()
  const [patterns, setPatterns] = useState<RedactPattern[] | null>(null)
  const [newPattern, setNewPattern] = useState("")
  const [error, setError] = useState<string | null>(null)

  function reload() {
    api.redactPatterns().then(setPatterns).catch((e) => setError(String(e)))
  }

  useEffect(reload, [])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      await api.addRedactPattern(newPattern)
      setNewPattern("")
      reload()
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    }
  }

  async function toggle(p: RedactPattern) {
    await api.toggleRedactPattern(p.id, !p.enabled)
    reload()
  }

  async function remove(p: RedactPattern) {
    await api.deleteRedactPattern(p.id)
    reload()
  }

  return (
    <section className="settings-card">
      <h2>{t("settings.redact_title")}</h2>
      <p>{t("settings.redact_body")}</p>
      <p className="muted">{t("settings.redact_guid_hint")}</p>

      {!patterns ? (
        <p className="muted">{t("common.loading")}</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>{t("settings.redact_col_pattern")}</th>
              <th>{t("settings.redact_col_status")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {patterns.map((p) => (
              <tr key={p.id}>
                <td>
                  <code>{p.pattern}</code>
                  {p.is_default === 1 && <span className="badge badge-muted">{t("settings.redact_default_badge")}</span>}
                </td>
                <td>
                  <label className="checkbox-label">
                    <input type="checkbox" checked={p.enabled === 1} onChange={() => toggle(p)} />
                    {p.enabled === 1 ? t("settings.redact_enabled") : t("settings.redact_disabled")}
                  </label>
                </td>
                <td>
                  <button onClick={() => remove(p)}>{t("settings.redact_delete")}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form onSubmit={add} className="settings-form">
        <label>
          <input value={newPattern} onChange={(e) => setNewPattern(e.target.value)} placeholder={t("settings.redact_add_placeholder")} required />
        </label>
        <button type="submit">{t("settings.redact_add_button")}</button>
      </form>
      {error && <div className="error-text">{error}</div>}
    </section>
  )
}

function StorageSection() {
  const { t } = useLocale()
  const [dbSize, setDbSize] = useState<number | null>(null)
  const [olderThanDays, setOlderThanDays] = useState(90)
  const [estimate, setEstimate] = useState<{ sessions_count: number; estimated_bytes: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [deleted, setDeleted] = useState<number | null>(null)

  useEffect(() => {
    api.adminStorage().then((r) => setDbSize(r.db_size_bytes))
  }, [deleted])

  async function calculate() {
    setBusy(true)
    setEstimate(null)
    try {
      setEstimate(await api.cleanupEstimate(olderThanDays))
    } finally {
      setBusy(false)
    }
  }

  async function execute() {
    if (!window.confirm(t("settings.storage_delete_confirm"))) return
    setBusy(true)
    try {
      const r = await api.cleanupExecute(olderThanDays)
      setDeleted(r.deleted_sessions)
      setEstimate(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="settings-card">
      <h2>{t("settings.storage_title")}</h2>
      <p>
        {t("settings.storage_current")}: <strong>{dbSize != null ? fmtBytes(dbSize, t) : "…"}</strong>
      </p>
      <div className="settings-form">
        <label>
          {t("settings.storage_older_than_label")}
          <input
            type="number"
            min={0}
            value={olderThanDays}
            onChange={(e) => setOlderThanDays(Number(e.target.value))}
          />
        </label>
        <div className="toolbar">
          <button onClick={calculate} disabled={busy}>
            {busy ? t("settings.storage_calculating") : t("settings.storage_calculate")}
          </button>
          {estimate && estimate.sessions_count > 0 && (
            <button onClick={execute} disabled={busy}>
              {t("settings.storage_delete_button")}
            </button>
          )}
        </div>
      </div>
      {estimate && (
        <p className="muted">
          {t("settings.storage_estimate_sessions")}: {estimate.sessions_count} · {t("settings.storage_estimate_bytes")}: ≈
          {fmtBytes(estimate.estimated_bytes, t)}
        </p>
      )}
      {deleted != null && (
        <div className="toast toast-success">
          {t("settings.storage_deleted")}: {deleted}
        </div>
      )}
    </section>
  )
}

export default function Settings() {
  const { t } = useLocale()
  const [path, setPath] = useState("/import/opencode")
  const [sourceName, setSourceName] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ accepted: number; duplicates: number; rejected: number; sessions_touched: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function runImport(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.importStorage(path, sourceName)
      setResult(r)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1>{t("settings.title")}</h1>

      <section className="settings-card">
        <h2>{t("settings.import_title")}</h2>
        <p>{t("settings.import_body")}</p>
        <form onSubmit={runImport} className="settings-form">
          <label>
            {t("settings.path_label")}
            <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/import/opencode" required />
          </label>
          <label>
            {t("settings.source_name_label")}
            <input value={sourceName} onChange={(e) => setSourceName(e.target.value)} placeholder="my-agent" required />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? t("settings.importing") : t("settings.import_button")}
          </button>
        </form>
        {result && (
          <div className="toast toast-success">
            {t("settings.result_accepted")}: {result.accepted} · {t("settings.result_duplicates")}: {result.duplicates} ·{" "}
            {t("settings.result_rejected")}: {result.rejected} · {t("settings.result_sessions")}: {result.sessions_touched}
          </div>
        )}
        {error && <div className="error-text">{error}</div>}
        <p className="muted">{t("settings.layouts_note")}</p>
      </section>

      <RedactPatternsSection />
      <StorageSection />
    </div>
  )
}
