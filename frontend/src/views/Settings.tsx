import { useState } from "react"
import { api, ApiError } from "../api"

export default function Settings() {
  const [path, setPath] = useState("/import/opencode")
  const [sourceName, setSourceName] = useState("")
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function runImport(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.importStorage(path, sourceName)
      setResult(
        `Готово: принято ${r.accepted} событий, дубликатов ${r.duplicates}, отклонено ${r.rejected}, затронуто сессий: ${r.sessions_touched}.`,
      )
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1>Настройки</h1>

      <section className="settings-card">
        <h2>Импорт уже существующих сессий</h2>
        <p>
          Разовое действие: подтягивает историю сессий, которые агент накопил ещё до подключения
          плагина, из локального хранилища OpenCode. Дальше новые сессии будут появляться сами —
          повторный запуск с теми же данными безопасен и не создаёт дублей (идемпотентно по
          <code> event_id</code>).
        </p>
        <form onSubmit={runImport} className="settings-form">
          <label>
            Путь к хранилищу OpenCode (примонтирован в контейнер вьювера только на чтение)
            <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/import/opencode" required />
          </label>
          <label>
            Имя источника (как будет называться агент в списке)
            <input value={sourceName} onChange={(e) => setSourceName(e.target.value)} placeholder="my-agent" required />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? "Импортирую…" : "Импортировать все существующие сессии"}
          </button>
        </form>
        {result && <div className="toast toast-success">{result}</div>}
        {error && <div className="error-text">{error}</div>}
        <p className="muted">
          Поддерживаются обе раскладки хранилища OpenCode: набор JSON-файлов (
          <code>storage/session|message|part|todo</code>) и SQLite (<code>opencode.db</code>) — формат
          определяется автоматически.
        </p>
      </section>
    </div>
  )
}
