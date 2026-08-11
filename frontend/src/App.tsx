import { useEffect, useState } from "react"
import { useHashRoute } from "./useHashRoute"
import { api, ApiError } from "./api"
import Login from "./views/Login"
import Sources from "./views/Sources"
import Sessions from "./views/Sessions"
import SessionDetail from "./views/SessionDetail"
import Settings from "./views/Settings"

type AuthState = "checking" | "authed" | "anonymous"

export default function App() {
  const [route, navigate] = useHashRoute()
  const [auth, setAuth] = useState<AuthState>("checking")

  useEffect(() => {
    api
      .sources()
      .then(() => setAuth("authed"))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setAuth("anonymous")
        else setAuth("authed") // UI auth disabled server-side, or a transient error - don't lock the user out
      })
  }, [])

  if (auth === "checking") return <div className="center-message">Загрузка…</div>
  if (auth === "anonymous") {
    return <Login onLoggedIn={() => setAuth("authed")} />
  }

  const parts = route.split("/").filter(Boolean)

  let body: React.ReactNode
  if (parts[0] === "sources" && parts[1] && parts[2] === "sessions") {
    body = <Sessions sourceId={parts[1]} onOpenSession={(id) => navigate(`/sessions/${id}`)} />
  } else if (parts[0] === "sessions" && parts[1]) {
    body = <SessionDetail sessionId={parts[1]} onBack={() => window.history.back()} />
  } else if (parts[0] === "settings") {
    body = <Settings />
  } else {
    body = <Sources onOpenSource={(id) => navigate(`/sources/${id}/sessions`)} />
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <a className="brand" href="#/sources">
          OpenCode Trace Viewer
        </a>
        <nav>
          <a href="#/sources">Агенты</a>
          <a href="#/settings">Настройки</a>
          <button
            className="link-button"
            onClick={() => {
              api.logout().finally(() => setAuth("anonymous"))
            }}
          >
            Выйти
          </button>
        </nav>
      </header>
      <main className="app-main">{body}</main>
    </div>
  )
}
