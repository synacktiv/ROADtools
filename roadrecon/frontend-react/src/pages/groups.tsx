import { Link, useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import { IconBolt, IconBrandOffice, IconCornerDownRight, IconCrown, IconMail, IconServer2, IconShield, IconWorld, type Icon } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable, type FilterDef } from '@/components/data-table'
import { ObjectLink } from '@/components/object-link'
import { ObjectPage } from '@/components/object-page'
import { SourceIcon, flag } from '@/components/badges'
import { ListPage, SubViews, orDash, toRef } from '@/components/page-parts'
import { ObjectPolicies } from '@/components/policy-match-list'
import { UsersTable } from '@/pages/users'
import { DevicesTable, AdministrativeUnitsTable } from '@/pages/devices'
import { OwnersTable, ServicePrincipalsTable } from '@/pages/apps'
import { RoleAssignmentsTable } from '@/pages/roles'
import { AppRoleAssignmentsTable } from '@/pages/grants'
import { AzureRolesTable, GroupPimView } from '@/pages/governance'
import { useApi } from '@/api/client'
import type { GroupDetail, GroupQuery, GroupRow } from '@/api/types'
import { fmtDate, fmtNumber } from '@/lib/format'
import { useSetCrumb } from '@/lib/crumb'
import { cn } from '@/lib/utils'

export const groupKind = (g: Pick<GroupRow, 'groupTypes' | 'securityEnabled' | 'mailEnabled'>) =>
  g.groupTypes.includes('Unified') ? 'Microsoft 365' : g.mailEnabled && !g.securityEnabled ? 'Distribution' : g.mailEnabled ? 'Mail-enabled security' : 'Security'

const KIND_ICON: Record<ReturnType<typeof groupKind>, Icon> = {
  'Microsoft 365': IconBrandOffice,
  Distribution: IconMail,
  'Mail-enabled security': IconShield,
  Security: IconShield,
}

function GroupKind({ g }: { g: Pick<GroupRow, 'groupTypes' | 'securityEnabled' | 'mailEnabled'> }) {
  const kind = groupKind(g)
  const I = KIND_ICON[kind]
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <I className="size-4 text-muted-foreground" stroke={1.75} aria-hidden />
      {kind}
    </span>
  )
}

/** Inverted badge: the one group property that turns membership into directory role access. */
function RoleAssignableBadge() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge tabIndex={0}>
          <IconCrown stroke={2} aria-hidden /> Role assignable
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Can hold directory roles. Only privileged role administrators can manage its members and owners.</TooltipContent>
    </Tooltip>
  )
}

/** Small icon with a tooltip, shown after a group name. */
function Marker({ icon: I, label, tip, strong }: { icon: Icon; label: string; tip?: React.ReactNode; strong?: boolean }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label={label} className="inline-flex">
          <I className={cn('size-4', strong ? 'text-foreground' : 'text-muted-foreground')} stroke={1.75} aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-sm">{tip ?? label}</TooltipContent>
    </Tooltip>
  )
}

function GroupName({ g }: { g: GroupRow }) {
  return (
    <span className="inline-flex items-center gap-2">
      <ObjectLink value={toRef('group', g)} />
      {g.isAssignableToRole && <Marker icon={IconCrown} label="Role assignable" strong tip="Role assignable: can hold directory roles. Only privileged role administrators can manage its members and owners." />}
      {g.membershipRule && <Marker icon={IconBolt} label="Dynamic membership" tip={<><span className="block">Dynamic membership</span><span className="font-mono">{g.membershipRule}</span></>} />}
      {g.isPublic && <Marker icon={IconWorld} label="Public" tip="Public: anyone in the tenant can join" />}
      {g.dirSyncEnabled && <Marker icon={IconServer2} label="Synced from AD" />}
    </span>
  )
}

