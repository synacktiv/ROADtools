import { useEffect, useState } from 'react'
import { IconFilter2, IconPlus, IconX } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { ButtonGroup, ButtonGroupText } from '@/components/ui/button-group'
import { Checkbox } from '@/components/ui/checkbox'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { FilterField, FilterOp, FilterType } from '@/api/types'

export interface ActiveFilter {
  key: string
  op: FilterOp
  /** Raw value; for in / notIn a list of items. */
  value: string | string[]
}

export const OPS: Record<FilterType, FilterOp[]> = {
  text: ['contains', 'notContains', 'eq', 'ne', 'startsWith', 'endsWith', 'empty', 'notEmpty'],
  enum: ['in', 'notIn', 'empty', 'notEmpty'],
  bool: ['eq'],
  date: ['gt', 'lt', 'empty', 'notEmpty'],
  number: ['eq', 'ne', 'gt', 'lt'],
}

export function opLabel(op: FilterOp, type: FilterType) {
  if (type === 'date') return op === 'gt' ? 'after' : op === 'lt' ? 'before' : op === 'empty' ? 'is empty' : 'is set'
  return {
    contains: 'contains',
    notContains: 'does not contain',
    eq: type === 'number' ? '=' : 'is',
    ne: type === 'number' ? '≠' : 'is not',
    startsWith: 'starts with',
    endsWith: 'ends with',
    empty: 'is empty',
    notEmpty: 'is not empty',
    in: 'is any of',
    notIn: 'is none of',
    gt: '>',
    lt: '<',
  }[op]
}

export const noValue = (op: FilterOp) => op === 'empty' || op === 'notEmpty'
export const isList = (op: FilterOp) => op === 'in' || op === 'notIn'

/** `field:op:value` — the wire format of the `filter` query parameter. */
export function serializeFilter(f: ActiveFilter) {
  const v = Array.isArray(f.value) ? f.value.map(encodeURIComponent).join(',') : f.value
  return `${f.key}:${f.op}:${v}`
}

export function parseFilter(s: string): ActiveFilter | null {
  const a = s.indexOf(':')
  const b = s.indexOf(':', a + 1)
  if (a < 0 || b < 0) return null
  const op = s.slice(a + 1, b) as FilterOp
  const raw = s.slice(b + 1)
  return { key: s.slice(0, a), op, value: isList(op) ? (raw ? raw.split(',').map(decodeURIComponent) : []) : raw }
}

export function newFilter(field: FilterField): ActiveFilter {
  const op = OPS[field.type][0]
  return { key: field.key, op, value: field.type === 'bool' ? 'true' : isList(op) ? [] : '' }
}

/** Filters that are complete enough to send to the API. */
export const isComplete = (f: ActiveFilter) => noValue(f.op) || (Array.isArray(f.value) ? f.value.length > 0 : f.value !== '')

interface FilterBuilderProps {
  fields: FilterField[]
  filters: ActiveFilter[]
  match: 'all' | 'any'
  onChange: (filters: ActiveFilter[], match: 'all' | 'any') => void
}

