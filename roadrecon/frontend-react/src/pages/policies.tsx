import { lazy, Suspense, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import {
  IconAlertTriangle,
  IconArrowRight,
  IconCircleCheck,
  IconCircleCheckFilled,
  IconCircleFilled,
  IconCircleHalf2,
  IconMinus,
  IconNetwork,
  IconShieldCheck,
  IconShieldX,
  IconWorld,
  IconX,
} from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Card, CardContent } from '@/components/ui/card'
import { DataTable, useTableParams } from '@/components/data-table'
import { ObjectLink, TYPE_LABEL } from '@/components/object-link'
import { ObjectPage } from '@/components/object-page'
import { PolicyStateBadge, flag } from '@/components/badges'
import { PolicyFlow } from '@/components/policy-flow'
import { BlockMark, IconText, PolicyMatchList, SessionControls, grantIcon, grantSummary } from '@/components/policy-match-list'
import { Dash, ListPage, orDash, toRef } from '@/components/page-parts'
import { UsersTable } from '@/pages/users'
import { useApi } from '@/api/client'
import type { NamedLocationRow, ObjectRef, ObjectType, PolicyQuery, PolicyRow, WhatIfMatch, WhatIfQuery, WhatIfResult } from '@/api/types'
import { fmtDate, fmtNumber, plural } from '@/lib/format'
import { useSetCrumb } from '@/lib/crumb'

// The world map data is ~1 MB: its own chunk, fetched only by the named location pages.
const worldMap = () => import('@/components/world-map')
const NamedLocationMap = lazy(() => worldMap().then((m) => ({ default: m.NamedLocationMap })))
const NamedLocationsOverviewMap = lazy(() => worldMap().then((m) => ({ default: m.NamedLocationsOverviewMap })))
const mapFallback = <Skeleton className="h-64 w-full" />
import { cn } from '@/lib/utils'

/** All vs selected scope: a full disc for everyone, a half disc for a selection. */
function Scope({ all }: { all: boolean }) {
  const I = all ? IconCircleFilled : IconCircleHalf2
  return (
    <span className={cn('inline-flex items-center gap-1.5', all ? 'font-medium' : 'text-muted-foreground')}>
      <I className="size-3.5 shrink-0" stroke={2} aria-hidden />
      {all ? 'All' : 'Selected'}
    </span>
  )
}

function Unreadable({ error }: { error: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="regulatory" tabIndex={0} className="cursor-help">
          <IconAlertTriangle stroke={2} aria-hidden />
          Unreadable
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{error}</TooltipContent>
    </Tooltip>
  )
}