const columns: ColumnDef<GroupRow>[] = [
  { id: 'displayName', header: 'Name', meta: { sort: 'displayName', filter: 'displayName' }, enableHiding: false, cell: ({ row }) => <GroupName g={row.original} /> },
  { id: 'description', header: 'Description', meta: { filter: 'description' }, cell: ({ row }) => orDash(row.original.description) },
  { id: 'kind', header: 'Type', meta: { filter: 'kind' }, cell: ({ row }) => <GroupKind g={row.original} /> },
  { id: 'mail', header: 'Mail', meta: { filter: 'mail' }, cell: ({ row }) => orDash(row.original.mail) },
  { id: 'createdDateTime', header: 'Created', meta: { sort: 'createdDateTime', filter: 'createdDateTime' }, cell: ({ row }) => orDash(fmtDate(row.original.createdDateTime)) },
  { id: 'membershipRule', header: 'Membership rule', meta: { filter: 'membershipRule', defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => orDash(row.original.membershipRule) },
  { id: 'isAssignableToRole', header: 'Role assignable', meta: { filter: 'isAssignableToRole', defaultHidden: true, noCopy: true }, cell: ({ row }) => flag(row.original.isAssignableToRole) },
  { id: 'dynamic', header: 'Dynamic', meta: { filter: 'dynamic', defaultHidden: true, noCopy: true }, cell: ({ row }) => flag(!!row.original.membershipRule) },
  { id: 'isPublic', header: 'Public', meta: { filter: 'isPublic', defaultHidden: true, noCopy: true }, cell: ({ row }) => orDash(flag(row.original.isPublic, true)) },
  { id: 'dirSyncEnabled', header: 'Source', meta: { filter: 'dirSyncEnabled', defaultHidden: true, noCopy: true }, cell: ({ row }) => <SourceIcon dirSync={row.original.dirSyncEnabled} /> },
]

export function GroupsTable({ query, filters = [], noun = 'group' }: { query?: Partial<GroupQuery>; filters?: FilterDef[]; noun?: string }) {
  return (
    <DataTable
      route="/api/groups"
      query={query}
      columns={columns}
      filters={filters}
      resource="groups"
      searchPlaceholder="Search name, mail or object ID"
      noun={noun}
      defaultSort={{ sort: 'displayName', order: 'asc' }}
    />
  )
}

export function GroupsPage() {
  return (
    <ListPage title="Groups">
      <GroupsTable />
    </ListPage>
  )
}

export function GroupPage() {
  const { id = '' } = useParams()
  const { data: g, isLoading, error } = useApi('/api/groups/{id}', { path: { id } })
  useSetCrumb(g?.displayName)
  const c = g?.counts
  const transitive = { kind: 'toggle', key: 'transitive', label: 'Include members of nested groups' } as const
  return (
    <ObjectPage
      type="group"
      title={g?.displayName}
      loading={isLoading}
      error={error}
      portalUrl={`https://entra.microsoft.com/#view/Microsoft_AAD_IAM/GroupDetailsMenuBlade/~/Overview/groupId/${id}`}
      badges={
        g && (
          <>
            {g.isAssignableToRole && <RoleAssignableBadge />}
            {g.membershipRule && (
              <Badge variant="outline">
                <IconBolt aria-hidden /> Dynamic
              </Badge>
            )}
            {g.dirSyncEnabled && (
              <Badge variant="outline">
                <IconServer2 aria-hidden /> Synced
              </Badge>
            )}
            {g.pimEnabled && <Badge variant="warning">PIM</Badge>}
          </>
        )
      }
      summary={g && [
        ['Description', g.description],
        ['Type', <GroupKind key="k" g={g} />],
        ['Membership rule', g.membershipRule, { mono: true, copy: g.membershipRule ?? undefined }],
        ['Mail', g.mail, g.mail ? { copy: g.mail } : undefined],
        ['Public', flag(g.isPublic, true)],
        ['Created', fmtDate(g.createdDateTime, true)],
        ['Object ID', g.id, { mono: true, copy: g.id }],
        ['Security identifier', g.securityIdentifier, { mono: true, copy: g.securityIdentifier ?? undefined }],
        ['On-premises security identifier', g.onPremisesSecurityIdentifier, { mono: true, copy: g.onPremisesSecurityIdentifier ?? undefined }],
      ]}
      aside={c && <MembershipCard c={c} />}
      raw={g?.raw}
      tabs={[
        {
          key: 'members',
          label: 'Members',
          count: c && c.memberUsers + c.memberGroups + c.memberServicePrincipals + c.memberDevices,
          render: () => (
            <SubViews
              views={[
                { key: 'users', label: 'Users', count: c?.memberUsers, render: () => <UsersTable query={{ memberOf: id }} filters={[transitive]} noun="member" /> },
                { key: 'groups', label: 'Groups', count: c?.memberGroups, render: () => <GroupsTable query={{ memberOf: id }} filters={[transitive]} noun="member group" /> },
                { key: 'servicePrincipals', label: 'Service principals', count: c?.memberServicePrincipals, render: () => <ServicePrincipalsTable query={{ memberOf: id }} /> },
                { key: 'devices', label: 'Devices', count: c?.memberDevices, render: () => <DevicesTable query={{ memberOf: id }} /> },
              ]}
            />
          ),
        },
        { key: 'memberOf', label: 'Member of', count: c?.memberOf, render: () => <GroupsTable query={{ memberId: id }} filters={[{ kind: 'toggle', key: 'transitive', label: 'Include parents of parent groups' }]} noun="parent group" /> },
        { key: 'owners', label: 'Owners', count: c?.owners, render: () => <OwnersTable ownerOf={id} /> },
        { key: 'roles', label: 'Roles', count: c?.roles, render: () => <RoleAssignmentsTable query={{ principalId: id }} hidePrincipal /> },
        { key: 'policies', label: 'Policies', count: c?.policies, render: () => <ObjectPolicies type="group" id={id} /> },
        { key: 'appRoles', label: 'App roles', count: c?.appRoleAssignments, render: () => <AppRoleAssignmentsTable query={{ principalId: id }} hidePrincipal /> },
        { key: 'units', label: 'Administrative units', count: c?.administrativeUnits, hidden: c?.administrativeUnits === 0, render: () => <AdministrativeUnitsTable query={{ memberId: id }} /> },
        { key: 'pim', label: 'PIM', hidden: g && !g.pimEnabled, render: () => <GroupPimView groupId={id} /> },
        { key: 'azure', label: 'Azure roles', count: c?.azureRoles, hidden: c?.azureRoles === 0, render: () => <AzureRolesTable principalId={id} /> },
      ]}
    />
  )
}

type Counts = GroupDetail['counts']

/**
 * Member mix as one proportional bar, plus users reached through nested groups.
 * Rendered only when it says more than the tab counts: several member types, or nested users.
 */
function MembershipCard({ c }: { c: Counts }) {
  const parts: { view: string; label: string; count: number; shade: string }[] = [
    { view: 'users', label: 'Users', count: c.memberUsers, shade: 'bg-foreground/85' },
    { view: 'groups', label: 'Groups', count: c.memberGroups, shade: 'bg-foreground/55' },
    { view: 'servicePrincipals', label: 'Service principals', count: c.memberServicePrincipals, shade: 'bg-foreground/35' },
    { view: 'devices', label: 'Devices', count: c.memberDevices, shade: 'bg-foreground/20' },
  ].filter((p) => p.count > 0)
  const total = parts.reduce((n, p) => n + p.count, 0)
  const nested = c.transitiveMemberUsers - c.memberUsers
  if (parts.length < 2 && nested <= 0) return null
  return (
    <Card className="gap-3">
      <CardHeader className="px-4">
        <CardTitle>Member mix</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 px-4 text-base">
        {parts.length > 1 && (
          <>
            <div className="flex h-2 gap-0.5 overflow-hidden rounded-full" aria-hidden>
              {parts.map((p) => (
                <span key={p.view} className={p.shade} style={{ flexGrow: p.count }} />
              ))}
            </div>
            <div className="-mx-1.5 flex flex-wrap">
              {parts.map((p) => (
                <Link
                  key={p.view}
                  to={{ search: `?tab=members&view=${p.view}` }}
                  replace
                  className="inline-flex items-center gap-1.5 rounded-md px-1.5 py-1 text-sm transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
                >
                  <span className={cn('size-2 rounded-sm', p.shade)} aria-hidden />
                  {p.label}
                  <span className="text-muted-foreground tabular-nums">{Math.round((p.count / total) * 100)}%</span>
                </Link>
              ))}
            </div>
          </>
        )}
        {nested > 0 && (
          <div className="-mx-2 flex flex-col">
            <CountLink
              search="?tab=members&view=users&transitive=true"
              count={c.transitiveMemberUsers}
              label={`Users including nested groups (+${fmtNumber(nested)})`}
              icon={<IconCornerDownRight className="size-4 text-muted-foreground" stroke={1.75} aria-hidden />}
            />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function CountLink({ search, count, label, icon, children }: { search: string; count: number; label: string; icon: React.ReactNode; children?: React.ReactNode }) {
  return (
    <Link
      to={{ search }}
      replace
      className="flex items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {children}
      {icon}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <span className="tabular-nums">{fmtNumber(count)}</span>
    </Link>
  )
}
