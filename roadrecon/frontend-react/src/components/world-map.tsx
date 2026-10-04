import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useQueries } from '@tanstack/react-query'
import { IconWorldQuestion } from '@tabler/icons-react'
// Country shapes keyed by ISO 3166-1 alpha-2 (lowercase). @svg-maps/world, CC BY 4.0.
import worldMap from '@svg-maps/world'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { get } from '@/api/client'
import type { NamedLocationDetail, NamedLocationRow, PolicyMatch } from '@/api/types'
import { plural } from '@/lib/format'
import { cn } from '@/lib/utils'

// The package types import svg-maps__common, which is not installed.
const world = worldMap as unknown as { viewBox: string; locations: { id: string; name: string; path: string }[] }
const NAMES = new Map(world.locations.map((l) => [l.id, l.name]))

export const countryName = (code: string) => NAMES.get(code.toLowerCase()) ?? code.toUpperCase()

/** block = regulatory, trusted = guide, neutral = foreground. */
export type MapTone = 'block' | 'trusted' | 'neutral'

const TONE: Record<MapTone, { fill: string; swatch: string }> = {
  block: { fill: 'fill-regulatory/80 hover:fill-regulatory', swatch: 'bg-regulatory' },
  trusted: { fill: 'fill-guide/80 hover:fill-guide', swatch: 'bg-guide' },
  neutral: { fill: 'fill-foreground/50 hover:fill-foreground/75', swatch: 'bg-muted-foreground' },
}
const RANK: Record<MapTone, number> = { neutral: 0, trusted: 1, block: 2 }

/** Shapes narrower than this (viewBox units, the map is 1010 wide) get a dot so they stay visible. */
const TINY = 8

const Swatch = ({ tone }: { tone: MapTone }) => <span className={cn('size-2.5 shrink-0 rounded-sm', TONE[tone].swatch)} aria-hidden />

interface WorldMapProps {
  /** Highlighted countries: ISO alpha-2 code (any case) to tone. */
  countries: Record<string, MapTone>
  /** Accessible name; the highlighted country names are appended. */
  label: string
  /** Extra tooltip lines for a highlighted country (receives the uppercase code). */
  describe?: (code: string) => ReactNode
  className?: string
}

/** Theme-aware world map. Hover shows the country name; tiny highlighted countries get a dot. */
export function WorldMap({ countries, label, describe, className }: WorldMapProps) {
  const tones = new Map(Object.entries(countries).map(([c, t]) => [c.toLowerCase(), t]))
  const svg = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null)
  const [dots, setDots] = useState<{ id: string; cx: number; cy: number }[]>([])

  const ids = [...tones.keys()].sort().join()
  useLayoutEffect(() => {
    const found: typeof dots = []
    for (const id of ids ? ids.split(',') : []) {
      const b = svg.current?.querySelector<SVGPathElement>(`path[data-id="${id}"]`)?.getBBox()
      if (b && Math.max(b.width, b.height) < TINY) found.push({ id, cx: b.x + b.width / 2, cy: b.y + b.height / 2 })
    }
    setDots(found)
  }, [ids])

  // One delegated handler; the tooltip is anchored where the pointer entered the country.
  const over = (e: React.PointerEvent<SVGSVGElement>) => {
    const id = (e.target as Element).getAttribute('data-id')
    if (id === (hover?.id ?? null)) return
    if (!id) return setHover(null)
    const r = e.currentTarget.getBoundingClientRect()
    setHover({ id, x: ((e.clientX - r.left) / r.width) * 100, y: ((e.clientY - r.top) / r.height) * 100 })
  }

  const highlighted = world.locations.filter((l) => tones.has(l.id))
  const tone = (id: string) => tones.get(id)!
  return (
    <figure className={cn('relative flex flex-col gap-1', className)}>
      <svg
        ref={svg}
        viewBox={world.viewBox}
        className="h-auto w-full"
        role="img"
        aria-label={highlighted.length ? `${label}: ${highlighted.map((l) => l.name).join(', ')}` : label}
        onPointerOver={over}
        onPointerLeave={() => setHover(null)}
      >
        <g className="fill-foreground/10 stroke-background [stroke-width:0.6] *:transition-[fill] *:duration-150 *:hover:fill-foreground/25 motion-reduce:*:transition-none">
          {world.locations.map((l) => !tones.has(l.id) && <path key={l.id} data-id={l.id} d={l.path} />)}
        </g>
        {/* Drawn last so their borders are not covered by neighbours. */}
        <g className="stroke-background [stroke-width:0.6]">
          {highlighted.map((l) => (
            <path key={l.id} data-id={l.id} d={l.path} className={cn('transition-[fill] duration-150 motion-reduce:transition-none', TONE[tone(l.id)].fill)} />
          ))}
          {dots.map((d) => (
            <circle key={d.id} data-id={d.id} cx={d.cx} cy={d.cy} r={7} className={cn('[stroke-width:1.5]', TONE[tone(d.id)].fill)} />
          ))}
        </g>
      </svg>
      <Tooltip open={hover !== null}>
        {/* Remounted per country so the tooltip moves with it. */}
        <TooltipTrigger asChild>
          <span key={hover?.id} className="pointer-events-none absolute size-px" style={{ left: `${hover?.x ?? 0}%`, top: `${hover?.y ?? 0}%` }} aria-hidden />
        </TooltipTrigger>
        {hover && (
          <TooltipContent side="top" sideOffset={8} className="pointer-events-none flex-col items-start gap-1">
            <span className="font-medium">
              {NAMES.get(hover.id)} <span className="font-mono opacity-60">{hover.id.toUpperCase()}</span>
            </span>
            {tones.has(hover.id) && describe?.(hover.id.toUpperCase())}
          </TooltipContent>
        )}
      </Tooltip>
      <figcaption className="self-end text-xs text-muted-foreground">Map data: @svg-maps/world, CC BY 4.0</figcaption>
    </figure>
  )
}