const columns: ColumnDef<PolicyRow>[] = [
  {
    id: 'displayName',
    header: 'Policy',
    meta: { sort: 'displayName', filter: 'displayName' },
    enableHiding: false,
    // Enabled is the norm: only report-only and disabled get a marker next to the name.
    cell: ({ row }) => (
      <span className="flex min-w-0 items-center gap-2">
        <ObjectLink value={toRef('policy', row.original)} className={cn(row.original.state === 'disabled' && 'text-muted-foreground')} />
        {row.original.state !== 'enabled' && <PolicyStateBadge state={row.original.state} />}
        {row.original.parseError && <Unreadable error={row.original.parseError} />}
      </span>
    ),
  },
  { id: 'state', header: 'State', meta: { sort: 'state', filter: 'state', noCopy: true, defaultHidden: true }, cell: ({ row }) => <PolicyStateBadge state={row.original.state} /> },
  { id: 'users', header: 'Users', meta: { filter: 'targetsAllUsers', noCopy: true }, cell: ({ row }) => <Scope all={row.original.targetsAllUsers} /> },
  { id: 'apps', header: 'Resources', meta: { filter: 'targetsAllApps', noCopy: true }, cell: ({ row }) => <Scope all={row.original.targetsAllApps} /> },
  { id: 'grant', header: 'Grant', meta: { filter: 'grant' }, cell: ({ row }) => grantSummary(row.original) },
  { id: 'block', header: 'Blocks access', meta: { filter: 'block', noCopy: true, defaultHidden: true }, cell: ({ row }) => flag(row.original.block, true) },
  {
    id: 'session',
    header: 'Session',
    meta: { filter: 'sessionControls', noCopy: true },
    cell: ({ row }) => (row.original.sessionControls.length ? <SessionControls items={row.original.sessionControls} compact /> : <Dash />),
  },
  { id: 'modified', header: 'Modified', meta: { sort: 'modifiedDateTime', filter: 'modifiedDateTime', className: 'tabular-nums' }, cell: ({ row }) => orDash(fmtDate(row.original.modifiedDateTime)) },
  { id: 'id', header: 'Policy ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.id },
]

/** Expanded row: the policy route in compact form. Same query as the policy page, so opening it is instant. */
function PolicyPeek({ id }: { id: string }) {
  const { data: p } = useApi('/api/policies/{id}', { path: { id } })
  return (
    <div className="flex flex-col gap-4">
      {p ? <PolicyFlow policy={p} compact /> : <Skeleton className="h-28 w-full" />}
      <Link to={`/policies/${id}`} className="inline-flex items-center gap-1 self-start text-sm text-info hover:underline">
        Open policy <IconArrowRight className="size-4" stroke={1.75} aria-hidden />
      </Link>
    </div>
  )
}

/** Users in scope vs excluded, as one proportional bar. The counts are in the tab labels, so the text gives shares. */
function UserSplit({ inScope, excluded }: { inScope: number; excluded: number }) {
  const total = inScope + excluded
  // Shares add up to 100; a non-zero side never rounds to 0.
  const ex = excluded && (inScope ? Math.min(99, Math.max(1, Math.round((excluded / total) * 100))) : 100)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex h-2 gap-0.5" role="img" aria-label={`${fmtNumber(inScope)} in scope, ${fmtNumber(excluded)} excluded`}>
        {inScope > 0 && <span className="min-w-1.5 rounded-full bg-guide" style={{ flex: `${inScope} 1 0` }} />}
        {excluded > 0 && <span className="min-w-1.5 rounded-full bg-regulatory" style={{ flex: `${excluded} 1 0` }} />}
      </div>
      <div className="flex justify-between gap-3 text-sm tabular-nums">
        <span>
          <span className="font-semibold">{100 - ex}%</span> <span className="text-muted-foreground">in scope</span>
        </span>
        <span className={excluded ? 'text-regulatory' : 'text-muted-foreground'}>
          <span className="font-semibold">{ex}%</span> excluded
        </span>
      </div>
    </div>
  )
}

/** A policy's result for the sign-in check: applies, or may apply and what it depends on. */
function CheckResult({ m }: { m?: WhatIfMatch | null }) {
  if (!m) return <Dash />
  if (m.result === 'applies')
    return (
      <span className="inline-flex items-center gap-1.5 font-medium text-guide">
        <IconCircleCheckFilled className="size-4.5 shrink-0" aria-hidden />
        Applies
      </span>
    )
  return (
    <span className="flex min-w-0 flex-col">
      <span className="inline-flex items-center gap-1.5 font-medium text-warning">
        <IconCircleCheck className="size-4.5 shrink-0" stroke={2} aria-hidden />
        May apply
      </span>
      <span className="text-sm text-pretty text-muted-foreground">Depends on {m.dependsOn.join(', ').toLowerCase()}</span>
    </span>
  )
}

const checkColumn: ColumnDef<PolicyRow> = {
  id: 'whatIf',
  header: 'Sign-in check',
  enableHiding: false,
  meta: { noCopy: true, className: 'max-w-72 whitespace-normal' },
  cell: ({ row }) => <CheckResult m={row.original.whatIf} />,
}

export function PoliciesTable({ query, check }: { query?: Partial<PolicyQuery>; check?: boolean }) {
  return (
    <DataTable
      route="/api/policies"
      query={query}
      columns={check ? [columns[0], checkColumn, ...columns.slice(1)] : columns}
      resource="policies"
      searchPlaceholder="Search policy name"
      noun="policy"
      defaultSort={{ sort: 'displayName', order: 'asc' }}
      renderExpanded={(p) => <PolicyPeek id={p.id} />}
    />
  )
}

// --- Sign-in check ----------------------------------------------------------

