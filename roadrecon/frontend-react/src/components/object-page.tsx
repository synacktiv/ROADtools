import { useSearchParams } from 'react-router'
import { IconExternalLink } from '@tabler/icons-react'
import { Card, CardContent } from '@/components/ui/card'
import { PropertyList, type Property } from '@/components/property-list'
import { JsonView } from '@/components/json-view'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { TYPE_LABEL, TypeGlyph } from '@/components/object-link'
import type { ObjectType } from '@/api/types'
import { ApiError } from '@/api/client'
import { fmtNumber } from '@/lib/format'
import { useSettings } from '@/lib/settings'

export interface TabDef {
  key: string
  label: string
  count?: number
  hidden?: boolean
  render: () => React.ReactNode
}

interface ObjectPageProps {
  /** Properties shown in the side panel, always visible next to the tabs. */
  summary?: Property[] | null | false
  /** Compact visual card shown above the properties (posture, exposure, breakdown). */
  aside?: React.ReactNode
  /** Raw dump object, shown in a final Raw tab as a JSON tree. */
  raw?: unknown
  type: ObjectType
  title?: string
  /** Kept for callers; identifiers are shown once, in the summary panel. */
  sub?: string | null
  id?: string
  badges?: React.ReactNode
  portalUrl?: string
  tabs: TabDef[]
  loading?: boolean
  error?: unknown
}

export { copy } from '@/lib/copy'

export function ObjectPage({ type, title, badges, portalUrl, tabs, loading, error, summary, aside, raw }: ObjectPageProps) {
  const [params, setParams] = useSearchParams()
  const { portalLinks } = useSettings()
  const rawTab: TabDef[] = raw !== undefined ? [{ key: 'raw', label: 'Raw', render: () => <JsonView value={raw} /> }] : []
  // While loading, hidden-ness is unknown: keep every tab so the requested one exists and stays reachable by keyboard.
  const visible = [...tabs, ...rawTab].filter((t) => loading || !t.hidden)
  const tab = visible.some((t) => t.key === params.get('tab')) ? params.get('tab')! : visible[0]?.key

  if (error)
    return (
      <Empty className="mt-16">
        <EmptyHeader>
          <EmptyTitle>{error instanceof ApiError && error.status === 404 ? `${TYPE_LABEL[type]} not found` : 'Could not load this object'}</EmptyTitle>
          <EmptyDescription>
            {error instanceof ApiError && error.status === 404
              ? 'No object with this ID exists in the dump. It may have been deleted before the dump was made.'
              : (error as Error).message}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="grid size-10 place-items-center rounded-lg border glass" title={TYPE_LABEL[type]}>
          <TypeGlyph type={type} className="size-5" />
        </span>
        <div className="flex min-w-0 flex-col">
          <span className="text-sm text-muted-foreground">{TYPE_LABEL[type]}</span>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            {loading ? <Skeleton className="h-7 w-72" /> : <h1 className="text-2xl leading-tight font-semibold tracking-tight">{title}</h1>}
            <div className="flex flex-wrap items-center gap-1.5">{badges}</div>
          </div>
        </div>
        {portalLinks && portalUrl && (
          <Button variant="outline" size="sm" asChild className="ml-auto bg-transparent">
            <a href={portalUrl} target="_blank" rel="noreferrer">
              Entra admin center <IconExternalLink />
            </a>
          </Button>
        )}
      </header>
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(20rem,24rem)_minmax(0,1fr)]">
        <aside className="flex flex-col gap-4 xl:sticky xl:top-20">
          {aside}
          <Card className="gap-0 py-2">
            <CardContent className="px-4">
              {loading || !summary ? <Skeleton className="my-2 h-64 w-full" /> : <PropertyList items={summary} layout="stacked" />}
            </CardContent>
          </Card>
        </aside>
        <Tabs value={tab} onValueChange={(t) => setParams({ tab: t }, { replace: true })} className="min-w-0 gap-4">
          <div className="overflow-x-auto">
            <TabsList className="h-10">
              {visible.map((t) => (
                <TabsTrigger key={t.key} value={t.key} className="flex-none px-3">
                  {t.label}
                  {t.count !== undefined && <span className="text-xs text-muted-foreground tabular-nums">{fmtNumber(t.count)}</span>}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {visible.map((t) => (
            <TabsContent key={t.key} value={t.key} className="min-w-0">
              {t.key === tab && t.render()}
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </div>
  )
}

/** A titled block inside a tab. */
export function Section({ title, count, children, aside }: { title: string; count?: number; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <h2 className="text-base font-semibold">{title}</h2>
        {count !== undefined && <span className="text-muted-foreground tabular-nums">{fmtNumber(count)}</span>}
        <div className="ml-auto">{aside}</div>
      </div>
      {children}
    </section>
  )
}