/** red if an enabled or report-only block policy includes the location, green if trusted. */
const locationTone = (trusted: boolean, policies: PolicyMatch[] = []): MapTone =>
  policies.some((m) => m.effect === 'included' && m.policy.block && m.policy.state !== 'disabled') ? 'block' : trusted ? 'trusted' : 'neutral'

const UnknownCountries = () => (
  <Tooltip>
    <TooltipTrigger asChild>
      <Badge variant="outline" tabIndex={0} className="cursor-help border-dashed text-muted-foreground">
        <IconWorldQuestion stroke={1.75} aria-hidden />
        Unknown countries
      </Badge>
    </TooltipTrigger>
    <TooltipContent>Also matches sign-ins whose country cannot be determined</TooltipContent>
  </Tooltip>
)

/** Country-kind named location on a map, with legend and country chips. Null for IP locations. */
export function NamedLocationMap({ location: l }: { location: NamedLocationDetail }) {
  if (l.kind === 'ip') return null
  const tone = locationTone(l.trusted, l.policyMatches)
  const blockers = l.policyMatches.filter((m) => m.effect === 'included' && m.policy.block && m.policy.state !== 'disabled').length
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Countries</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-x-2">
          <Swatch tone={tone} />
          <span className="text-foreground tabular-nums">{plural(l.countries.length, 'country', 'countries')}</span>
          {tone === 'block' && <span className="text-regulatory">blocked by {plural(blockers, 'policy', 'policies')}</span>}
          {tone === 'trusted' && <span className="text-guide">trusted</span>}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <WorldMap countries={Object.fromEntries(l.countries.map((c) => [c, tone]))} label={l.displayName} />
        <ul className="flex flex-wrap gap-1" aria-label="Countries">
          {l.countries.map((c) => (
            <li key={c}>
              <Badge variant="outline" className="gap-1.5">
                <span className="font-mono text-muted-foreground">{c}</span>
                {countryName(c)}
              </Badge>
            </li>
          ))}
          {l.includeUnknownCountries && (
            <li>
              <UnknownCountries />
            </li>
          )}
        </ul>
      </CardContent>
    </Card>
  )
}

/** Every country referenced by a country-kind named location; hover lists the locations that contain it. */
/** `size` caps the map width: md fits above a table without pushing it below the fold. */
export function NamedLocationsOverviewMap({ locations, size = 'lg' }: { locations: NamedLocationRow[]; size?: 'md' | 'lg' }) {
  const countryLocs = locations.filter((l) => l.kind === 'country')
  // The block tone needs each location's policies. Same query key as useApi, so this shares the table's per-row fetch.
  const details = useQueries({
    queries: countryLocs.map((l) => ({
      queryKey: ['/api/named-locations/{id}', { id: l.id }, undefined],
      queryFn: () => get('/api/named-locations/{id}', { path: { id: l.id } }),
      enabled: l.policyCount > 0,
    })),
  })
  if (!countryLocs.length) return null

  const byCountry = new Map<string, { l: NamedLocationRow; tone: MapTone }[]>()
  countryLocs.forEach((l, i) => {
    const tone = locationTone(l.trusted, details[i].data?.policyMatches)
    for (const c of l.countries) byCountry.set(c.toUpperCase(), [...(byCountry.get(c.toUpperCase()) ?? []), { l, tone }])
  })
  const countries = Object.fromEntries([...byCountry].map(([c, ls]) => [c, ls.reduce<MapTone>((t, x) => (RANK[x.tone] > RANK[t] ? x.tone : t), 'neutral')]))
  const present = (['block', 'trusted', 'neutral'] as const).filter((t) => Object.values(countries).includes(t))
  const LEGEND: Record<MapTone, string> = { block: 'blocked', trusted: 'trusted', neutral: 'other' }

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Countries in named locations</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="tabular-nums">
            <span className="text-foreground">{plural(byCountry.size, 'country', 'countries')}</span> in {plural(countryLocs.length, 'location')}
          </span>
          {present.map((t) => (
            <span key={t} className="inline-flex items-center gap-1.5">
              <Swatch tone={t} />
              {LEGEND[t]}
            </span>
          ))}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <WorldMap
          className={cn('mx-auto w-full', size === 'md' ? 'max-w-xl' : 'max-w-3xl')}
          countries={countries}
          label="Countries in named locations"
          describe={(c) => (
            <ul className="flex flex-col gap-0.5">
              {byCountry.get(c)!.map(({ l, tone }) => (
                <li key={l.id} className="flex items-center gap-1.5">
                  <Swatch tone={tone} />
                  {l.displayName}
                </li>
              ))}
            </ul>
          )}
        />
      </CardContent>
    </Card>
  )
}
