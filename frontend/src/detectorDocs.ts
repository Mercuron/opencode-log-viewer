import type { Locale } from "./i18n"

// Kept in sync by hand with viewer/detectors/*.py - see CLAUDE.md. These are
// UI-chrome explanations of what each deterministic detector checks, not
// server-generated content, so they're bilingual like the rest of the UI.
export const detectorDocs: Record<string, Record<Locale, string>> = {
  repeated_tool_call: {
    ru: "Один и тот же инструмент вызван ≥3 раз с эквивалентными аргументами (SQL нормализуется: регистр, комментарии, пробелы, литералы приводятся к общему виду перед сравнением).",
    en: "The same tool was called ≥3 times with equivalent arguments (SQL is normalized - case, comments, whitespace, and literals are collapsed before comparing).",
  },
  tool_loop_alternating: {
    ru: "Два разных вызова чередуются друг с другом ≥6 раз суммарно — похоже на цикл, из которого агент не может выйти.",
    en: "Two different calls alternate with each other ≥6 times total - looks like a loop the agent can't break out of.",
  },
  no_prompt_cache: {
    ru: "cache_read=0 на всех шагах модели при суммарном input больше 50 000 токенов. Может значить, что кэш промпта не работает, а может — что провайдер просто не сообщает эту метрику.",
    en: "cache_read=0 on every model step while total input exceeds 50,000 tokens. Could mean prompt caching isn't working, or simply that the provider doesn't report this metric at all.",
  },
  time_unaccounted: {
    ru: "Больше 50% времени сессии не попадает ни в один известный интервал (ни в сообщение, ни в часть с явным временем).",
    en: "More than 50% of the session's duration falls outside every known interval (neither a message nor a part with explicit timing covers it).",
  },
  slow_tool: {
    ru: "Отдельный вызов инструмента занял дольше 10 секунд.",
    en: "A single tool call took longer than 10 seconds.",
  },
  oversized_output: {
    ru: "Вывод одного инструмента оценивается больше чем в 20 000 токенов — крупный кандидат на переполнение контекста.",
    en: "A single tool's output is estimated at more than 20,000 tokens - a prime candidate for filling up the context window.",
  },
  todo_stagnation: {
    ru: "К концу сессии не закрыт ни один пункт плана (при их числе больше одного), либо у пунктов плана нет стабильного id.",
    en: "By the end of the session zero plan items were completed (with more than one item total), or plan items have no stable id.",
  },
  cyrillic_identifier: {
    ru: "Кириллические символы найдены внутри имени таблицы/базы в SQL — либо в квадратных скобках, либо сразу после FROM/JOIN/INTO/UPDATE.",
    en: "Cyrillic characters found inside a SQL table/database identifier - either in square brackets or right after FROM/JOIN/INTO/UPDATE.",
  },
  tool_error: {
    ru: "Вызов инструмента завершился статусом error/failed.",
    en: "A tool call finished with status error/failed.",
  },
  tool_soft_failure: {
    ru: "Инструмент вернул success=false в теле ответа (JSON), хотя сам вызов не помечен ошибкой — статус OpenCode не видит такие сбои, это отдельная проверка.",
    en: "The tool's own JSON body says success=false even though the call itself isn't marked as an error — OpenCode's status can't see this kind of failure, so it's checked separately.",
  },
  context_near_limit: {
    ru: "tokens_input у одного из сообщений превышает 80% известного контекстного окна модели.",
    en: "tokens_input on one of the messages exceeds 80% of the model's known context window.",
  },
}

export function detectorDoc(kind: string, locale: Locale): string | null {
  return detectorDocs[kind]?.[locale] ?? null
}
