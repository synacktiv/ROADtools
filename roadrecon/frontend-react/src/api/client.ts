import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { Route, Routes } from './types'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export interface ApiOptions<R extends Route> {
  path?: Record<string, string>
  query?: Routes[R]['query']
}

export function buildUrl(route: string, path: Record<string, string> = {}, query: object = {}) {
  const url = route.replace(/\{(\w+)\}/g, (_, k: string) => encodeURIComponent(path[k] ?? ''))
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, String(x)))
    else if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return s ? `${url}?${s}` : url
}

// The mock is only bundled in mock builds (VITE_MOCK=1).
const fetchImpl: typeof fetch = import.meta.env.VITE_MOCK === '1' ? (await import('./mock')).mockFetch : fetch.bind(window)

export async function get<R extends Route>(route: R, opts: ApiOptions<R> = {}): Promise<Routes[R]['res']> {
  const res = await fetchImpl(buildUrl(route, opts.path, opts.query ?? {}))
  if (!res.ok) throw new ApiError(res.status, (await res.text()) || res.statusText)
  return res.json()
}

export function useApi<R extends Route>(route: R, opts: ApiOptions<R> = {}, enabled = true) {
  return useQuery({
    queryKey: [route, opts.path, opts.query],
    queryFn: () => get(route, opts),
    placeholderData: keepPreviousData,
    enabled,
  })
}
