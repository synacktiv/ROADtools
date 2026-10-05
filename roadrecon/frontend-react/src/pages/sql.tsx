import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import type { ColumnDef } from '@tanstack/react-table'
import { IconAlertTriangle, IconBookmarks, IconPlayerPlay } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Spinner } from '@/components/ui/spinner'
import { Textarea } from '@/components/ui/textarea'
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover'
import { Command, CommandItem, CommandList } from '@/components/ui/command'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { DataTable } from '@/components/data-table'
import { ListPage, orDash } from '@/components/page-parts'
import { post, useApi } from '@/api/client'
import type { SqlResult, SqlSchema } from '@/api/types'
import { fmtNumber } from '@/lib/format'

type Row = Record<string, unknown>
type Table = SqlSchema['tables'][number]
interface Suggestions {
  start: number
  end: number
  items: string[]
}

const DEFAULT_SQL = 'SELECT displayName, userPrincipalName, userType, accountEnabled\nFROM Users\nLIMIT 100'
const NEEDS_QUOTES = /^(group|order|default|index|key|table|check|references)$/i

/** Tables and columns completing the word before the caret. `alias.` or `Table.` completes that table's columns. */
function suggest(sql: string, caret: number, tables: Table[]): Suggestions | null {
  const [, qualifier, prefix] = /(?:(\w+)\.)?(\w*)$/.exec(sql.slice(0, caret))!
  if (!qualifier && prefix.length < 2) return null
  const byName = new Map(tables.map((t) => [t.name.toLowerCase(), t]))
  const refs = [...sql.matchAll(/\b(?:from|join)\s+"?(\w+)"?(?:\s+(?:as\s+)?(\w+))?/gi)]
  let names: string[]
  if (qualifier) {
    const q = qualifier.toLowerCase()
    const t = byName.get(refs.find((r) => r[2]?.toLowerCase() === q)?.[1].toLowerCase() ?? q)
    if (!t) return null
    names = t.columns
  } else {
    const used = refs.map((r) => byName.get(r[1].toLowerCase())).filter((t): t is Table => !!t)
    names = [...tables.map((t) => t.name), ...(used.length ? used : tables).flatMap((t) => t.columns)]
  }
  const p = prefix.toLowerCase()
  const items = [...new Set(names)].filter((n) => n.toLowerCase().startsWith(p) && n.toLowerCase() !== p).slice(0, 50)
  return items.length ? { start: caret - prefix.length, end: caret, items } : null
}

/** Caret position in the textarea (monospace, no wrapping), relative to its top-left corner. */
function caretXY(el: HTMLTextAreaElement, pos: number) {
  const cs = getComputedStyle(el)
  const lines = el.value.slice(0, pos).split('\n')
  const ctx = document.createElement('canvas').getContext('2d')!
  ctx.font = cs.font
  const x = parseFloat(cs.paddingLeft) + ctx.measureText(lines[lines.length - 1]).width - el.scrollLeft
  const y = parseFloat(cs.paddingTop) + lines.length * parseFloat(cs.lineHeight) - el.scrollTop
  return { x: Math.min(x, el.clientWidth), y: Math.min(y, el.clientHeight) }
}

