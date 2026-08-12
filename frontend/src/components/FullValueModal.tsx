import { useEffect } from "react"
import { useLocale } from "../i18n"

export default function FullValueModal({ title, value, onClose }: { title: string; value: string; onClose: () => void }) {
  const { t } = useLocale()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <strong>{title}</strong>
          <div className="modal-actions">
            <button onClick={() => navigator.clipboard.writeText(value)}>{t("feed.modal_copy")}</button>
            <button onClick={onClose}>{t("feed.modal_close")}</button>
          </div>
        </div>
        <pre className="modal-body">{value}</pre>
      </div>
    </div>
  )
}
