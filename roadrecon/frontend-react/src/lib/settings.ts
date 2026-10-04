import { useSyncExternalStore } from 'react'

export interface Settings {
  mfaColumns: boolean
  portalLinks: boolean
  blueTeam: boolean
  pageSize: number
}

const KEY = 'roadrecon.settings'
// No settings page: these are fixed defaults; the theme toggle, page size and Columns menu cover the rest.
const defaults: Settings = { mfaColumns: true, portalLinks: true, blueTeam: false, pageSize: 50 }
const listeners = new Set<() => void>()

let current: Settings = (() => {
  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return defaults
  }
})()

export function setSettings(patch: Partial<Settings>) {
  current = { ...current, ...patch }
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    // storage unavailable: settings last for this session only
  }
  listeners.forEach((l) => l())
}

export function useSettings(): Settings {
  return useSyncExternalStore(
    (l) => (listeners.add(l), () => listeners.delete(l)),
    () => current,
  )
}
