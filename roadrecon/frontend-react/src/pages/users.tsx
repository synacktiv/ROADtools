import { Link, useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import { IconAlertTriangle, IconCloud, IconServer2, IconShieldBolt, IconShieldCheck, IconShieldOff, IconUserShare } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable, useTableParams, type FilterDef } from '@/components/data-table'
import { ObjectLink } from '@/components/object-link'
import { ObjectPage } from '@/components/object-page'
import { MfaMethods } from '@/components/mfa-methods'
import { EnabledBadge, Flag, KindBadge, Marker, PolicyStateBadge, SourceIcon, StatusMark } from '@/components/badges'
import { Dash, ListPage, SubViews, orDash, toRef } from '@/components/page-parts'
import { ObjectPolicies } from '@/components/policy-match-list'
import { GroupsTable } from '@/pages/groups'
import { DevicesTable, AdministrativeUnitsTable } from '@/pages/devices'
import { ApplicationsTable, ServicePrincipalsTable } from '@/pages/apps'
import { RoleAssignmentsTable } from '@/pages/roles'
import { AppRoleAssignmentsTable, OAuth2GrantsTable } from '@/pages/grants'
import { AccessPackagesTable, AzureRolesTable, PimAssignmentsTable } from '@/pages/governance'
import { useApi } from '@/api/client'
import type { MfaSummary, RoleAssignmentRow, Route, Routes, UserQuery, UserRow } from '@/api/types'
import { fmtDate, fmtNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useSettings } from '@/lib/settings'
import { useSetCrumb } from '@/lib/crumb'

const DAY = 864e5
const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
function ago(ms: number) {
  const days = ms / DAY
  return days >= 365 ? rtf.format(-Math.floor(days / 365), 'year') : days >= 30 ? rtf.format(-Math.floor(days / 30), 'month') : rtf.format(-Math.floor(days), 'day')
}

/** Password change date; older than a year is flagged as a warning. */
function PasswordAge({ value, detail }: { value: string; detail?: boolean }) {
  const age = Date.now() - new Date(value).getTime()
  const old = age > 365 * DAY
  const body = (
    <span className={cn('inline-flex items-center gap-1.5', old && 'text-warning')} tabIndex={old ? 0 : undefined}>
      {old && <IconAlertTriangle className="size-4 shrink-0" stroke={1.75} aria-label="Old password" />}
      {fmtDate(value, detail)}
      {detail && <span className={old ? undefined : 'text-muted-foreground'}>({ago(age)})</span>}
    </span>
  )
  if (!old) return body
  return (
    <Tooltip>
      <TooltipTrigger asChild>{body}</TooltipTrigger>
      <TooltipContent>Not changed for more than a year</TooltipContent>
    </Tooltip>
  )
}

function SourceMark({ dirSync }: { dirSync: boolean | null }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex align-middle">
          <SourceIcon dirSync={dirSync} withLabel={false} />
        </span>
      </TooltipTrigger>
      <TooltipContent>{dirSync ? 'Synced from AD' : 'Cloud'}</TooltipContent>
    </Tooltip>
  )
}

const mfaCount = (m: MfaSummary) => m.methods.length + m.fido + m.windowsHello

/** "No MFA": red for an enabled account, muted for a disabled one. */
function NoMfaBadge({ enabled }: { enabled: boolean }) {
  return (
    <Badge variant={enabled ? 'regulatory' : 'outline'} className={enabled ? undefined : 'text-muted-foreground'}>
      <IconShieldOff stroke={1.75} />
      No MFA
    </Badge>
  )
}

function PerUserMfa({ state }: { state: string | null }) {
  if (!state) return <Dash />
  return <Badge variant={state === 'Enforced' ? 'guide' : 'outline'}>{state}</Badge>
}

