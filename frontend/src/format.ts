import type { TranslationKey } from "./i18n"

export function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "?"
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} с`
  const m = Math.floor(s / 60)
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`
}

export function fmtBytes(n: number, t: (k: TranslationKey) => string): string {
  if (n < 1024) return `${n} ${t("unit.b")}`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} ${t("unit.kb")}`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} ${t("unit.mb")}`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} ${t("unit.gb")}`
}
