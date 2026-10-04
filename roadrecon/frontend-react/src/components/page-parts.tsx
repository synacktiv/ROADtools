import { useSearchParams } from 'react-router'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import type { ObjectRef, ObjectType } from '@/api/types'
import { fmtNumber } from '@/lib/format'

export function ListPage({ title, description, children }: { title: string; description?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h1 className="text-[1.43rem] leading-tight font-semibold">{title}</h1>
        {description && <p className="max-w-[72ch] text-muted-foreground">{description}</p>}
      </div>
      {children}
    </div>
  )
}

export interface SubView {
  key: string
  label: string
  count?: number
  hidden?: boolean
  render: () => React.ReactNode
}

/** One table at a time inside a tab, selected by `view` in the URL. */
export function SubViews({ views }: { views: SubView[] }) {
  const [params, setParams] = useSearchParams()
  const visible = views.filter((v) => !v.hidden)
  const view = visible.find((v) => v.key === params.get('view')) ?? visible[0]
  if (!view) return null
  return (
    <div className="flex flex-col gap-3">
      {visible.length > 1 && (
        <ToggleGroup
          type="single"
          variant="outline"
          size="sm"
          value={view.key}
          onValueChange={(v) => v && setParams({ tab: params.get('tab') ?? '', view: v }, { replace: true })}
          className="w-fit"
        >
          {visible.map((v) => (
            <ToggleGroupItem key={v.key} value={v.key} className="gap-1.5 px-3">
              {v.label}
              {v.count !== undefined && <span className="text-muted-foreground tabular-nums">{fmtNumber(v.count)}</span>}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
      {view.render()}
    </div>
  )
}

export const Dash = () => <span className="text-muted-foreground/60" aria-label="Empty">·</span>

export function orDash(v: React.ReactNode) {
  return v === null || v === undefined || v === '' ? <Dash /> : v
}

export const toRef = (type: ObjectType, row: { id: string; displayName: string }, sub?: string | null): ObjectRef => ({
  id: row.id,
  type,
  displayName: row.displayName,
  sub,
})

export const yesNo = (v: boolean | null | undefined) => (v === null || v === undefined ? null : v ? 'Yes' : 'No')