/** Name cell: the link, then disabled / guest / no-MFA markers. */
function UserName({ u }: { u: UserRow }) {
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <ObjectLink value={toRef('user', u)} />
      {!u.accountEnabled && <StatusMark status="disabled" />}
      {u.userType === 'Guest' && <Marker icon={IconUserShare} label="Guest" className="text-muted-foreground" />}
      {mfaCount(u.mfa) === 0 && <StatusMark status="noMfa" muted={!u.accountEnabled} />}
    </span>
  )
}

type Col = ColumnDef<UserRow>
const hidden = (c: Col): Col => ({ ...c, meta: { ...c.meta, defaultHidden: true } })
const COL = {
  name: { id: 'displayName', header: 'Name', meta: { sort: 'displayName', filter: 'displayName' }, enableHiding: false, cell: ({ row }) => <UserName u={row.original} /> },
  upn: { accessorKey: 'userPrincipalName', header: 'UPN', meta: { sort: 'userPrincipalName', filter: 'userPrincipalName' } },
  source: { id: 'dirSyncEnabled', header: 'Source', meta: { filter: 'dirSyncEnabled', noCopy: true }, cell: ({ row }) => <SourceMark dirSync={row.original.dirSyncEnabled} /> },
  mail: { id: 'mail', header: 'Mail', meta: { filter: 'mail' }, cell: ({ row }) => orDash(row.original.mail) },
  department: { id: 'department', header: 'Department', meta: { filter: 'department' }, cell: ({ row }) => orDash(row.original.department) },
  jobTitle: { id: 'jobTitle', header: 'Job title', meta: { filter: 'jobTitle' }, cell: ({ row }) => orDash(row.original.jobTitle) },
  mobile: { id: 'mobile', header: 'Mobile', meta: { filter: 'mobile' }, cell: ({ row }) => orDash(row.original.mobile) },
  password: {
    id: 'lastPasswordChangeDateTime',
    header: 'Password changed',
    meta: { sort: 'lastPasswordChangeDateTime', filter: 'lastPasswordChangeDateTime' },
    cell: ({ row }) => (row.original.lastPasswordChangeDateTime ? <PasswordAge value={row.original.lastPasswordChangeDateTime} /> : <Dash />),
  },
  mfa: { id: 'mfa', header: 'MFA', meta: { filter: 'mfaMethod', noCopy: true }, cell: ({ row }) => (mfaCount(row.original.mfa) ? <MfaMethods mfa={row.original.mfa} /> : <Dash />) },
  perUserMfa: { id: 'perUserMfa', header: 'Per-user MFA', meta: { filter: 'perUserMfa', noCopy: true }, cell: ({ row }) => <PerUserMfa state={row.original.mfa.perUserMfa} /> },
  userType: { id: 'userType', header: 'Type', meta: { filter: 'userType' }, cell: ({ row }) => row.original.userType },
  enabled: { id: 'accountEnabled', header: 'Enabled', meta: { filter: 'accountEnabled' }, cell: ({ row }) => <Flag value={row.original.accountEnabled} risky={false} /> },
  hasMfa: { id: 'hasMfa', header: 'Has MFA', meta: { filter: 'hasMfa' }, cell: ({ row }) => <Flag value={mfaCount(row.original.mfa) > 0} risky={false} /> },
  hasApp: { id: 'hasApp', header: 'App', meta: { filter: 'hasApp', noCopy: true }, cell: ({ row }) => <Flag value={row.original.mfa.methods.some((m) => m.startsWith('PhoneApp'))} /> },
  hasPhone: { id: 'hasPhone', header: 'Phone', meta: { filter: 'hasPhone', noCopy: true }, cell: ({ row }) => <Flag value={row.original.mfa.methods.some((m) => m === 'OneWaySms' || m.startsWith('TwoWayVoice'))} /> },
  hasFido: { id: 'hasFido', header: 'FIDO', meta: { filter: 'hasFido', noCopy: true }, cell: ({ row }) => <Flag value={row.original.mfa.fido > 0} /> },
  mfaRequired: {
    id: 'mfaRequired',
    header: 'MFA required',
    meta: { noCopy: true },
    // Enforced by a Conditional Access policy / authentication strength — distinct from Registered (methods the user set up).
    cell: ({ row }) => <Flag value={row.original.mfaRequired} label="Enforced by a Conditional Access policy (authentication strength included)" />,
  },
  id: { accessorKey: 'id', header: 'Object ID', meta: { className: 'font-mono text-sm' } },
} satisfies Record<string, Col>

