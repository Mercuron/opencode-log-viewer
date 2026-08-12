import { useState } from "react"
import { api } from "../api"
import { useLocale } from "../i18n"

export default function Login({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { t } = useLocale()
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
      setError(t("login.error"))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-message">
      <form className="login-form" onSubmit={submit}>
        <h1>{t("login.title")}</h1>
        <p>{t("login.subtitle")}</p>
        <input
          type="password"
          placeholder={t("login.password_placeholder")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
        <button type="submit" disabled={busy}>
          {t("login.button")}
        </button>
        {error && <div className="error-text">{error}</div>}
      </form>
    </div>
  )
}
