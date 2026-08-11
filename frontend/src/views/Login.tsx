import { useState } from "react"
import { api } from "../api"

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(password)
      onLoggedIn()
    } catch {
      setError("Неверный пароль")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-message">
      <form className="login-form" onSubmit={submit}>
        <h1>OpenCode Trace Viewer</h1>
        <p>Вьювер содержит выдержки из боевых логов агентов. Доступ ограничен паролем.</p>
        <input
          type="password"
          placeholder="Пароль"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
        <button type="submit" disabled={busy}>
          Войти
        </button>
        {error && <div className="error-text">{error}</div>}
      </form>
    </div>
  )
}
