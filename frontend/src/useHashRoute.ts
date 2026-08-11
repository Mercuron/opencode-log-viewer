import { useEffect, useState } from "react"

export function useHashRoute(): [string, (to: string) => void] {
  const [hash, setHash] = useState(() => window.location.hash.slice(1) || "/sources")

  useEffect(() => {
    const onChange = () => setHash(window.location.hash.slice(1) || "/sources")
    window.addEventListener("hashchange", onChange)
    return () => window.removeEventListener("hashchange", onChange)
  }, [])

  const navigate = (to: string) => {
    window.location.hash = to
  }

  return [hash, navigate]
}
