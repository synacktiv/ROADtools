import { Link, useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import { IconAlertTriangle, IconArrowRight, IconCircleFilled, IconCircleHalf2, IconMinus, IconNetwork, IconShieldCheck, IconWorld } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Card, CardContent } from '@/components/ui/card'
import { DataTable } from '@/components/data-table'
import { ObjectLink } from '@/components/object-link'
import { ObjectPage } from '@/components/object-page'
import { PolicyStateBadge, flag } from '@/components/badges'
import { NamedLocationMap, NamedLocationsOverviewMap } from '@/components/world-map'
import { PolicyFlow } from '@/components/policy-flow'
import { IconText, PolicyMatchList, SessionControls, grantSummary } from '@/components/policy-match-list'
import { Dash, ListPage, orDash, toRef } from '@/components/page-parts'
import { UsersTable } from '@/pages/users'
import { useApi } from '@/api/client'
import type { NamedLocationRow, PolicyQuery, PolicyRow } from '@/api/types'
import { fmtDate, fmtNumber } from '@/lib/format'
import { useSetCrumb } from '@/lib/crumb'
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

export function PoliciesTable({ query }: { query?: Partial<PolicyQuery> }) {
  return (
    <DataTable
      route="/api/policies"
      query={query}
      columns={columns}
      resource="policies"
      searchPlaceholder="Search policy name"
      noun="policy"
      defaultSort={{ sort: 'displayName', order: 'asc' }}
      renderExpanded={(p) => <PolicyPeek id={p.id} />}
    />
  )
}

export function PoliciesPage() {
  return (
    <ListPage
      title="Conditional Access"
      description="Policies evaluated at sign-in. Unfold a row for its route from users to grant controls; open it for every user it applies to after exclusions."
    >
      <PoliciesTable />
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
            <NamedLocationsOverviewMap locations={data.items} size="md" />
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
      aside={l && <NamedLocationMap location={l} />}
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
