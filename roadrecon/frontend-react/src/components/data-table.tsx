import { Fragment, useEffect, useState } from 'react'
import { flushSync } from 'react-dom'
import { useSearchParams } from 'react-router'
import { flexRender, getCoreRowModel, useReactTable, type Column, type ColumnDef, type ColumnSizingState, type Header, type VisibilityState } from '@tanstack/react-table'
import {
  IconArrowDown,
  IconArrowUp,
  IconChevronLeft,
  IconChevronRight,
  IconColumns3,
  IconCopy,
  IconDotsVertical,
  IconDownload,
  IconEyeOff,
  IconFilterFilled,
  IconSearch,
} from '@tabler/icons-react'
import { toast } from 'sonner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'
import { ButtonGroup } from '@/components/ui/button-group'
import { Spinner } from '@/components/ui/spinner'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { get, useApi, type ApiOptions } from '@/api/client'
import type { FilterField, FilterResource, Page, Route, Routes } from '@/api/types'
import {
  FilterBuilder,
  OPS,
  ValueEditor,
  isComplete,
  newFilter,
  noValue,
  opLabel,
  parseFilter,
  serializeFilter,
  type ActiveFilter,
} from '@/components/filter-builder'
import { useSettings } from '@/lib/settings'
import { fmtNumber } from '@/lib/format'
import { copy } from '@/lib/copy'
import { cn } from '@/lib/utils'

declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    /** API sort key; the column is sortable when set. */
    sort?: string
    /** Filter field key (from /api/filters/{resource}); enables search / value picking in the header. */
    filter?: string
    /** Not shown until the user adds it from the Columns menu. */
    defaultHidden?: boolean
    /** No copy button on hover (cells with only icons or buttons). */
    noCopy?: boolean
    className?: string
  }
}

/** A relation switch shown in the toolbar, e.g. "include nested groups". Field filters use the filter builder. */
export type FilterDef = { kind: 'toggle'; key: string; label: string }

/** Table state lives in the URL so every view can be linked and survives Back. */
export function useTableParams() {
  const [params, setParams] = useSearchParams()
  const set = (patch: Record<string, string | string[] | null | undefined>) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [k, v] of Object.entries(patch)) {
          next.delete(k)
          if (Array.isArray(v)) v.forEach((x) => next.append(k, x))
          else if (v !== null && v !== undefined && v !== '') next.set(k, v)
        }
        if (!('page' in patch)) next.delete('page')
        return next
      },
      { replace: true },
    )
  return { params, set }
}

interface DataTableProps<R extends Route, T> {
  route: R
  path?: Record<string, string>
  /** Fixed filters, e.g. the relation of a tab: { memberOf: groupId }. */
  query?: Partial<Routes[R]['query']>
  columns: ColumnDef<T, any>[] // eslint-disable-line @typescript-eslint/no-explicit-any
  filters?: FilterDef[]
  searchPlaceholder?: string
  /** Noun for the count and the empty state, e.g. "member". */
  noun?: string
  defaultSort?: { sort: string; order: 'asc' | 'desc' }
  hideSearch?: boolean
  /** Enables the advanced filter builder with this resource's fields. */
  resource?: FilterResource
  /** Makes rows expandable; renders under the row across all columns. */
  renderExpanded?: (row: T) => React.ReactNode
}

const colKey = (c: ColumnDef<unknown>) => c.id ?? (c as { accessorKey?: string }).accessorKey ?? ''

function loadVisibility(key: string, columns: ColumnDef<unknown>[]): VisibilityState {
  const defaults = Object.fromEntries(columns.filter((c) => c.meta?.defaultHidden).map((c) => [colKey(c), false]))
  try {
    return { ...defaults, ...JSON.parse((key && localStorage.getItem(key)) || '{}') }
  } catch {
    return defaults
  }
}