function SqlEditor({ value, onChange, onRun, tables }: { value: string; onChange: (v: string) => void; onRun: () => void; tables: Table[] }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [sug, setSug] = useState<Suggestions | null>(null)
  const [active, setActive] = useState('')
  const [xy, setXy] = useState({ x: 0, y: 0 })

  useEffect(() => {
    listRef.current?.querySelector('[data-selected=true]')?.scrollIntoView({ block: 'nearest' })
  }, [active])

  const update = (el: HTMLTextAreaElement) => {
    const s = suggest(el.value, el.selectionStart, tables)
    setSug(s)
    if (s) {
      setActive(s.items[0])
      setXy(caretXY(el, el.selectionStart))
    }
  }

  const accept = (name: string) => {
    if (!sug) return
    const quoted = value[sug.start - 1] === '"'
    const ident = quoted ? `${name}"` : /^[A-Za-z_]\w*$/.test(name) && !NEEDS_QUOTES.test(name) ? name : `"${name}"`
    onChange(value.slice(0, sug.start) + ident + value.slice(sug.end))
    setSug(null)
    const pos = sug.start + ident.length
    requestAnimationFrame(() => ref.current?.setSelectionRange(pos, pos))
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault()
      setSug(null)
      onRun()
    } else if (sug && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      const n = sug.items.length
      setActive(sug.items[(sug.items.indexOf(active) + (e.key === 'ArrowDown' ? 1 : -1) + n) % n])
    } else if (sug && (e.key === 'Enter' || e.key === 'Tab')) {
      e.preventDefault()
      accept(active || sug.items[0])
    } else if (sug && e.key === 'Escape') {
      e.preventDefault()
      setSug(null)
    }
  }

  return (
    <Popover open={!!sug} onOpenChange={(o) => !o && setSug(null)}>
      <div className="relative">
        <Textarea
          ref={ref}
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            update(e.target)
          }}
          onKeyDown={onKeyDown}
          onClick={() => setSug(null)}
          onBlur={() => setSug(null)}
          wrap="off"
          spellCheck={false}
          aria-label="SQL query"
          className="max-h-[50vh] min-h-40 resize-y bg-transparent! font-mono text-sm! leading-6"
        />
        {/* Re-keyed so the popover re-measures its anchor when the caret moves. */}
        <PopoverAnchor asChild key={`${xy.x},${xy.y}`}>
          <span className="pointer-events-none absolute" style={{ left: xy.x, top: xy.y }} />
        </PopoverAnchor>
      </div>
      <PopoverContent align="start" className="w-72 p-0" onOpenAutoFocus={(e) => e.preventDefault()} onMouseDown={(e) => e.preventDefault()}>
        <Command shouldFilter={false} value={active} onValueChange={setActive}>
          <CommandList ref={listRef} className="max-h-64">
            {sug?.items.map((name) => (
              <CommandItem key={name} value={name} onSelect={() => accept(name)} className="font-mono text-sm">
                {name}
                {tables.some((t) => t.name === name) && <span className="ml-auto font-sans text-xs text-muted-foreground">table</span>}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

export function SqlPage() {
  const [params, setParams] = useSearchParams()
  const sql = params.get('sql') ?? ''
  const [text, setText] = useState(sql || DEFAULT_SQL)
  useEffect(() => {
    if (sql) setText(sql)
  }, [sql])
  const { data: schema } = useApi('/api/sql/schema')
  const { data, error, isFetching } = useQuery({
    queryKey: ['/api/sql', sql],
    queryFn: () => post<SqlResult>('/api/sql', { sql }),
    enabled: !!sql.trim(),
    retry: false,
  })
  const run = (q = text) => q.trim() && setParams({ sql: q })

  // Duplicate column names (SELECT * over a join) get a suffix so every column keeps its own key.
  const { columns, rows } = useMemo(() => {
    if (!data) return { columns: [], rows: [] }
    const keys = data.columns.map((c, i) => (data.columns.indexOf(c) === i ? c : `${c} (${i + 1})`))
    return {
      columns: keys.map(
        (k, i): ColumnDef<Row> => ({
          id: k,
          header: data.columns[i],
          accessorFn: (r) => r[k],
          cell: ({ getValue }) => orDash(getValue() === null ? null : String(getValue())),
        }),
      ),
      rows: data.rows.map((r) => Object.fromEntries(keys.map((k, i) => [k, r[i]]))),
    }
  }, [data])

  return (
    <ListPage
      title="SQL query"
      description="Read-only SQL against the dump (SQLite). Results stop at 1,000 rows and 10 seconds. Tab or Enter completes table and column names."
    >
      <div className="glass flex flex-col gap-3 rounded-xl border p-3">
        <SqlEditor value={text} onChange={setText} onRun={() => run()} tables={schema?.tables ?? []} />
        <div className="flex flex-wrap items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="bg-transparent">
                <IconBookmarks /> Built-in queries
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-96">
              {schema?.queries.map((q) => (
                <DropdownMenuItem
                  key={q.name}
                  className="flex-col items-start gap-0.5"
                  onSelect={() => {
                    setText(q.sql)
                    run(q.sql)
                  }}
                >
                  <span className="font-medium">{q.name}</span>
                  <span className="text-xs text-muted-foreground">{q.description}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          {data && sql && !isFetching && (
            <span className="text-sm text-muted-foreground tabular-nums">
              {fmtNumber(data.rows.length)} rows in {fmtNumber(data.elapsedMs)} ms
            </span>
          )}
          <Button size="sm" className="ml-auto" onClick={() => run()} disabled={!text.trim()}>
            {isFetching ? <Spinner /> : <IconPlayerPlay />} Run <Kbd className="bg-primary-foreground/15! text-primary-foreground!">Ctrl Enter</Kbd>
          </Button>
        </div>
      </div>
      {error && (
        <div role="alert" className="glass rounded-xl border border-regulatory/40 px-4 py-3 font-mono text-sm whitespace-pre-wrap text-regulatory">
          {error.message}
        </div>
      )}
      {data?.truncated && (
        <p className="flex items-center gap-2 text-warning">
          <IconAlertTriangle className="size-4" stroke={1.75} /> Only the first {fmtNumber(data.rows.length)} rows are shown. Add a LIMIT or narrow the query.
        </p>
      )}
      {data && !error && <DataTable key={sql} route="/api/sql" rows={rows} columns={columns} hideSearch noun="row" />}
    </ListPage>
  )
}
