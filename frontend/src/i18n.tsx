import { createContext, useContext, useState, useCallback, useMemo } from "react"
import type { ReactNode } from "react"

export type Locale = "ru" | "en"

const STORAGE_KEY = "opencode-viewer-locale"

// UI chrome only. Server-generated content (detector messages, agent
// session data, error text from tools) is never translated - it's factual
// data in whatever language it was produced, not interface copy. See
// CLAUDE.md for the full rule.
const dict = {
  ru: {
    "nav.sources": "Агенты",
    "nav.settings": "Настройки",
    "nav.logout": "Выйти",
    "common.loading": "Загрузка…",
    "common.back": "← Назад",

    "login.title": "OpenCode Trace Viewer",
    "login.subtitle": "Вьювер содержит выдержки из боевых логов агентов. Доступ ограничен паролем.",
    "login.password_placeholder": "Пароль",
    "login.button": "Войти",
    "login.error": "Неверный пароль",

    "sources.title": "Агенты",
    "sources.col_source": "Источник",
    "sources.col_sessions": "Сессий",
    "sources.col_last_activity": "Последняя активность",
    "sources.col_status": "Статус",
    "sources.active": "активен",
    "sources.empty_title": "Пока нет ни одного агента",
    "sources.empty_body":
      "Источник появится здесь автоматически после первого события от плагина. Ничего заводить в интерфейсе руками не нужно — положите плагин в .opencode/plugin/ агента и укажите адрес этого вьювера:",
    "sources.empty_import_hint": "Если у агента уже есть история прошлых сессий — импортируйте её один раз на странице «Настройки».",
    "sources.rename_hint": "Нажмите, чтобы задать человекочитаемое имя",
    "sources.rename_placeholder": "Человекочитаемое имя источника",
    "sources.time_now": "только что",
    "sources.time_min_ago": "мин назад",
    "sources.time_hours_ago": "ч назад",
    "sources.time_days_ago": "дн назад",
    "sources.time_never": "—",

    "sessions.search_placeholder": "Поиск по заголовку и содержимому…",
    "sessions.only_errors": "Только с ошибками",
    "sessions.empty": "У этого источника пока нет сессий, подходящих под фильтр.",
    "sessions.col_session": "Сессия",
    "sessions.col_start": "Начало",
    "sessions.col_duration": "Длительность",
    "sessions.col_model": "Модель",
    "sessions.col_tokens": "Токены in/out",
    "sessions.col_tools": "Инструменты",
    "sessions.col_flags": "Флаги",
    "sessions.badge_error": "ошибка",
    "sessions.badge_compaction": "компакция",
    "sessions.unnamed": "(без названия)",
    "sessions.has_notes": "есть заметка",

    "session.copy_full_log": "Скопировать полный лог",
    "session.download_md": "Скачать .md",
    "session.copied": "Скопировано в буфер обмена",
    "session.notes_label": "Заметка",
    "session.notes_placeholder": "Добавить заметку к сессии…",
    "session.notes_saved": "Заметка сохранена",
    "session.disconnected": "Нет живого соединения — показаны последние сохранённые данные",

    "summary.duration": "Длительность",
    "summary.unaccounted": "Не покрыто событиями",
    "summary.tools": "Инструменты",
    "summary.compactions": "Компакции",
    "summary.tokens": "Токены in/out/reasoning",
    "summary.cache": "Cache read/write",
    "summary.model": "Модель",
    "summary.project": "Проект",
    "summary.errors_suffix": "ошибок",

    "detections.title": "Что видно сразу",
    "detections.subtitle": "Детерминированные проверки на стороне вьювера (не анализ моделью) — см. описание каждой ⓘ",
    "detections.empty": "Детекторы ничего не нашли.",

    "messages_table.title": "Шаги модели",
    "messages_table.col_seq": "#",
    "messages_table.col_role": "Роль",
    "messages_table.col_total": "Всего",
    "messages_table.col_tool_time": "В инструментах",
    "messages_table.col_model_time": "У модели",
    "messages_table.col_input": "Input",
    "messages_table.col_output": "Output",
    "messages_table.col_cache_read": "Cache read",
    "messages_table.role_help": "Роль сообщения — как её сообщил сам OpenCode (user/assistant).",
    "messages_table.cache_help":
      "cache_read=0 означает, что провайдер модели не передал данные о кэше — это не обязательно значит, что кэш не работает (см. детектор no_prompt_cache).",

    "waterfall.title": "Waterfall",
    "waterfall.gap_label": "нет событий",
    "waterfall.legend_model": "у модели",
    "waterfall.legend_tool": "в инструментах",

    "tools.title": "Инструменты",
    "tools.col_tool": "Инструмент",
    "tools.col_calls": "Вызовов",
    "tools.col_errors": "Ошибок",
    "tools.col_total": "Всего",
    "tools.col_avg": "Среднее",
    "tools.col_tokens_est": "≈токенов вывода",
    "tools.filter_banner_prefix": "Показаны только шаги инструмента",
    "tools.filter_reset": "Сбросить фильтр",

    "context_attrib.title": "Чем заполнялся контекст",
    "context_attrib.empty": "Нет данных.",

    "context_growth.title": "Рост контекста",
    "context_growth.hint": "Кликните по шагу, чтобы увидеть разбивку контекста на этот момент",
    "context_growth.breakdown_title": "Чем занят контекст на шаге",
    "context_growth.cleared_label": "уже вычищено OpenCode",
    "context_growth.still_live_label": "оценочно ещё в контексте",

    "todo.title": "История плана",
    "todo.empty": "Агент не пользовался планированием шагов (todo-листом) в этой сессии. Здесь появятся все снимки плана по времени, когда агент их обновляет.",
    "todo.no_id": "без id",

    "feed.title": "Лента шагов",
    "feed.show_full": "Показать целиком",
    "feed.modal_copy": "Скопировать",
    "feed.modal_close": "Закрыть",
    "feed.input_label": "Вход:",
    "feed.output_label": "Выход:",
    "feed.error_label": "Ошибка:",
    "feed.step_label": "Шаг",
    "feed.finish_label": "финиш",
    "feed.open_subagent_session": "→ Открыть сессию разведчика",

    "settings.title": "Настройки",
    "settings.import_title": "Импорт уже существующих сессий",
    "settings.import_body":
      "Разовое действие: подтягивает историю сессий, которые агент накопил ещё до подключения плагина. Дальше новые сессии будут появляться сами — повторный запуск с теми же данными безопасен и не создаёт дублей (идемпотентно по event_id).",
    "settings.path_label": "Путь к хранилищу OpenCode (примонтирован в контейнер вьювера только на чтение)",
    "settings.source_name_label": "Имя источника (как будет называться агент в списке)",
    "settings.import_button": "Импортировать все существующие сессии",
    "settings.importing": "Импортирую…",
    "settings.layouts_note":
      "Поддерживаются обе раскладки хранилища OpenCode: набор JSON-файлов (storage/session|message|part|todo) и SQLite (opencode.db) — формат определяется автоматически.",
    "settings.language_title": "Язык интерфейса",
    "settings.result_accepted": "Принято событий",
    "settings.result_duplicates": "Дубликатов",
    "settings.result_rejected": "Отклонено",
    "settings.result_sessions": "Затронуто сессий",
    "unit.b": "Б",
    "unit.kb": "КБ",
    "unit.mb": "МБ",
    "unit.gb": "ГБ",
  },
  en: {
    "nav.sources": "Agents",
    "nav.settings": "Settings",
    "nav.logout": "Log out",
    "common.loading": "Loading…",
    "common.back": "← Back",

    "login.title": "OpenCode Trace Viewer",
    "login.subtitle": "This viewer stores excerpts from production agent logs. Access is password-protected.",
    "login.password_placeholder": "Password",
    "login.button": "Log in",
    "login.error": "Wrong password",

    "sources.title": "Agents",
    "sources.col_source": "Source",
    "sources.col_sessions": "Sessions",
    "sources.col_last_activity": "Last activity",
    "sources.col_status": "Status",
    "sources.active": "active",
    "sources.empty_title": "No agents yet",
    "sources.empty_body":
      "A source appears here automatically after its plugin's first event - nothing to set up by hand in this UI. Drop the plugin into the agent's .opencode/plugin/ and point it at this viewer:",
    "sources.empty_import_hint": "If the agent already has past session history, import it once from the Settings page.",
    "sources.rename_hint": "Click to give it a human-readable name",
    "sources.rename_placeholder": "Human-readable source name",
    "sources.time_now": "just now",
    "sources.time_min_ago": "min ago",
    "sources.time_hours_ago": "h ago",
    "sources.time_days_ago": "d ago",
    "sources.time_never": "—",

    "sessions.search_placeholder": "Search title and message content…",
    "sessions.only_errors": "Errors only",
    "sessions.empty": "No sessions from this source match the current filter.",
    "sessions.col_session": "Session",
    "sessions.col_start": "Started",
    "sessions.col_duration": "Duration",
    "sessions.col_model": "Model",
    "sessions.col_tokens": "Tokens in/out",
    "sessions.col_tools": "Tools",
    "sessions.col_flags": "Flags",
    "sessions.badge_error": "error",
    "sessions.badge_compaction": "compaction",
    "sessions.unnamed": "(untitled)",
    "sessions.has_notes": "has a note",

    "session.copy_full_log": "Copy full log",
    "session.download_md": "Download .md",
    "session.copied": "Copied to clipboard",
    "session.notes_label": "Note",
    "session.notes_placeholder": "Add a note to this session…",
    "session.notes_saved": "Note saved",
    "session.disconnected": "Live connection lost - showing the last saved data",

    "summary.duration": "Duration",
    "summary.unaccounted": "Not covered by events",
    "summary.tools": "Tool calls",
    "summary.compactions": "Compactions",
    "summary.tokens": "Tokens in/out/reasoning",
    "summary.cache": "Cache read/write",
    "summary.model": "Model",
    "summary.project": "Project",
    "summary.errors_suffix": "errors",

    "detections.title": "At a glance",
    "detections.subtitle": "Deterministic checks run by the viewer (not model-based analysis) - see each ⓘ for details",
    "detections.empty": "No detectors triggered.",

    "messages_table.title": "Model steps",
    "messages_table.col_seq": "#",
    "messages_table.col_role": "Role",
    "messages_table.col_total": "Total",
    "messages_table.col_tool_time": "In tools",
    "messages_table.col_model_time": "In model",
    "messages_table.col_input": "Input",
    "messages_table.col_output": "Output",
    "messages_table.col_cache_read": "Cache read",
    "messages_table.role_help": "The message role as reported by OpenCode itself (user/assistant).",
    "messages_table.cache_help":
      "cache_read=0 means the model provider didn't report cache stats at all - it doesn't necessarily mean caching isn't working (see the no_prompt_cache detector).",

    "waterfall.title": "Waterfall",
    "waterfall.gap_label": "no events",
    "waterfall.legend_model": "model",
    "waterfall.legend_tool": "tools",

    "tools.title": "Tools",
    "tools.col_tool": "Tool",
    "tools.col_calls": "Calls",
    "tools.col_errors": "Errors",
    "tools.col_total": "Total",
    "tools.col_avg": "Average",
    "tools.col_tokens_est": "≈output tokens",
    "tools.filter_banner_prefix": "Showing only steps for tool",
    "tools.filter_reset": "Clear filter",

    "context_attrib.title": "What filled up the context",
    "context_attrib.empty": "No data.",

    "context_growth.title": "Context growth",
    "context_growth.hint": "Click a step to see what made up the context at that point",
    "context_growth.breakdown_title": "What's occupying context at step",
    "context_growth.cleared_label": "already cleared by OpenCode",
    "context_growth.still_live_label": "estimated still in context",

    "todo.title": "Plan history",
    "todo.empty": "The agent didn't use step planning (a todo list) in this session. Every plan snapshot over time will show up here once it does.",
    "todo.no_id": "no id",

    "feed.title": "Step feed",
    "feed.show_full": "Show full value",
    "feed.modal_copy": "Copy",
    "feed.modal_close": "Close",
    "feed.input_label": "Input:",
    "feed.output_label": "Output:",
    "feed.error_label": "Error:",
    "feed.step_label": "Step",
    "feed.finish_label": "finished",
    "feed.open_subagent_session": "→ Open scout session",

    "settings.title": "Settings",
    "settings.import_title": "Import existing sessions",
    "settings.import_body":
      "A one-time action: pulls in session history the agent accumulated before the plugin was connected. New sessions arrive on their own after that - re-running this is safe and never creates duplicates (idempotent on event_id).",
    "settings.path_label": "Path to OpenCode's storage (mounted read-only into the viewer container)",
    "settings.source_name_label": "Source name (how the agent will be labeled in the list)",
    "settings.import_button": "Import all existing sessions",
    "settings.importing": "Importing…",
    "settings.layouts_note":
      "Both OpenCode storage layouts are supported: a tree of JSON files (storage/session|message|part|todo) and SQLite (opencode.db) - detected automatically.",
    "settings.language_title": "Interface language",
    "settings.result_accepted": "Events accepted",
    "settings.result_duplicates": "Duplicates",
    "settings.result_rejected": "Rejected",
    "settings.result_sessions": "Sessions touched",
    "unit.b": "B",
    "unit.kb": "KB",
    "unit.mb": "MB",
    "unit.gb": "GB",
  },
} as const

export type TranslationKey = keyof (typeof dict)["ru"]

interface LocaleContextValue {
  locale: Locale
  setLocale: (l: Locale) => void
  t: (key: TranslationKey) => string
}

const LocaleContext = createContext<LocaleContextValue | null>(null)

function readStoredLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored === "en" ? "en" : "ru"
  } catch {
    return "ru"
  }
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale)

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l)
    try {
      window.localStorage.setItem(STORAGE_KEY, l)
    } catch {
      // localStorage unavailable (private mode etc.) - locale just won't
      // survive a full page reload, navigation within the app is unaffected.
    }
  }, [])

  const t = useCallback((key: TranslationKey) => dict[locale][key] ?? dict.ru[key] ?? key, [locale])

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext)
  if (!ctx) throw new Error("useLocale() must be used inside <LocaleProvider>")
  return ctx
}
