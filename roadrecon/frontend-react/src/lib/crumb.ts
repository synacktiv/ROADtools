import { useEffect, useSyncExternalStore } from 'react'

// The object page tells the header which object is shown.
let crumb: string | null = null
const listeners = new Set<() => void>()
const emit = (v: string | null) => ((crumb = v), listeners.forEach((l) => l()))

export function useSetCrumb(name: string | undefined) {
  useEffect(() => {
    emit(name ?? null)
    if (name) document.title = `${name} — ROADrecon`
    return () => emit(null)
  }, [name])
}

export const useCrumb = () =>
  useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => crumb,
  )