export function FilterBuilder({ fields, filters, match, onChange }: FilterBuilderProps) {
  const [adding, setAdding] = useState(false)
  const set = (i: number, f: ActiveFilter) => onChange(filters.map((x, j) => (j === i ? f : x)), match)
  const add = (field: FilterField) => {
    onChange([...filters, newFilter(field)], match)
    setAdding(false)
  }
  return (
    <>
      {filters.map((f, i) => {
        const field = fields.find((x) => x.key === f.key)
        return field ? (
          <FilterChip key={i} field={field} filter={f} onChange={(nf) => set(i, nf)} onRemove={() => onChange(filters.filter((_, j) => j !== i), match)} />
        ) : null
      })}
      <Popover open={adding} onOpenChange={setAdding}>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 border-dashed bg-transparent">
            {filters.length ? <IconPlus /> : <IconFilter2 />}
            {filters.length ? 'Add filter' : 'Filter'}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-0">
          <Command>
            <CommandInput placeholder="Filter by…" />
            <CommandList>
              <CommandEmpty>No such field.</CommandEmpty>
              <CommandGroup>
                {fields.map((f) => (
                  <CommandItem key={f.key} value={f.label} onSelect={() => add(f)}>
                    {f.label}
                    <span className="ml-auto text-xs text-muted-foreground">{f.type === 'bool' ? 'yes / no' : f.type}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {filters.length > 1 && (
        <Select value={match} onValueChange={(m) => onChange(filters, m as 'all' | 'any')}>
          <SelectTrigger size="sm" className="h-8 bg-transparent">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Match all</SelectItem>
            <SelectItem value="any">Match any</SelectItem>
          </SelectContent>
        </Select>
      )}
      {filters.length > 0 && (
        <Button variant="ghost" size="sm" className="h-8 text-muted-foreground" onClick={() => onChange([], 'all')}>
          Clear
        </Button>
      )}
    </>
  )
}

function FilterChip({ field, filter, onChange, onRemove }: { field: FilterField; filter: ActiveFilter; onChange: (f: ActiveFilter) => void; onRemove: () => void }) {
  const ops = OPS[field.type]
  const setOp = (op: FilterOp) => onChange({ ...filter, op, value: isList(op) === isList(filter.op) ? filter.value : isList(op) ? [] : '' })
  return (
    <ButtonGroup className="h-8">
      <ButtonGroupText className="h-8 bg-transparent font-medium">{field.label}</ButtonGroupText>
      {ops.length > 1 && (
        <Select value={filter.op} onValueChange={(v) => setOp(v as FilterOp)}>
          <SelectTrigger size="sm" className="h-8 bg-transparent text-muted-foreground">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ops.map((op) => (
              <SelectItem key={op} value={op}>
                {opLabel(op, field.type)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {!noValue(filter.op) && <ValueEditor field={field} filter={filter} onChange={onChange} />}
      <Button variant="outline" size="icon-sm" className="h-8 bg-transparent" aria-label={`Remove ${field.label} filter`} onClick={onRemove}>
        <IconX />
      </Button>
    </ButtonGroup>
  )
}

export function ValueEditor({ field, filter, onChange, inline }: { field: FilterField; filter: ActiveFilter; onChange: (f: ActiveFilter) => void; inline?: boolean }) {
  if (field.type === 'bool')
    return (
      <Select value={String(filter.value)} onValueChange={(v) => onChange({ ...filter, value: v })}>
        <SelectTrigger size="sm" className="h-8 bg-transparent">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true">Yes</SelectItem>
          <SelectItem value="false">No</SelectItem>
        </SelectContent>
      </Select>
    )
  if (field.type === 'enum') return inline ? <EnumList field={field} filter={filter} onChange={onChange} /> : <EnumValue field={field} filter={filter} onChange={onChange} />
  return <TextValue type={field.type} value={String(filter.value)} onCommit={(v) => onChange({ ...filter, value: v })} />
}

function TextValue({ type, value, onCommit }: { type: FilterType; value: string; onCommit: (v: string) => void }) {
  const [text, setText] = useState(value)
  useEffect(() => setText(value), [value])
  useEffect(() => {
    if (text === value) return
    const t = setTimeout(() => onCommit(text), 400)
    return () => clearTimeout(t)
  }, [text]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Input
      autoFocus={!value}
      type={type === 'date' ? 'date' : type === 'number' ? 'number' : 'text'}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onKeyDown={(e) => e.key === 'Enter' && onCommit(text)}
      placeholder="Value"
      className="h-8 w-40 rounded-none bg-transparent"
    />
  )
}

function EnumValue({ field, filter, onChange }: { field: FilterField; filter: ActiveFilter; onChange: (f: ActiveFilter) => void }) {
  const selected = Array.isArray(filter.value) ? filter.value : []
  const options = field.options ?? []
  const label = (v: string) => options.find((o) => o.value === v)?.label ?? v
  const toggle = (v: string) => onChange({ ...filter, value: selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v] })
  return (
    <Popover defaultOpen={selected.length === 0}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 max-w-56 justify-start bg-transparent font-normal">
          <span className="truncate">{selected.length === 0 ? 'Choose…' : selected.length <= 2 ? selected.map(label).join(', ') : `${selected.length} selected`}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-0">
        <Command>
          <CommandInput placeholder={field.label} />
          <CommandList>
            <CommandEmpty>No value.</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem key={o.value} value={o.label} onSelect={() => toggle(o.value)}>
                  <Checkbox checked={selected.includes(o.value)} className="pointer-events-none" />
                  {o.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

/** Checkbox list of enum values, shown directly (column header menu). */
function EnumList({ field, filter, onChange }: { field: FilterField; filter: ActiveFilter; onChange: (f: ActiveFilter) => void }) {
  const selected = Array.isArray(filter.value) ? filter.value : []
  const toggle = (v: string) => onChange({ ...filter, value: selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v] })
  return (
    <Command className="rounded-lg border bg-transparent">
      <CommandInput placeholder={`Search ${field.label.toLowerCase()}`} />
      <CommandList className="max-h-60">
        <CommandEmpty>No value.</CommandEmpty>
        <CommandGroup>
          {(field.options ?? []).map((o) => (
            <CommandItem key={o.value} value={o.label} onSelect={() => toggle(o.value)}>
              <Checkbox checked={selected.includes(o.value)} className="pointer-events-none" />
              {o.label}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </Command>
  )
}
