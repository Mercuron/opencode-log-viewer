import { useState } from "react"
import { api, ApiError } from "../api"
import { useLocale } from "../i18n"

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
    </div>
  )
}