function userColumns(mfa: boolean): Col[] {
  return [
    COL.name, COL.upn, COL.source, COL.mail, COL.department, COL.jobTitle, COL.mobile, COL.password,
    ...(mfa ? [COL.mfa] : []),
    ...[COL.userType, COL.enabled, COL.hasMfa, COL.perUserMfa, COL.id].map(hidden),
  ]
}

const MFA_COLUMNS: Col[] = [
  COL.name,
  COL.upn,
  COL.perUserMfa,
  {
    id: 'count',
    header: 'Methods',
    meta: { className: 'tabular-nums', filter: 'hasMfa' },
    cell: ({ row }) => {
      const n = mfaCount(row.original.mfa)
      return <span className={n ? undefined : 'text-muted-foreground'}>{n}</span>
    },
  },
  COL.hasApp,
  COL.hasPhone,
  COL.hasFido,
  { ...COL.mfa, header: 'Registered' },
  ...[COL.enabled, COL.userType, COL.source, COL.mail, COL.department, COL.jobTitle, COL.password, COL.id].map(hidden),
]

interface UsersTableProps {
  route?: Extract<Route, '/api/users' | '/api/policies/{id}/users'>
  path?: Record<string, string>
  query?: Partial<UserQuery> & Record<string, unknown>
  filters?: FilterDef[]
  noun?: string
}

export function UsersTable({ route = '/api/users', path, query, filters = [], noun = 'user' }: UsersTableProps) {
  const { mfaColumns } = useSettings()
  return (
    <DataTable
      route={route}
      path={path}
      query={query as Partial<Routes['/api/users']['query']>}
      columns={userColumns(mfaColumns)}
      filters={filters}
      resource="users"
      searchPlaceholder="Search name, UPN or object ID"
      noun={noun}
      defaultSort={{ sort: 'displayName', order: 'asc' }}
    />
  )
}

export function UsersPage() {
  return (
    <ListPage title="Users">
      <UsersTable />
    </ListPage>
  )
}

const NO_MFA = 'hasMfa:eq:false'
const ENABLED = 'accountEnabled:eq:true'
const MFA_VIEWS: [key: string, label: string, filter: string[]][] = [
  ['all', 'All users', []],
  ['exposed', 'Enabled without MFA', [NO_MFA, ENABLED]],
  ['none', 'All without MFA', [NO_MFA]],
]
const sameFilters = (a: string[], b: string[]) => [...a].sort().join('&') === [...b].sort().join('&')

function ViewCount({ filter }: { filter: string[] }) {
  const { data } = useApi('/api/users', { query: { excludeMailboxOnly: true, filter, page_size: 1 } })
  return <span className="text-muted-foreground tabular-nums">{data ? fmtNumber(data.total) : ''}</span>
}