const CHECK_KEYS = ['identity', 'resource', 'location', 'platform', 'clientApp', 'signInRisk', 'userRisk', 'authFlow'] as const
const ANY = '_any' // Radix Select has no empty value
const RISKS: [string, string][] = [['none', 'No risk'], ['low', 'Low'], ['medium', 'Medium'], ['high', 'High']]
const CHOICES: [key: (typeof CHECK_KEYS)[number], label: string, options: [string, string][]][] = [
  ['platform', 'Device platform', [['android', 'Android'], ['ios', 'iOS'], ['windows', 'Windows'], ['windowsphone', 'Windows Phone'], ['macos', 'macOS'], ['linux', 'Linux']]],
  ['clientApp', 'Client app', [['browser', 'Browser'], ['native', 'Mobile apps and desktop clients'], ['eas', 'Exchange ActiveSync'], ['other', 'Other clients']]],
  ['signInRisk', 'Sign-in risk', RISKS],
  ['userRisk', 'User risk', RISKS],
  ['authFlow', 'Authentication flow', [['none', 'None'], ['deviceCodeFlow', 'Device code flow'], ['authenticationTransfer', 'Authentication transfer']]],
]
const USER_ACTIONS: [string, string][] = [['urn:user:registersecurityinfo', 'Register security information'], ['urn:user:registerdevice', 'Register or join devices']]

function CheckField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span className="text-sm text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}

