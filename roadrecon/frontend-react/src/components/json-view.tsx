import { useState } from 'react'
import { IconChevronRight, IconCopy, IconFoldDown, IconFoldUp } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { copy } from '@/lib/copy'
import { cn } from '@/lib/utils'

// Syntax colours for JSON only; the rest of the UI keeps colour for meaning.
const TONE = {
  key: 'text-sky-700 dark:text-sky-300',
  string: 'text-emerald-700 dark:text-emerald-300',
  number: 'text-amber-700 dark:text-amber-300',
  boolean: 'text-violet-700 dark:text-violet-300',
  null: 'text-muted-foreground italic',
}

/**
 * Collapsible, syntax-coloured JSON tree. Strings that themselves contain JSON
 * (common in roadrecon.db, e.g. policyDetail) are expanded as nested values.
 */
export function JsonView({ value, depth: openDepth = 2 }: { value: unknown; depth?: number }) {
  // Bumping `gen` remounts the tree with every node open or closed.
  const [state, setState] = useState({ gen: 0, open: openDepth })
  const text = JSON.stringify(value, null, 2)
  return (
    <div className="glass overflow-hidden rounded-xl border">
      <div className="flex items-center gap-1 border-b px-2 py-1.5">
        <Button variant="ghost" size="sm" onClick={() => setState((s) => ({ gen: s.gen + 1, open: 99 }))}>
          <IconFoldDown /> Expand all
        </Button>
        <Button variant="ghost" size="sm" onClick={() => setState((s) => ({ gen: s.gen + 1, open: 1 }))}>
          <IconFoldUp /> Collapse all
        </Button>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => copy(text, 'JSON')}>
          <IconCopy /> Copy
        </Button>
      </div>
      <div className="overflow-x-auto p-3 font-mono text-[0.85rem] leading-6">
        <Node key={state.gen} value={value} depth={0} openDepth={state.open} last />
      </div>
    </div>
  )
}

function parseNested(v: unknown): unknown {
  if (typeof v !== 'string' || v.length < 2 || !'[{'.includes(v[0])) return v
  try {
    return JSON.parse(v)
  } catch {
    return v
  }
}

function Scalar({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <span className={TONE.null}>null</span>
  if (typeof v === 'string') return <span className={cn(TONE.string, 'break-all')}>"{v}"</span>
  if (typeof v === 'number') return <span className={TONE.number}>{v}</span>
  if (typeof v === 'boolean') return <span className={TONE.boolean}>{String(v)}</span>
  return <span>{String(v)}</span>
}

function Node({ name, value: raw, depth, openDepth, last }: { name?: string; value: unknown; depth: number; openDepth: number; last?: boolean }) {
  const value = parseNested(raw)
  const nested = value !== raw
  const isObj = value !== null && typeof value === 'object'
  const [open, setOpen] = useState(depth < openDepth)
  const comma = last ? '' : ','
  const label = name !== undefined && (
    <>
      <span className={TONE.key}>"{name}"</span>
      <span className="text-muted-foreground">: </span>
    </>
  )
  if (!isObj)
    return (
      <div className="pl-5">
        {label}
        <Scalar v={value} />
        <span className="text-muted-foreground">{comma}</span>
      </div>
    )
  const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v] as const) : Object.entries(value as object)
  const [o, c] = Array.isArray(value) ? ['[', ']'] : ['{', '}']
  if (entries.length === 0)
    return (
      <div className="pl-5">
        {label}
        <span className="text-muted-foreground">
          {o}
          {c}
          {comma}
        </span>
      </div>
    )
  return (
    <div>
      <button type="button" onClick={() => setOpen(!open)} className="group inline-flex items-center rounded-sm text-left hover:bg-accent" aria-expanded={open}>
        <IconChevronRight className={cn('size-4 text-muted-foreground transition-transform', open && 'rotate-90')} />
        {label}
        <span className="text-muted-foreground">{o}</span>
        {!open && (
          <span className="px-1 text-xs text-muted-foreground">
            {entries.length} {Array.isArray(value) ? 'items' : 'keys'}
            {nested && ', from string'}
          </span>
        )}
        {!open && (
          <span className="text-muted-foreground">
            {c}
            {comma}
          </span>
        )}
      </button>
      {open && (
        <>
          <div className="ml-2 border-l border-border/60 pl-2">
            {entries.map(([k, v], i) => (
              <Node key={k} name={Array.isArray(value) ? undefined : k} value={v} depth={depth + 1} openDepth={openDepth} last={i === entries.length - 1} />
            ))}
          </div>
          <div className="pl-5 text-muted-foreground">
            {c}
            {comma}
          </div>
        </>
      )}
    </div>
  )
}