export function DataTable<R extends Route, T>({
  route,
  path,
  query,
  columns,
  filters = [],
  searchPlaceholder = 'Search',
  noun = 'result',
  defaultSort,
  hideSearch,
  resource,
  renderExpanded,
}: DataTableProps<R, T>) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const settings = useSettings()
  const { params, set } = useTableParams()
  const page = Number(params.get('page') ?? 1)
  const pageSize = Number(params.get('page_size') ?? settings.pageSize)
  const sort = params.get('sort') ?? defaultSort?.sort
  const order = (params.get('order') as 'asc' | 'desc' | null) ?? defaultSort?.order
  const q = params.get('q') ?? ''

  const toggles = Object.fromEntries(filters.map((f) => [f.key, params.get(f.key) ?? undefined]))
  const { data: fields } = useApi('/api/filters/{resource}', { path: { resource: resource ?? '' } }, !!resource)
  const active = params.getAll('filter').map(parseFilter).filter((f): f is ActiveFilter => !!f)
  const match = params.get('match') === 'any' ? 'any' : 'all'
  const sent = active.filter(isComplete).map(serializeFilter)
  const baseQuery = { ...query, ...toggles, q: q || undefined, sort, order, filter: sent, match: sent.length > 1 ? match : undefined }
  const { data, isLoading, isFetching, error, refetch } = useApi(route, { path, query: { ...baseQuery, page, page_size: pageSize } } as ApiOptions<R>)
  const pageData = data as Page<T> | undefined
  const setFilters = (fs: ActiveFilter[], m = match) => set({ filter: fs.map(serializeFilter), match: fs.length > 1 && m === 'any' ? 'any' : null })

  // Column visibility per list, remembered in this browser.
  // Keyed by route and column set, so two views of the same route (users / MFA) keep separate choices.
  const visKey = `roadrecon.columns:${route}:${(columns as ColumnDef<unknown>[]).map(colKey).join(',')}`
  const [visibility, setVisibility] = useState<VisibilityState>(() => loadVisibility(visKey, columns as ColumnDef<unknown>[]))
  useEffect(() => {
    try {
      localStorage.setItem(visKey, JSON.stringify(visibility))
    } catch {
      // storage unavailable: visibility lasts for this page only
    }
  }, [visKey, visibility])

  // Column widths per list, same key pattern. Columns never resized keep the automatic table layout.
  const sizeKey = visKey.replace('roadrecon.columns:', 'roadrecon.widths:')
  const [sizing, setSizing] = useState<ColumnSizingState>(() => {
    try {
      return JSON.parse(localStorage.getItem(sizeKey) || '{}')
    } catch {
      return {}
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem(sizeKey, JSON.stringify(sizing))
    } catch {
      // storage unavailable: widths last for this page only
    }
  }, [sizeKey, sizing])
  const width = (c: Column<T>) => (sizing[c.id] ? { width: c.getSize(), minWidth: c.getSize(), maxWidth: c.getSize() } : undefined)
  const startResize = (h: Header<T, unknown>) => (e: React.MouseEvent | React.TouchEvent) => {
    // TanStack starts the drag from column.getSize(); seed it with the rendered width so the edge does not jump.
    const w = (e.currentTarget.parentElement as HTMLElement).offsetWidth
    if (!sizing[h.column.id]) flushSync(() => setSizing((s) => ({ ...s, [h.column.id]: w })))
    h.getResizeHandler()(e)
  }

  const table = useReactTable({
    data: pageData?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    state: { columnVisibility: visibility, columnSizing: sizing },
    onColumnVisibilityChange: setVisibility,
    onColumnSizingChange: setSizing,
    enableColumnResizing: true,
    columnResizeMode: 'onChange',
    defaultColumn: { minSize: 60 },
  })

  const total = pageData?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1
  const last = Math.min(total, page * pageSize)
  const hasFilters = !!q || sent.length > 0 || filters.some((f) => params.get(f.key))

  const setSort = (key: string | null, o: 'asc' | 'desc' | null) => set({ sort: key, order: o })
  const cycleSort = (key: string) => {
    if (sort !== key) setSort(key, 'asc')
    else if (order === 'asc') setSort(key, 'desc')
    else setSort(null, null)
  }

  const exportRows = async (format: 'csv' | 'json', all: boolean) => {
    let rows = (pageData?.items ?? []) as unknown[]
    if (all) {
      rows = []
      // ponytail: client-side paging, capped at 50 000 rows; add a streaming export route if dumps need more
      for (let p = 1; p <= Math.min(100, Math.ceil(total / 500)); p++) {
        const res = (await get(route, { path, query: { ...baseQuery, page: p, page_size: 500 } } as ApiOptions<R>)) as Page<unknown>
        rows.push(...res.items)
      }
    }
    const name = `${route.replace('/api/', '').replace(/[^\w-]+/g, '-')}-${new Date().toISOString().slice(0, 10)}.${format}`
    download(name, format === 'json' ? JSON.stringify(rows, null, 2) : toCsv(rows), format === 'json' ? 'application/json' : 'text/csv')
    toast(`Exported ${fmtNumber(rows.length)} rows to ${name}`)
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {!hideSearch && <SearchBox value={q} placeholder={searchPlaceholder} onChange={(v) => set({ q: v })} />}
        {filters.map((f) => (
          <div key={f.key} className="flex items-center gap-2 px-1">
            <Switch id={`f-${f.key}`} checked={params.get(f.key) === 'true'} onCheckedChange={(c) => set({ [f.key]: c ? 'true' : null })} />
            <Label htmlFor={`f-${f.key}`} className="font-normal">
              {f.label}
            </Label>
          </div>
        ))}
        {resource && fields && <FilterBuilder fields={fields} filters={active} match={match} onChange={setFilters} />}
        <div className="ml-auto flex items-center gap-2 text-muted-foreground">
          {isFetching && <Spinner className="size-4" />}
          <span aria-live="polite" className="mr-1 tabular-nums">
            {total === 0 ? `No ${noun}s` : `${fmtNumber(first)} to ${fmtNumber(last)} of ${fmtNumber(total)}`}
          </span>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-8 bg-transparent" disabled={total === 0}>
                <IconDownload /> Export
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => exportRows('csv', false)}>CSV, this page</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportRows('csv', true)}>CSV, all {fmtNumber(total)} rows</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => exportRows('json', false)}>JSON, this page</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportRows('json', true)}>JSON, all {fmtNumber(total)} rows</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <ColumnMenu table={table} onReset={() => {
              setVisibility(loadVisibility('', columns as ColumnDef<unknown>[]))
              setSizing({})
            }}
          />
        </div>
      </div>

      <div className="glass overflow-x-auto rounded-xl border">
        <Table>
          <TableHeader className="bg-shoulder">
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id} className="hover:bg-transparent">
                {renderExpanded && <TableHead className="w-10 px-2" aria-label="Expand" />}
                {hg.headers.map((h) => (
                  <TableHead
                    key={h.id}
                    style={width(h.column)}
                    className={cn('group/head relative h-10 px-3 font-medium text-ink', sizing[h.column.id] && 'overflow-hidden', h.column.columnDef.meta?.className)}
                  >
                    <HeaderCell
                      header={h}
                      sort={sort}
                      order={order}
                      onCycleSort={cycleSort}
                      onSort={setSort}
                      field={fields?.find((f) => f.key === h.column.columnDef.meta?.filter)}
                      filters={active}
                      onFilters={setFilters}
                    />
                    {h.column.getCanResize() && (
                      <div
                        role="separator"
                        aria-orientation="vertical"
                        aria-label="Resize column"
                        title="Drag to resize, double-click to reset"
                        onMouseDown={startResize(h)}
                        onTouchStart={startResize(h)}
                        onDoubleClick={() => h.column.resetSize()}
                        className={cn(
                          'absolute inset-y-0 right-0 z-10 w-2 cursor-col-resize touch-none select-none',
                          'after:absolute after:inset-y-2 after:right-0 after:w-px after:bg-foreground/15 after:opacity-0 after:transition-opacity group-hover/head:after:opacity-100 hover:after:bg-foreground/40',
                          h.column.getIsResizing() && 'after:bg-foreground/40 after:opacity-100',
                        )}
                      />
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody className={cn(isFetching && !isLoading && 'opacity-60 transition-opacity')}>
            {isLoading &&
              Array.from({ length: 8 }, (_, i) => (
                <TableRow key={i}>
                  {renderExpanded && <TableCell className="w-10" />}
                  {table.getVisibleLeafColumns().map((c) => (
                    <TableCell key={c.id} style={width(c)} className="px-3">
                      <Skeleton className="h-4 w-3/4" />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            {table.getRowModel().rows.map((row) => (
              <Fragment key={row.id}>
              <TableRow data-state={expanded.has(row.id) ? 'selected' : undefined}>
                {renderExpanded && (
                  <TableCell className="w-10 px-2">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={expanded.has(row.id) ? 'Collapse' : 'Expand'}
                      aria-expanded={expanded.has(row.id)}
                      onClick={() => setExpanded((s) => { const n = new Set(s); if (n.has(row.id)) n.delete(row.id); else n.add(row.id); return n })}
                    >
                      <IconChevronRight className={cn('transition-transform', expanded.has(row.id) && 'rotate-90')} />
                    </Button>
                  </TableCell>
                )}
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    style={width(cell.column)}
                    className={cn('group/cell h-10 max-w-96 px-3 py-1.5', sizing[cell.column.id] && 'overflow-hidden', cell.column.columnDef.meta?.className)}
                  >
                    {cell.column.columnDef.meta?.noCopy ? (
                      flexRender(cell.column.columnDef.cell, cell.getContext())
                    ) : (
                      <div className="relative min-w-0">
                        <div data-cell className={cn('min-w-0', cell.column.columnDef.meta?.className?.includes('whitespace-normal') ? 'break-words' : 'truncate')}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </div>
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          className="absolute top-1/2 right-0 -translate-y-1/2 bg-background/90 text-muted-foreground opacity-0 shadow-sm backdrop-blur group-hover/cell:opacity-100 focus-visible:opacity-100"
                          aria-label="Copy value"
                          onClick={(e) => {
                            // Prefer the object name over badge words when the cell holds an ObjectLink.
                            const cellEl = e.currentTarget.parentElement?.querySelector('[data-cell]')
                            const named = cellEl?.querySelectorAll('[data-copy]')
                            const text = (named?.length === 1 ? named[0] : cellEl)?.textContent?.trim()
                            if (text) copy(text, 'Value')
                          }}
                        >
                          <IconCopy />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                ))}
              </TableRow>
              {renderExpanded && expanded.has(row.id) && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={row.getVisibleCells().length + 1} className="bg-shoulder/60 px-6 py-5 whitespace-normal">
                    {renderExpanded(row.original)}
                  </TableCell>
                </TableRow>
              )}
              </Fragment>
            ))}
          </TableBody>
        </Table>
        {!isLoading && total === 0 && (
          <Empty className="py-10">
            <EmptyHeader>
              <EmptyTitle>{error ? 'Could not load this list' : hasFilters ? `No ${noun}s match` : `No ${noun}s`}</EmptyTitle>
              <EmptyDescription>
                {error ? (
                  <>
                    {(error as Error).message}{' '}
                    <Button variant="link" className="h-auto p-0" onClick={() => refetch()}>
                      Retry
                    </Button>
                  </>
                ) : hasFilters ? (
                  <Button
                    variant="link"
                    className="h-auto p-0"
                    onClick={() => set(Object.fromEntries([['q', null], ['filter', null], ['match', null], ...filters.map((f) => [f.key, null])]))}
                  >
                    Clear search and filters
                  </Button>
                ) : (
                  'The dump has no data for this view.'
                )}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </div>

      {total > 0 && (
        <div className="flex items-center justify-end gap-4 text-muted-foreground">
          <div className="flex items-center gap-2">
            <span>Rows per page</span>
            <Select value={String(pageSize)} onValueChange={(v) => set({ page_size: v })}>
              <SelectTrigger size="sm" className="w-20">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[25, 50, 100, 200, 500].map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <span>
            Page {fmtNumber(page)} of {fmtNumber(pages)}
          </span>
          <ButtonGroup>
            <Button variant="outline" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>
              <IconChevronLeft />
            </Button>
            <Button variant="outline" size="icon-sm" aria-label="Next page" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>
              <IconChevronRight />
            </Button>
          </ButtonGroup>
        </div>
      )}
    </div>
  )
}

interface HeaderCellProps<T> {
  header: Header<T, unknown>
  sort?: string | null
  order?: string | null
  onCycleSort: (key: string) => void
  onSort: (key: string | null, order: 'asc' | 'desc' | null) => void
  field?: FilterField
  filters: ActiveFilter[]
  onFilters: (fs: ActiveFilter[]) => void
}

/** Header label (click to sort) plus a menu to sort, search or pick values of this column, and hide it. */
function HeaderCell<T>({ header, sort, order, onCycleSort, onSort, field, filters, onFilters }: HeaderCellProps<T>) {
  const col = header.column
  const key = col.columnDef.meta?.sort
  const label = flexRender(col.columnDef.header, header.getContext())
  const idx = field ? filters.findIndex((f) => f.key === field.key) : -1
  const current = idx >= 0 ? filters[idx] : field ? newFilter(field) : null
  const filtered = idx >= 0 && isComplete(filters[idx])
  const setCurrent = (f: ActiveFilter) => onFilters(idx >= 0 ? filters.map((x, i) => (i === idx ? f : x)) : [...filters, f])
  const sorted = !!key && sort === key
  return (
    <div className="flex items-center gap-1">
      {key ? (
        <button className="inline-flex items-center gap-1 whitespace-nowrap hover:text-foreground" onClick={() => onCycleSort(key)}>
          {label}
          {sorted && (order === 'desc' ? <IconArrowDown className="size-3.5" /> : <IconArrowUp className="size-3.5" />)}
        </button>
      ) : (
        <span className="whitespace-nowrap">{label}</span>
      )}
      {filtered && <IconFilterFilled className="size-3.5 text-foreground" aria-label="Filtered" />}
      {(key || field || col.getCanHide()) && (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="ghost"
              size="icon-xs"
              className={cn('text-muted-foreground opacity-0 group-hover/head:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100', filtered && 'opacity-100')}
              aria-label="Column options"
            >
              <IconDotsVertical />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="flex w-72 flex-col gap-2 p-2 font-normal">
            {key && (
              <div className="flex gap-1">
                <Button variant={sorted && order === 'asc' ? 'secondary' : 'ghost'} size="sm" className="flex-1" onClick={() => onSort(key, 'asc')}>
                  <IconArrowUp /> Ascending
                </Button>
                <Button variant={sorted && order === 'desc' ? 'secondary' : 'ghost'} size="sm" className="flex-1" onClick={() => onSort(key, 'desc')}>
                  <IconArrowDown /> Descending
                </Button>
              </div>
            )}
            {field && current && (
              <>
                {key && <Separator />}
                <div className="flex items-center gap-2">
                  {OPS[field.type].length > 1 ? (
                    <Select value={current.op} onValueChange={(op) => setCurrent({ ...newFilter(field), op: op as ActiveFilter['op'] })}>
                      <SelectTrigger size="sm" className="flex-1">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {OPS[field.type].map((op) => (
                          <SelectItem key={op} value={op}>
                            {opLabel(op, field.type)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <span className="flex-1 text-sm text-muted-foreground">{field.label} is</span>
                  )}
                  {filtered && (
                    <Button variant="ghost" size="sm" onClick={() => onFilters(filters.filter((_, i) => i !== idx))}>
                      Clear
                    </Button>
                  )}
                </div>
                {!noValue(current.op) && <ValueEditor field={field} filter={current} onChange={setCurrent} inline />}
              </>
            )}
            {col.getCanHide() && (
              <>
                {(key || field) && <Separator />}
                <Button variant="ghost" size="sm" className="justify-start" onClick={() => col.toggleVisibility(false)}>
                  <IconEyeOff /> Hide column
                </Button>
              </>
            )}
          </PopoverContent>
        </Popover>
      )}
    </div>
  )
}

function SearchBox({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (v: string) => void }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  useEffect(() => {
    if (text === value) return
    const t = setTimeout(() => onChange(text), 250)
    return () => clearTimeout(t)
  }, [text]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <InputGroup className="h-8 w-72">
      <InputGroupAddon>
        <IconSearch />
      </InputGroupAddon>
      <InputGroupInput value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
    </InputGroup>
  )
}

function ColumnMenu<T>({ table, onReset }: { table: ReturnType<typeof useReactTable<T>>; onReset: () => void }) {
  const hideable = table.getAllLeafColumns().filter((c) => c.getCanHide())
  if (hideable.length === 0) return null
  const hidden = hideable.filter((c) => !c.getIsVisible()).length
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 bg-transparent">
          <IconColumns3 /> Columns
          {hidden > 0 && <span className="text-xs text-muted-foreground tabular-nums">{hidden} hidden</span>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-96 w-56">
        <DropdownMenuLabel>Show columns</DropdownMenuLabel>
        {hideable.map((c) => (
          <DropdownMenuCheckboxItem key={c.id} checked={c.getIsVisible()} onCheckedChange={(v) => c.toggleVisibility(!!v)} onSelect={(e) => e.preventDefault()}>
            {typeof c.columnDef.header === 'string' ? c.columnDef.header : c.id}
          </DropdownMenuCheckboxItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onReset}>Reset to default</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** Flatten API rows to CSV: object references become their display name, lists are joined. */
function toCsv(rows: unknown[]) {
  const flat = rows.map((r) => flatten(r as Record<string, unknown>))
  const cols = [...new Set(flat.flatMap((r) => Object.keys(r)))]
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [cols.join(','), ...flat.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}

function flatten(o: Record<string, unknown>, prefix = '', out: Record<string, unknown> = {}) {
  for (const [k, v] of Object.entries(o)) {
    const key = prefix + k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      const ref = v as Record<string, unknown>
      if ('displayName' in ref && 'type' in ref) out[key] = ref.displayName
      else flatten(ref, `${key}.`, out)
    } else if (Array.isArray(v)) {
      out[key] = v.map((x) => (x && typeof x === 'object' ? ((x as Record<string, unknown>).displayName ?? JSON.stringify(x)) : x)).join('; ')
    } else out[key] = v
  }
  return out
}

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  URL.revokeObjectURL(url)
}