function Choice({ label, value, options, onChange }: { label: string; value?: string; options: [string, string][]; onChange: (v: string | null) => void }) {
  return (
    <CheckField label={label}>
      <Select value={value ?? ANY} onValueChange={(v) => onChange(v === ANY ? null : v)}>
        <SelectTrigger className="w-full" aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>
            <span className="text-muted-foreground">Any</span>
          </SelectItem>
          {options.map(([v, l]) => (
            <SelectItem key={v} value={v}>
              {l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </CheckField>
  )
}

/** Searches the dump for objects of `types`; `fixed(q)` adds options that are not objects (user actions, contexts). */
function ObjectChoice({ label, types, selected, valueOf, fixed, onChange }: {
  label: string
  types: ObjectType[]
  selected?: ObjectRef | null
  valueOf: (r: ObjectRef) => string | null | undefined
  fixed?: (q: string) => [string, string][]
  onChange: (v: string | null) => void
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 150)
    return () => clearTimeout(t)
  }, [text])
  const { data } = useApi('/api/search', { query: { q, limit: 8 } }, q.length >= 2)
  const groups = q.length >= 2 ? (data?.groups ?? []).filter((g) => types.includes(g.type) && g.items.length > 0) : []
  const extra = fixed?.(q) ?? []
  const choose = (v: string | null | undefined) => {
    onChange(v ?? null)
    setOpen(false)
    setText('')
  }
  return (
    <CheckField label={label}>
      <div className="flex min-w-0 gap-1">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" aria-label={label} className="h-8 min-w-0 flex-1 justify-start bg-transparent px-2.5 font-normal">
              {!selected ? (
                <span className="text-muted-foreground">Any</span>
              ) : selected.type === 'keyword' ? (
                <span className="truncate">{selected.displayName}</span>
              ) : (
                <ObjectLink value={{ ...selected, id: null }} className="pointer-events-none min-w-0" />
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-96 max-w-[calc(100vw-2rem)] p-0">
            <Command shouldFilter={false}>
              <CommandInput value={text} onValueChange={setText} placeholder="Name, UPN, app ID or object ID" />
              <CommandList>
                {q.length >= 2 && <CommandEmpty>Nothing matches “{q}”.</CommandEmpty>}
                {extra.length > 0 && (
                  <CommandGroup heading="Not an application">
                    {extra.map(([v, l]) => (
                      <CommandItem key={v} value={v} onSelect={() => choose(v)}>
                        {l}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                )}
                {groups.map((g) => (
                  <CommandGroup key={g.type} heading={`${TYPE_LABEL[g.type]}s`}>
                    {g.items.map((r) => (
                      <CommandItem key={r.id} value={`${g.type}:${r.id}`} onSelect={() => choose(valueOf(r))}>
                        <ObjectLink value={{ ...r, id: null }} sub className="pointer-events-none" />
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ))}
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
        {selected && (
          <Button variant="ghost" size="icon" className="size-8" aria-label={`Clear ${label.toLowerCase()}`} onClick={() => onChange(null)}>
            <IconX />
          </Button>
        )}
      </div>
    </CheckField>
  )
}

/** User actions always, an authentication context when the text looks like one (c1 to c99). */
const resourceExtras = (q: string): [string, string][] => [
  ...USER_ACTIONS.filter(([, l]) => l.toLowerCase().includes(q.toLowerCase())),
  ...(/^c\d{1,2}$/i.test(q) ? [[q.toLowerCase(), `Authentication context ${q.toLowerCase()}`] as [string, string]] : []),
]

/** What the enabled policies enforce on the sign-in: the verdict first, then what it depends on. */
function CheckOutcome({ r }: { r: WhatIfResult }) {
  const maybe = [r.mayBlock && 'block access', r.mayRequireMfa && !r.block && !r.requiresMfa && 'require MFA'].filter(Boolean).join(' or ')
  return (
    <div className="flex flex-col gap-3 border-t pt-4">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-lg">
        {r.block ? (
          <BlockMark label="Access blocked" />
        ) : r.requiresMfa ? (
          <span className="inline-flex items-center gap-1.5 font-semibold text-guide">
            <IconShieldCheck className="size-5" stroke={2} aria-hidden />
            MFA required
          </span>
        ) : r.mayRequireMfa ? (
          <span className="inline-flex items-center gap-1.5 font-semibold text-warning">
            <IconShieldCheck className="size-5" stroke={2} aria-hidden />
            MFA may be required
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 font-semibold text-regulatory">
            <IconShieldX className="size-5" stroke={2} aria-hidden />
            MFA not required
          </span>
        )}
        {!r.block && r.grant.length > 0 && (
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1 text-base">
            {r.grant.map((g) => (
              <IconText key={g} icon={grantIcon(g)}>
                {g}
              </IconText>
            ))}
          </span>
        )}
        {!r.block && r.sessionControls.length > 0 && <SessionControls items={r.sessionControls} compact />}
      </div>
      <ul className="flex flex-col gap-1 text-muted-foreground">
        <li>
          {r.applies ? `${plural(r.applies, 'enforced policy applies', 'enforced policies apply')}${r.applies > 1 && r.grant.length ? '; each one must be satisfied.' : '.'}` : 'No enforced policy applies for sure.'}
        </li>
        {r.mayApply > 0 && (
          <li className="text-warning">
            {plural(r.mayApply, `${r.applies ? 'more ' : ''}policy may apply`, `${r.applies ? 'more ' : ''}policies may apply`)}
            {maybe && <> and {maybe}</>}, depending on {r.dependsOn.join(', ').toLowerCase()}.
          </li>
        )}
        {r.reportOnly > 0 && <li>{plural(r.reportOnly, 'report-only policy also matches', 'report-only policies also match')}, logged but not enforced.</li>}
      </ul>
    </div>
  )
}

function SignInCheck({ values, set }: { values: WhatIfQuery; set: (patch: Record<string, string | null>) => void }) {
  const active = CHECK_KEYS.some((k) => values[k])
  const { data: r } = useApi('/api/policies/what-if', { query: values }, active)
  const { data: locations } = useApi('/api/named-locations', { query: { page_size: 500 } })
  const locationOptions: [string, string][] = [...(locations?.items ?? []).map((l): [string, string] => [l.id, l.displayName]), ['other', 'Outside every named location']]
  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <h2 className="font-semibold">Sign-in check</h2>
            <p className="text-sm text-muted-foreground">Describe a sign-in to see what it must satisfy. A condition left on Any can be anything.</p>
          </div>
          {active && (
            <Button variant="ghost" size="sm" onClick={() => set(Object.fromEntries(CHECK_KEYS.map((k) => [k, null])))}>
              Clear
            </Button>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ObjectChoice label="User or workload identity" types={['user', 'servicePrincipal']} selected={values.identity ? r?.identity : null} valueOf={(o) => o.id} onChange={(v) => set({ identity: v })} />
          <ObjectChoice label="Target resource" types={['servicePrincipal']} selected={values.resource ? r?.resource : null} valueOf={(o) => o.sub} fixed={resourceExtras} onChange={(v) => set({ resource: v })} />
          <Choice label="Location" value={values.location ?? undefined} options={locationOptions} onChange={(v) => set({ location: v })} />
          {CHOICES.map(([k, label, options]) => (
            <Choice key={k} label={label} value={values[k] ?? undefined} options={options} onChange={(v) => set({ [k]: v })} />
          ))}
        </div>
        {active && r && <CheckOutcome r={r} />}
      </CardContent>
    </Card>
  )
}

export function PoliciesPage() {
  const { params, set } = useTableParams()
  const values = Object.fromEntries(CHECK_KEYS.map((k) => [k, params.get(k) ?? undefined])) as WhatIfQuery
  const active = CHECK_KEYS.some((k) => values[k])
  return (
    <ListPage
      title="Conditional Access"
      description="Policies evaluated at sign-in. Unfold a row for its route from users to grant controls; open it for every user it applies to after exclusions."
    >
      <SignInCheck values={values} set={set} />
      <PoliciesTable query={values} check={active} />
    </ListPage>
  )
}

export function PolicyPage() {
  const { id = '' } = useParams()
  const { data: p, isLoading, error } = useApi('/api/policies/{id}', { path: { id } })
  useSetCrumb(p?.displayName)
  return (
    <ObjectPage
      type="policy"
      title={p?.displayName}
      loading={isLoading}
      error={error}
      portalUrl={`https://entra.microsoft.com/#view/Microsoft_AAD_ConditionalAccess/PolicyBlade/policyId/${id}`}
      raw={p?.raw}
      summary={p && [
        ['Grant', p.block ? null : grantSummary(p)],
        ['Session', p.sessionControls.length ? <SessionControls key="se" items={p.sessionControls} /> : null],
        ['Users', p.counts.inScope + p.counts.excluded ? <UserSplit key="u" inScope={p.counts.inScope} excluded={p.counts.excluded} /> : null],
        ['Modified', fmtDate(p.modifiedDateTime, true)],
        ['Policy ID', p.id, { mono: true, copy: p.id }],
      ]}
      badges={
        p && (
          <>
            <PolicyStateBadge state={p.state} />
            {p.block && <Badge variant="regulatory">Block</Badge>}
            {p.parseError && <Badge variant="regulatory">Partly unreadable</Badge>}
          </>
        )
      }
      tabs={[
        {
          key: 'route',
          label: 'Policy',
          render: () =>
            p && (
              <div className="flex flex-col gap-8">
                <p className="max-w-[72ch] text-muted-foreground">
                  {p.state === 'disabled'
                    ? 'This policy is disabled and never evaluated.'
                    : p.state === 'reporting'
                      ? 'Report-only: sign-ins are evaluated and logged, but nothing is enforced.'
                      : 'Enforced at every sign-in that matches all conditions below.'}
                </p>
                <Card>
                  <CardContent className="pt-3">
                    <PolicyFlow policy={p} />
                  </CardContent>
                </Card>
                {p.parseError && (
                  <IconText icon={IconAlertTriangle} className="text-regulatory [&>svg]:text-regulatory">
                    Part of this policy could not be read: {p.parseError}. The raw definition is in the Raw tab.
                  </IconText>
                )}
              </div>
            ),
        },
        {
          key: 'inScope',
          label: 'Users in scope',
          count: p?.counts.inScope,
          render: () => <UsersTable route="/api/policies/{id}/users" path={{ id }} query={{ effect: 'applies' }} noun="user in scope" />,
        },
        {
          key: 'excluded',
          label: 'Excluded users',
          count: p?.counts.excluded,
          render: () => <UsersTable route="/api/policies/{id}/users" path={{ id }} query={{ effect: 'excluded' }} noun="excluded user" />,
        },
      ]}
    />
  )
}

// --- Named locations -------------------------------------------------------

const Kind = ({ kind }: { kind: NamedLocationRow['kind'] }) => <IconText icon={kind === 'ip' ? IconNetwork : IconWorld}>{kind === 'ip' ? 'IP ranges' : 'Countries'}</IconText>

const TrustedBadge = () => (
  <Badge variant="warning">
    <IconShieldCheck stroke={2} aria-hidden />
    Trusted
  </Badge>
)

/** IP ranges in mono, countries as code chips, plus a marker when unknown countries are included. */
function Ranges({ l }: { l: NamedLocationRow }) {
  if (l.kind === 'ip')
    return (
      <span className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-sm">
        {l.ipRanges.map((r) => (
          <span key={r}>{r}</span>
        ))}
      </span>
    )
  return (
    <span className="flex flex-wrap items-center gap-1">
      {l.countries.map((c) => (
        <Badge key={c} variant="outline" className="font-mono">
          {c}
        </Badge>
      ))}
      {l.includeUnknownCountries && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Badge variant="outline" tabIndex={0} className="cursor-help border-dashed text-muted-foreground">
              Unknown
            </Badge>
          </TooltipTrigger>
          <TooltipContent>Also matches sign-ins whose country cannot be determined</TooltipContent>
        </Tooltip>
      )}
    </span>
  )
}

/** Policies referencing a location; excluded references get a red minus. */
function LocationPolicies({ l }: { l: NamedLocationRow }) {
  if (l.policies.length === 0) return <Dash />
  return (
    <ul className="flex flex-col gap-1">
      {l.policies.map((p) => (
        <li key={p.id} className="flex min-w-0 items-center gap-1.5">
          <ObjectLink value={p} wrap className="max-w-full" />
          {l.excludedBy.includes(p.id!) && (
            <span className="inline-flex shrink-0 items-center text-sm text-regulatory">
              <IconMinus className="size-3.5" stroke={2.25} aria-hidden />
              excluded
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

const locationColumns: ColumnDef<NamedLocationRow>[] = [
  {
    id: 'displayName',
    header: 'Location',
    meta: { sort: 'displayName', filter: 'displayName' },
    enableHiding: false,
    cell: ({ row }) => (
      <span className="flex min-w-0 items-center gap-2">
        <ObjectLink value={toRef('namedLocation', row.original)} />
        {row.original.trusted && <TrustedBadge />}
      </span>
    ),
  },
  { id: 'kind', header: 'Kind', meta: { filter: 'kind' }, cell: ({ row }) => <Kind kind={row.original.kind} /> },
  { id: 'trusted', header: 'Trusted', meta: { filter: 'trusted', noCopy: true, defaultHidden: true }, cell: ({ row }) => flag(row.original.trusted) },
  { id: 'ranges', header: 'Ranges or countries', meta: { className: 'max-w-[56ch] whitespace-normal' }, cell: ({ row }) => <Ranges l={row.original} /> },
  {
    id: 'policies',
    header: 'Used by',
    meta: { filter: 'policyCount', noCopy: true, className: 'max-w-96 whitespace-normal' },
    cell: ({ row }) => <LocationPolicies l={row.original} />,
  },
  { id: 'policyCount', header: 'Policies', meta: { filter: 'policyCount', defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => fmtNumber(row.original.policyCount) },
  { id: 'id', header: 'ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.id },
]

export function NamedLocationsPage() {
  // ponytail: one unfiltered page for the map, separate from the table's paged query; fine for the few hundred locations a tenant has.
  const { data } = useApi('/api/named-locations', { query: { page_size: 500 } })
  return (
    <ListPage title="Named locations" description="IP ranges and countries referenced by Conditional Access location conditions. Trusted locations are often excluded from MFA requirements.">
      <div className="flex flex-col gap-6">
        {/* The map sizes itself to max-w-4xl; capped here so the table stays above the fold. */}
        {data && (
          <div>
            <Suspense fallback={mapFallback}>
              <NamedLocationsOverviewMap locations={data.items} size="md" />
            </Suspense>
          </div>
        )}
        <DataTable route="/api/named-locations" columns={locationColumns} resource="named-locations" noun="named location" defaultSort={{ sort: 'displayName', order: 'asc' }} />
      </div>
    </ListPage>
  )
}

export function NamedLocationPage() {
  const { id = '' } = useParams()
  const { data: l, isLoading, error } = useApi('/api/named-locations/{id}', { path: { id } })
  useSetCrumb(l?.displayName)
  return (
    <ObjectPage
      type="namedLocation"
      title={l?.displayName}
      loading={isLoading}
      error={error}
      badges={l?.trusted && <TrustedBadge />}
      aside={l && (
        <Suspense fallback={mapFallback}>
          <NamedLocationMap location={l} />
        </Suspense>
      )}
      raw={l?.raw}
      summary={l && [
        ['Kind', <Kind key="k" kind={l.kind} />],
        ['IP ranges', l.ipRanges],
        // Countries and the unknown-country switch are on the map card.
        ['ID', l.id, { mono: true, copy: l.id }],
      ]}
      tabs={[
        {
          key: 'policies',
          label: 'Used by',
          count: l?.policyMatches.length,
          render: () => l && <PolicyMatchList matches={l.policyMatches} showReasons={false} />,
        },
      ]}
    />
  )
}
