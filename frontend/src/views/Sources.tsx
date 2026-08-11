import { useEffect, useState } from "react"
import { api, Source } from "../api"

function timeAgo(iso: string | null): string {
  if (!iso) return "—"
  const ms = Date.now() - new Date(iso).getTime()
  const min = Math.floor(ms / 60000)
  if (min < 1) return "только что"
  if (min < 60) return `${min} мин назад`
  const hours = Math.floor(min / 60)
  if (hours < 24) return `${hours} ч назад`
  return `${Math.floor(hours / 24)} дн назад`
}

const ENV_SNIPPET = `OPENCODE_LOG_VIEWER_URL=http://<адрес-этого-вьювера>:8080
OPENCODE_LOG_VIEWER_SECRET=<ingest secret из .env вьювера>`

export default function Sources({ onOpenSource }: { onOpenSource: (id: string) => void }) {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .sources()
      .then(setSources)
      .catch((e) => setError(String(e)))
  }, [])

  if (error) return <div className="error-text">{error}</div>
  if (!sources) return <div className="center-message">Загрузка…</div>

  if (sources.length === 0) {
    return (
      <div className="empty-state">
        <h2>Пока нет ни одного агента</h2>
        <p>
          Источник появится здесь автоматически после первого события от плагина. Ничего заводить в
          интерфейсе руками не нужно — положите плагин в <code>.opencode/plugin/</code> агента и
          укажите адрес этого вьювера:
        </p>
        <pre>{ENV_SNIPPET}</pre>
        <p>Если у агента уже есть история прошлых сессий — импортируйте её один раз на странице «Настройки».</p>
      </div>
    )
  }

  return (
    <div>
      <h1>Агенты</h1>
      <table className="data-table">
        <thead>
          <tr>
            <th>Источник</th>
            <th>Сессий</th>
            <th>Последняя активность</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id} className="clickable-row" onClick={() => onOpenSource(s.id)}>
              <td>
                <strong>{s.name}</strong>
                <div className="muted">{s.hostname}</div>
              </td>
              <td>{s.session_count}</td>
              <td>{timeAgo(s.last_session_at)}</td>
              <td>{s.active_count > 0 ? <span className="badge badge-active">активен</span> : <span className="muted">—</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
