import { useEffect, useState } from "react"
import { useHashRoute } from "./useHashRoute"
import { api, ApiError } from "./api"
import { useLocale } from "./i18n"
import Login from "./views/Login"
import Sources from "./views/Sources"
import Sessions from "./views/Sessions"
import SessionDetail from "./views/SessionDetail"
import Settings from "./views/Settings"

type AuthState = "checking" | "authed" | "anonymous"

export default function App() {
  const [route, navigate] = useHashRoute()
  const [auth, setAuth] = useState<AuthState>("checking")
  const { t, locale, setLocale } = useLocale()

  useEffect(() => {
    api
      .sources()
      .then(() => setAuth("authed"))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setAuth("anonymous")
        else setAuth("authed") // UI auth disabled server-side, or a transient error - don't lock the user out
      })
  }, [])

  if (auth === "checking") return <div className="center-message">{t("common.loading")}</div>
  if (auth === "anonymous") {
    return <Login onLoggedIn={() => setAuth("authed")} />
  }

  const parts = route.split("/").filter(Boolean)

  let body: React.ReactNode
  if (parts[0] === "sources" && parts[1] && parts[2] === "sessions") {
    body = <Sessions sourceId={parts[1]} onOpenSession={(id) => navigate(`/sessions/${id}`)} />
  } else if (parts[0] === "sessions" && parts[1]) {
    body = <SessionDetail sessionId={parts[1]} onOpenSession={(id) => navigate(`/sessions/${id}`)} onBack={() => window.history.back()} />
  } else if (parts[0] === "settings") {
    body = <Settings />
  } else {
    body = <Sources onOpenSource={(id) => navigate(`/sources/${id}/sessions`)} />
  }

  const onSources = parts[0] === "sources" || parts.length === 0
  const onSettings = parts[0] === "settings"

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="#/sources">
          OpenCode Trace Viewer
        </a>
        <nav className="nav-bar">
          <a className={`nav-button ${onSources ? "nav-button-active" : ""}`} href="#/sources">
            {t("nav.sources")}
          </a>
          <a className={`nav-button ${onSettings ? "nav-button-active" : ""}`} href="#/settings">
            {t("nav.settings")}
          </a>
          <div className="lang-switch">
            <button className={`lang-option ${locale === "ru" ? "lang-option-active" : ""}`} onClick={() => setLocale("ru")}>
              RU
            </button>
            <span className="lang-sep">|</span>
            <button className={`lang-option ${locale === "en" ? "lang-option-active" : ""}`} onClick={() => setLocale("en")}>
              ENG
            </button>
          </div>
          <button
            className="nav-button"
            onClick={() => {
              api.logout().finally(() => setAuth("anonymous"))
            }}
          >
            {t("nav.logout")}
          </button>
        </nav>
      </header>
      <main className="app-main">{body}</main>
    </div>
  )
}