/** Pre-filters for the MFA table, written to the same `filter` URL param as the filter builder. */
function MfaViews() {
  const { params, set } = useTableParams()
  const active = params.getAll('filter')
  const value = MFA_VIEWS.find(([, , f]) => sameFilters(f, active))?.[0] ?? ''
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => {
        const view = MFA_VIEWS.find(([k]) => k === v)
        if (view) set({ filter: view[2], match: null })
      }}
      className="w-fit"
    >
      {MFA_VIEWS.map(([key, label, filter]) => (
        <ToggleGroupItem key={key} value={key} className={cn('gap-1.5 px-3', key === 'exposed' && 'text-regulatory')}>
          {key === 'exposed' && <IconShieldOff stroke={1.75} />}
          {label}
          <ViewCount filter={filter} />
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

const MFA_REQUIRED: [key: string, label: string][] = [
  ['', 'Any'],
  ['true', 'Required'],
  ['false', 'Not required'],
]

/** Required = an enabled Conditional Access policy / authentication strength enforces MFA, distinct from Registered. */
function MfaRequiredFilter() {
  const { params, set } = useTableParams()
  const value = params.get('mfaRequired') ?? ''
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-muted-foreground">MFA required</span>
      <ToggleGroup type="single" variant="outline" size="sm" value={value} onValueChange={(v) => set({ mfaRequired: v || null })} className="w-fit">
        {MFA_REQUIRED.map(([key, label]) => (
          <ToggleGroupItem key={key || 'any'} value={key} className="px-3">
            {label}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  )
}

export function MfaPage() {
  // "MFA required" needs Conditional Access policies; without them the column and filter stay hidden (data-gated).
  const { data: stats } = useApi('/api/stats')
  const { params } = useTableParams()
  const showRequired = (stats?.policies ?? 0) > 0
  const mfaRequired = params.get('mfaRequired')
  const columns = showRequired ? MFA_COLUMNS.flatMap((c) => (c.header === 'Registered' ? [c, COL.mfaRequired] : [c])) : MFA_COLUMNS
  return (
    <ListPage
      title="MFA"
      description="Strong authentication methods registered per user, and the legacy per-user MFA state. “MFA required” is whether an enabled Conditional Access policy in scope enforces MFA — distinct from the methods a user registered. Mailbox-only accounts (shared and room mailboxes) are left out. Methods registered through the newer authentication methods policy are not in the dump."
    >
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <MfaViews />
        {showRequired && <MfaRequiredFilter />}
      </div>
      <DataTable
        route="/api/users"
        columns={columns}
        query={{ excludeMailboxOnly: true, mfaRequired: mfaRequired === 'true' ? true : mfaRequired === 'false' ? false : undefined }}
        resource="users"
        searchPlaceholder="Search name, UPN or object ID"
        noun="user"
        defaultSort={{ sort: 'displayName', order: 'asc' }}
      />
    </ListPage>
  )
}

/** Posture signals not shown elsewhere on the page: privileged roles held and Conditional Access exclusions. */
function RiskSignals({ id }: { id: string }) {
  const { data: ra } = useApi('/api/role-assignments', { query: { principalId: id, transitive: true, page_size: 500 } })
  // ponytail: whole role list to read isPrivileged; it is small (tens of roles) and cached across user pages.
  const { data: roles } = useApi('/api/roles', { query: { page_size: 500 } })
  const { data: matches } = useApi('/api/policies/affecting/{type}/{id}', { path: { type: 'user', id } })
  const privileged = new Set(roles?.items.filter((r) => r.isPrivileged).map((r) => r.id))
  // One entry per role; an active assignment wins over an eligible one.
  const held = new Map<string, RoleAssignmentRow>()
  for (const a of ra?.items ?? []) if (a.role.id && privileged.has(a.role.id) && (!held.has(a.role.id) || a.kind === 'active')) held.set(a.role.id, a)
  const excluded = (matches ?? []).filter((m) => m.effect === 'excluded')
  // Enabled policies in scope whose grant requires MFA (the MFA control or an authentication strength).
  const mfa = (matches ?? []).filter((m) => m.effect === 'included' && m.policy.state === 'enabled' && m.policy.requiresMfa)
  const mfaApprox = mfa.length > 0 && mfa.every((m) => m.policy.mfaApproximate)
  return (
    <Card className="gap-3 py-3">
      <CardHeader className="px-4">
        <CardTitle className="text-sm font-normal text-muted-foreground">Risk signals</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-4">
        <div className="flex flex-col gap-1">
          <span className={cn('inline-flex items-center gap-1.5 text-sm', held.size ? 'text-regulatory' : 'text-muted-foreground')}>
            <IconShieldBolt className="size-4" stroke={1.75} aria-hidden />
            {!ra || !roles ? 'Privileged roles' : held.size ? `${held.size} privileged ${held.size > 1 ? 'roles' : 'role'}` : 'No privileged roles'}
          </span>
          {[...held.values()].map((a) => (
            <span key={a.role.id} className="flex min-w-0 items-center gap-2 pl-5.5">
              <ObjectLink value={a.role} wrap />
              {a.kind === 'eligible' && <KindBadge kind="eligible" />}
            </span>
          ))}
        </div>
        <div className="flex flex-col gap-1">
          <Link to="?tab=policies" replace className={cn('inline-flex w-fit items-center gap-1.5 text-sm hover:underline underline-offset-4', excluded.length ? 'text-regulatory' : 'text-muted-foreground')}>
            <IconShieldOff className="size-4" stroke={1.75} aria-hidden />
            {!matches ? 'Policy exclusions' : excluded.length ? `Excluded from ${excluded.length} ${excluded.length > 1 ? 'policies' : 'policy'}` : 'Not excluded from any policy'}
          </Link>
          {excluded.map((m) => (
            <span key={m.policy.id} className="flex min-w-0 items-center gap-2 pl-5.5">
              <ObjectLink value={toRef('policy', m.policy)} wrap />
              {m.policy.state !== 'enabled' && <PolicyStateBadge state={m.policy.state} />}
            </span>
          ))}
        </div>
        <span className={cn('inline-flex items-center gap-1.5 text-sm', !matches ? 'text-muted-foreground' : !mfa.length ? 'text-regulatory' : mfaApprox ? 'text-warning' : 'text-muted-foreground')}>
          {mfa.length ? <IconShieldCheck className="size-4" stroke={1.75} aria-hidden /> : <IconShieldOff className="size-4" stroke={1.75} aria-hidden />}
          {!matches ? 'MFA requirement' : !mfa.length ? 'No enabled policy requires MFA' : `MFA required by ${mfa.length} ${mfa.length > 1 ? 'policies' : 'policy'}`}
          {mfaApprox && ' (custom authentication strength, combinations not collected)'}
        </span>
      </CardContent>
    </Card>
  )
}

export function UserPage() {
  const { id = '' } = useParams()
  const { data: u, isLoading, error } = useApi('/api/users/{id}', { path: { id } })
  useSetCrumb(u?.displayName)
  const c = u?.counts
  return (
    <ObjectPage
      type="user"
      title={u?.displayName}
      loading={isLoading}
      error={error}
      portalUrl={`https://entra.microsoft.com/#view/Microsoft_AAD_UsersAndTenants/UserProfileMenuBlade/~/overview/userId/${id}`}
      badges={
        u && (
          <>
            <EnabledBadge enabled={u.accountEnabled} />
            {u.userType === 'Guest' && (
              <Badge variant="outline">
                <IconUserShare stroke={1.75} />
                Guest
              </Badge>
            )}
            <Badge variant="outline">
              {u.dirSyncEnabled ? <IconServer2 stroke={1.75} /> : <IconCloud stroke={1.75} />}
              {u.dirSyncEnabled ? 'Synced from AD' : 'Cloud'}
            </Badge>
            {mfaCount(u.mfa) === 0 && <NoMfaBadge enabled={u.accountEnabled} />}
          </>
        )
      }
      summary={
        u && [
          [
            'MFA',
            <span key="m" className="flex flex-wrap items-center gap-x-3 gap-y-1">
              {mfaCount(u.mfa) > 0 && <MfaMethods mfa={u.mfa} />}
              {u.mfa.perUserMfa ? (
                <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                  Per-user MFA <PerUserMfa state={u.mfa.perUserMfa} />
                </span>
              ) : (
                <span className="text-muted-foreground">Per-user MFA disabled</span>
              )}
            </span>,
          ],
          ['User principal name', u.userPrincipalName, { copy: u.userPrincipalName }],
          ['Object ID', u.id, { mono: true, copy: u.id }],
          ['On-premises SID', u.onPremisesSecurityIdentifier, { mono: true, copy: u.onPremisesSecurityIdentifier ?? undefined }],
          ['On-premises account', u.onPremisesSamAccountName, { copy: u.onPremisesSamAccountName ?? undefined }],
          ['Job title and department', [u.jobTitle, u.department].filter(Boolean).join(', ')],
          ['Password changed', u.lastPasswordChangeDateTime && <PasswordAge value={u.lastPasswordChangeDateTime} detail />],
          // Mail is usually the UPN; show it only when it adds something.
          ['Mail', u.mail?.toLowerCase() === u.userPrincipalName.toLowerCase() ? null : u.mail, { copy: u.mail ?? undefined }],
          ['Mobile', u.mobile],
          ['Created', fmtDate(u.createdDateTime, true)],
          ['Last directory sync', fmtDate(u.lastDirSyncTime, true)],
        ]
      }
      aside={u && <RiskSignals id={id} />}
      raw={u?.raw}
      tabs={[
        {
          key: 'groups',
          label: 'Groups',
          count: c?.memberOf,
          render: () => <GroupsTable query={{ memberId: id }} filters={[{ kind: 'toggle', key: 'transitive', label: 'Include parent groups of nested groups' }]} noun="group" />,
        },
        { key: 'roles', label: 'Roles', count: c?.roles, render: () => <RoleAssignmentsTable query={{ principalId: id, transitive: true }} hidePrincipal /> },
        {
          key: 'owned',
          label: 'Owned objects',
          count: c && c.ownedDevices + c.ownedServicePrincipals + c.ownedApplications + c.ownedGroups,
          render: () => (
            <SubViews
              views={[
                { key: 'applications', label: 'Applications', count: c?.ownedApplications, render: () => <ApplicationsTable query={{ ownerId: id }} /> },
                { key: 'servicePrincipals', label: 'Service principals', count: c?.ownedServicePrincipals, render: () => <ServicePrincipalsTable query={{ ownerId: id }} /> },
                { key: 'groups', label: 'Groups', count: c?.ownedGroups, render: () => <GroupsTable query={{ ownerId: id }} /> },
                { key: 'devices', label: 'Devices', count: c?.ownedDevices, render: () => <DevicesTable query={{ ownerId: id }} /> },
              ]}
            />
          ),
        },
        { key: 'policies', label: 'Policies', count: c?.policies, render: () => <ObjectPolicies type="user" id={id} /> },
        {
          key: 'access',
          label: 'App access',
          count: c && c.appRoleAssignments + c.oauth2Grants,
          render: () => (
            <SubViews
              views={[
                { key: 'appRoles', label: 'App roles', count: c?.appRoleAssignments, render: () => <AppRoleAssignmentsTable query={{ principalId: id }} hidePrincipal /> },
                { key: 'grants', label: 'Delegated permissions', count: c?.oauth2Grants, render: () => <OAuth2GrantsTable query={{ principalId: id }} /> },
              ]}
            />
          ),
        },
        { key: 'units', label: 'Administrative units', count: c?.administrativeUnits, hidden: c?.administrativeUnits === 0, render: () => <AdministrativeUnitsTable query={{ memberId: id }} /> },
        { key: 'pim', label: 'PIM', count: c?.pim, render: () => <PimAssignmentsTable principalId={id} /> },
        { key: 'packages', label: 'Access packages', count: c?.accessPackages, hidden: c?.accessPackages === 0, render: () => <AccessPackagesTable userId={id} /> },
        { key: 'azure', label: 'Azure roles', count: c?.azureRoles, hidden: c?.azureRoles === 0, render: () => <AzureRolesTable principalId={id} /> },
      ]}
    />
  )
}
