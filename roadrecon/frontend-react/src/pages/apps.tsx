import { useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import {
  IconAlertTriangle,
  IconApps,
  IconArchive,
  IconBrandWindows,
  IconCertificate,
  IconCircleCheck,
  IconCircleOff,
  IconClockExclamation,
  IconClockX,
  IconHelpCircle,
  IconIdBadge2,
  IconKey,
  IconLockAccess,
  IconServerBolt,
  IconServerCog,
  IconUserShare,
  IconUserStar,
  IconWorld,
  type Icon,
} from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable, type FilterDef } from '@/components/data-table'
import { ObjectLink, TYPE_LABEL } from '@/components/object-link'
import { ObjectPage, Section } from '@/components/object-page'
import { JsonView } from '@/components/json-view'
import { CredentialList, expiryState, type ExpiryState } from '@/components/credential-list'
import { BoolMark, EnabledBadge, Flag, flag } from '@/components/badges'
import { ListPage, SubViews, orDash, toRef } from '@/components/page-parts'
import { ObjectPolicies } from '@/components/policy-match-list'
import { GroupsTable } from '@/pages/groups'
import { RoleAssignmentsTable } from '@/pages/roles'
import { AppRoleAssignmentsTable, OAuth2GrantsTable } from '@/pages/grants'
import { AzureRolesTable } from '@/pages/governance'
import { useApi } from '@/api/client'
import type {
  AppRoleDefinition,
  ApplicationQuery,
  ApplicationRow,
  Credential,
  MetadataEntry,
  ObjectRef,
  PermissionScopeDefinition,
  RequiredResourceAccess,
  ServicePrincipalQuery,
  ServicePrincipalRow,
} from '@/api/types'
import { useSetCrumb } from '@/lib/crumb'
import { plural } from '@/lib/format'
import { cn } from '@/lib/utils'

// --- Visual helpers --------------------------------------------------------

const DEFAULT_ACCESS = '00000000-0000-0000-0000-000000000000'

/** Tokens sent to plain http or a local listener can be caught by whoever runs that host. */
const isRiskyUrl = (u: string) => /^http:\/\//i.test(u) || /^[a-z][\w+.-]*:\/\/(localhost|127\.0\.0\.1|\[::1\])([:/]|$)/i.test(u)

// ponytail: name pattern, not a privilege model. Swap for a per-permission tier once the API ships one.

/** Icon (and optional text) with the explanation in a tooltip. */
function Hint({ label, className, children }: { label: string; className?: string; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label={label} className={cn('inline-flex items-center gap-1 rounded-sm', className)}>
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

const SP_TYPES: Record<string, [Icon, string]> = {
  Application: [IconApps, 'Application'],
  ManagedIdentity: [IconServerCog, 'Managed identity'],
  Legacy: [IconArchive, 'Legacy'],
  SocialIdp: [IconWorld, 'Social identity provider'],
}

/** Application is the common case and stays quiet; managed identities and legacy SPs stand out. */
function SpType({ type, label }: { type: string | null; label?: boolean }) {
  if (!type) return null
  const [I, text] = SP_TYPES[type] ?? [IconHelpCircle, type]
  const icon = <I className={cn('size-4', type === 'Application' && 'text-muted-foreground')} stroke={1.75} aria-hidden />
  if (label)
    return (
      <span className="inline-flex items-center gap-1.5">
        {icon}
        {text}
      </span>
    )
  return <Hint label={text}>{icon}</Hint>
}

/** Name-cell marker for secrets and certificates; counts in the tooltip. Red on apps not published by Microsoft: someone in reach holds that key. */
function CredMark({ secrets, certs, risky }: { secrets: number; certs: number; risky: boolean }) {
  if (secrets + certs === 0) return null
  const what = [secrets && plural(secrets, 'client secret'), certs && plural(certs, 'certificate')].filter(Boolean).join(', ')
  return (
    <Hint label={risky ? `${what} on a non-Microsoft app` : what} className={cn('gap-0.5', risky ? 'text-regulatory' : 'text-muted-foreground')}>
      {secrets > 0 && <IconKey className="size-4" stroke={1.75} aria-hidden />}
      {certs > 0 && <IconCertificate className="size-4" stroke={1.75} aria-hidden />}
    </Hint>
  )
}

/** Name followed by icon-only status markers. Icons carry no text, so the cell copy button still copies just the name. */
function NameCell({ value, children }: { value: ObjectRef; children: React.ReactNode }) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <ObjectLink value={value} />
      <span className="flex shrink-0 items-center gap-1.5 empty:hidden">{children}</span>
    </span>
  )
}

const DisabledMark = () => (
  <Hint label="Disabled" className="text-regulatory">
    <IconCircleOff className="size-4" stroke={1.75} />
  </Hint>
)

/** App roles and delegated scopes this app defines, as compact counts. */
function Defines({ roles, scopes }: { roles: number; scopes: number }) {
  if (roles + scopes === 0) return null
  const what = [roles && plural(roles, 'app role'), scopes && plural(scopes, 'delegated scope')].filter(Boolean).join(', ')
  return (
    <Hint label={`Defines ${what}`} className="gap-3 tabular-nums">
      {roles > 0 && (
        <span className="inline-flex items-center gap-1">
          <IconIdBadge2 className="size-4 text-muted-foreground" stroke={1.75} aria-hidden />
          {roles}
        </span>
      )}
      {scopes > 0 && (
        <span className="inline-flex items-center gap-1">
          <IconLockAccess className="size-4 text-muted-foreground" stroke={1.75} aria-hidden />
          {scopes}
        </span>
      )}
    </Hint>
  )
}

const OwnerMark = ({ owned }: { owned: boolean }) =>
  owned ? (
    <Hint label="Has an owner set in this tenant" className="text-muted-foreground">
      <IconUserStar className="size-4" stroke={1.75} />
    </Hint>
  ) : null

/** Breaks long URLs after slashes instead of mid-word. */
const breakable = (u: string) => u.split('/').flatMap((part, i) => (i === 0 ? [part] : [<wbr key={i} />, '/', part]))

/** Reply URLs and homepages; plain http and localhost are flagged. Returns null when empty so the summary skips the row. */
function urls(items: (string | null)[]) {
  const list = items.filter((u): u is string => !!u)
  if (list.length === 0) return null
  return (
    <ul className="flex flex-col gap-0.5">
      {list.map((u) =>
        isRiskyUrl(u) ? (
          <li key={u} className="flex items-start gap-1.5 font-mono text-sm leading-6 text-regulatory">
            <Hint label="Plain http or localhost: a token can reach a host an attacker may control" className="mt-1 shrink-0">
              <IconAlertTriangle className="size-4" stroke={1.75} />
            </Hint>
            <span className="break-words">{breakable(u)}</span>
          </li>
        ) : (
          <li key={u} className="font-mono text-sm leading-6 break-words">
            {breakable(u)}
          </li>
        ),
      )}
    </ul>
  )
}

// --- Credentials and application permissions card -------------------------

// Order: the one worth acting on first, expired (harmless) last.
const EXPIRY: [ExpiryState, Icon, string, string][] = [
  ['soon', IconClockExclamation, 'text-warning', 'expiring within 30 days'],
  ['valid', IconCircleCheck, 'text-guide', 'valid'],
  ['never', IconCircleCheck, 'text-guide', 'valid, no expiry date'],
  ['expired', IconClockX, 'text-muted-foreground', 'expired'],
]

interface Permission {
  value: string
  isPrivileged: boolean
}

interface PermissionGroup {
  resource: ObjectRef
  values: Permission[]
}

function CardHeading({ title, count }: { title: string; count: number }) {
  return (
    <h2 className="flex items-baseline gap-2 text-base font-semibold">
      {title}
      <span className="font-normal text-muted-foreground tabular-nums">{count}</span>
    </h2>
  )
}

/**
 * Side card with risk signals the tabs do not show directly: how many credentials are still usable,
 * and the high privilege application permissions only. Full lists live in the Credentials and permission tabs.
 */
function RiskCard({ credentials, permissions, permissionsTitle }: { credentials: Credential[]; permissions: PermissionGroup[]; permissionsTitle: string }) {
  const hot = permissions.map((g) => ({ ...g, values: g.values.filter((p) => p.isPrivileged) })).filter((g) => g.values.length > 0)
  const hotCount = hot.reduce((n, g) => n + g.values.length, 0)
  const states = EXPIRY.map(([state, I, tone, word]) => [I, tone, word, credentials.filter((c) => expiryState(c.endDate) === state).length] as const).filter(([, , , n]) => n > 0)
  if (states.length === 0 && hotCount === 0) return null
  return (
    <Card className="gap-0 py-0 text-base">
      {states.length > 0 && (
        <CardContent className="flex flex-col gap-2 px-4 py-3">
          <h2 className="text-base font-semibold">Credential expiry</h2>
          <ul className="flex flex-col gap-1">
            {states.map(([I, tone, word, n]) => (
              <li key={word} className="flex items-center gap-2">
                <I className={cn('size-4 shrink-0', tone)} stroke={1.75} aria-hidden />
                <span className="tabular-nums">{n}</span>
                <span className="text-muted-foreground">{word}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      )}
      {hotCount > 0 && (
        <CardContent className={cn('flex flex-col gap-2 px-4 py-3', states.length > 0 && 'border-t')}>
          <CardHeading title={permissionsTitle} count={hotCount} />
          {hot.map((g) => (
            <div key={g.resource.id ?? g.resource.displayName} className="flex flex-col gap-1.5">
              <ObjectLink value={g.resource} className="text-sm text-muted-foreground" />
              <ul className="flex flex-wrap gap-1.5">
                {g.values.map((p) => (
                  <li key={p.value}>
                    <PermissionChip p={p} app />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </CardContent>
      )}
    </Card>
  )
}

/** Application permissions are amber (no signed-in user), high privilege ones red. Delegated ones are outlined. */
function PermissionChip({ p, app }: { p: Permission; app: boolean }) {
  const hot = app && p.isPrivileged
  const chip = (
    <Badge variant={hot ? 'regulatory' : app ? 'warning' : 'outline'} className="h-6 px-2 font-mono text-sm font-normal">
      {hot && <IconAlertTriangle stroke={1.75} aria-hidden />}
      {p.value}
    </Badge>
  )
  return hot ? (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="inline-flex rounded-sm">
          {chip}
        </span>
      </TooltipTrigger>
      <TooltipContent>High privilege application permission: enough to take over the tenant or its data</TooltipContent>
    </Tooltip>
  ) : (
    chip
  )
}

/** App roles this SP holds on other apps: its application permissions. */
function useHeldPermissions(principalId: string, enabled: boolean): PermissionGroup[] {
  const { data } = useApi('/api/app-role-assignments', { query: { principalId, page_size: 500 } }, enabled)
  const groups = new Map<string, PermissionGroup>()
  for (const a of data?.items ?? []) {
    if (a.appRoleId === DEFAULT_ACCESS) continue
    const key = a.resource.id ?? a.resource.displayName
    const g = groups.get(key) ?? { resource: a.resource, values: [] }
    if (!g.values.some((p) => p.value === a.value)) g.values.push(a)
    groups.set(key, g)
  }
  return [...groups.values()]
}

// --- Service principals ----------------------------------------------------

const spColumns: ColumnDef<ServicePrincipalRow>[] = [
  {
    id: 'displayName',
    header: 'Name',
    meta: { sort: 'displayName', filter: 'displayName' },
    enableHiding: false,
    cell: ({ row }) => {
      const r = row.original
      return (
        <NameCell value={toRef('servicePrincipal', r)}>
          {!r.accountEnabled && <DisabledMark />}
          {r.microsoftFirstParty && (
            <Hint label="Microsoft first-party app" className="text-muted-foreground">
              <IconBrandWindows className="size-4" stroke={1.75} />
            </Hint>
          )}
          {r.servicePrincipalType !== 'Application' && <SpType type={r.servicePrincipalType} />}
          <CredMark secrets={r.passwordCount} certs={r.keyCount} risky={r.microsoftFirstParty !== true} />
          <OwnerMark owned={r.hasCustomOwner} />
        </NameCell>
      )
    },
  },
  { id: 'publisher', header: 'Publisher', meta: { sort: 'publisherName', filter: 'publisherName' }, cell: ({ row }) => orDash(row.original.publisherName) },
  { id: 'defines', header: 'Defines', meta: { noCopy: true }, cell: ({ row }) => <Defines roles={row.original.appRoleCount} scopes={row.original.oauth2PermissionCount} /> },
  { id: 'appId', header: 'App ID', meta: { filter: 'appId', defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.appId },
  { id: 'type', header: 'Type', meta: { filter: 'servicePrincipalType', defaultHidden: true, noCopy: true }, cell: ({ row }) => <SpType type={row.original.servicePrincipalType} label /> },
  { id: 'microsoft', header: 'Microsoft app', meta: { filter: 'microsoftFirstParty', defaultHidden: true, noCopy: true }, cell: ({ row }) => <BoolMark value={row.original.microsoftFirstParty} /> },
  { id: 'enabled', header: 'Enabled', meta: { filter: 'accountEnabled', defaultHidden: true, noCopy: true }, cell: ({ row }) => <Flag value={row.original.accountEnabled} risky={false} /> },
  { id: 'assignment', header: 'Assignment required', meta: { filter: 'appRoleAssignmentRequired', defaultHidden: true, noCopy: true }, cell: ({ row }) => <BoolMark value={row.original.appRoleAssignmentRequired} /> },
  { id: 'secrets', header: 'Secrets', meta: { filter: 'passwordCount', defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => row.original.passwordCount },
  { id: 'certificates', header: 'Certificates', meta: { filter: 'keyCount', defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => row.original.keyCount },
  { id: 'appRoles', header: 'App roles', meta: { filter: 'appRoleCount', defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => row.original.appRoleCount },
  { id: 'owner', header: 'Has owner', meta: { filter: 'hasCustomOwner', defaultHidden: true, noCopy: true }, cell: ({ row }) => <BoolMark value={row.original.hasCustomOwner} /> },
]

export function ServicePrincipalsTable({ query, filters = [] }: { query?: Partial<ServicePrincipalQuery>; filters?: FilterDef[] }) {
  return (
    <DataTable
      route="/api/service-principals"
      query={query}
      columns={spColumns}
      filters={filters}
      resource="service-principals"
      searchPlaceholder="Search name, app ID or object ID"
      noun="service principal"
      defaultSort={{ sort: 'displayName', order: 'asc' }}
    />
  )
}

export function ServicePrincipalsPage() {
  return (
    <ListPage title="Service principals">
      <ServicePrincipalsTable />
    </ListPage>
  )
}

export function ServicePrincipalPage() {
  const { id = '' } = useParams()
  const { data: s, isLoading, error } = useApi('/api/service-principals/{id}', { path: { id } })
  const held = useHeldPermissions(id, !!s?.counts.appRoleAssignments)
  useSetCrumb(s?.displayName)
  const c = s?.counts
  return (
    <ObjectPage
      type="servicePrincipal"
      title={s?.displayName}
      loading={isLoading}
      error={error}
      portalUrl={s && `https://entra.microsoft.com/#view/Microsoft_AAD_IAM/ManagedAppMenuBlade/~/Overview/objectId/${id}/appId/${s.appId}`}
      badges={
        s && (
          <>
            {!s.accountEnabled && <EnabledBadge enabled={false} />}
            {s.microsoftFirstParty && <Badge variant="outline">Microsoft</Badge>}
            {s.servicePrincipalType === 'ManagedIdentity' && <Badge variant="outline">Managed identity</Badge>}
            {s.passwordCount + s.keyCount > 0 && <Badge variant={s.microsoftFirstParty ? 'outline' : 'regulatory'}>Has credentials</Badge>}
          </>
        )
      }
      summary={
        s && [
          ['Application ID', s.appId, { mono: true, copy: s.appId }],
          ['Application object', s.application && <ObjectLink value={s.application} />],
          // Managed identity is a header badge.
          ['Type', s.servicePrincipalType !== 'ManagedIdentity' ? <SpType type={s.servicePrincipalType} label /> : null],
          ['Publisher', s.publisherName],
          ['Owner tenant', s.appOwnerTenantId, { mono: true, copy: s.appOwnerTenantId ?? undefined }],
          ['Assignment required', flag(s.appRoleAssignmentRequired)],
          ['Homepage', urls([s.homepage])],
          ['Reply URLs', urls(s.replyUrls)],
          // The app ID is always one of the names; it is shown above.
          ['Service principal names', s.servicePrincipalNames.filter((n) => n !== s.appId)],
          ['Object ID', s.id, { mono: true, copy: s.id }],
        ]
      }
      aside={s && <RiskCard credentials={s.credentials} permissions={held} permissionsTitle="High privilege permissions held" />}
      raw={s?.raw}
      tabs={[
        { key: 'owners', label: 'Owners', count: c?.owners, render: () => <OwnersTable ownerOf={id} /> },
        { key: 'memberOf', label: 'Member of', count: c?.memberOf, render: () => <GroupsTable query={{ memberId: id }} noun="group" /> },
        { key: 'roles', label: 'Roles', count: c?.roles, render: () => <RoleAssignmentsTable query={{ principalId: id, transitive: true }} hidePrincipal /> },
        {
          key: 'appRoles',
          label: 'App roles',
          count: c && c.appRoleAssignments + c.appRoleAssignedTo,
          render: () => (
            <SubViews
              views={[
                { key: 'held', label: 'Held by this app', count: c?.appRoleAssignments, render: () => <AppRoleAssignmentsTable query={{ principalId: id }} hidePrincipal /> },
                { key: 'granted', label: 'Granted on this app', count: c?.appRoleAssignedTo, render: () => <AppRoleAssignmentsTable query={{ resourceId: id }} hideResource /> },
              ]}
            />
          ),
        },
        {
          key: 'grants',
          label: 'Delegated permissions',
          count: c && c.oauth2GrantsAsClient + c.oauth2GrantsAsResource,
          render: () => (
            <SubViews
              views={[
                { key: 'client', label: 'Granted to this app', count: c?.oauth2GrantsAsClient, render: () => <OAuth2GrantsTable query={{ clientId: id }} /> },
                { key: 'resource', label: 'Granted on this app', count: c?.oauth2GrantsAsResource, render: () => <OAuth2GrantsTable query={{ resourceId: id }} /> },
              ]}
            />
          ),
        },
        { key: 'defined', label: 'Defined permissions', count: s && s.appRoles.length + s.oauth2Permissions.length, render: () => s && <DefinedPermissions appRoles={s.appRoles} scopes={s.oauth2Permissions} /> },
        { key: 'credentials', label: 'Credentials', count: s?.credentials.length, render: () => s && <CredentialList items={s.credentials} /> },
        { key: 'policies', label: 'Policies', count: c?.policies, render: () => <ObjectPolicies type="servicePrincipal" id={id} /> },
        { key: 'azure', label: 'Azure roles', count: c?.azureRoles, hidden: c?.azureRoles === 0, render: () => <AzureRolesTable principalId={id} /> },
        { key: 'metadata', label: 'Metadata', hidden: !s?.metadata.length, render: () => s && <Metadata items={s.metadata} /> },
      ]}
    />
  )
}

// --- Applications ----------------------------------------------------------

const appColumns: ColumnDef<ApplicationRow>[] = [
  {
    id: 'displayName',
    header: 'Name',
    meta: { sort: 'displayName', filter: 'displayName' },
    enableHiding: false,
    cell: ({ row }) => {
      const r = row.original
      return (
        <NameCell value={toRef('application', r)}>
          {r.oauth2AllowImplicitFlow && (
            <Hint label="Implicit flow allowed: tokens are returned in the URL" className="text-regulatory">
              <IconAlertTriangle className="size-4" stroke={1.75} />
            </Hint>
          )}
          {/* App registrations live in this tenant, so any credential on them is risky. */}
          <CredMark secrets={r.passwordCount} certs={r.keyCount} risky />
          <OwnerMark owned={r.hasCustomOwner} />
        </NameCell>
      )
    },
  },
  { id: 'multitenant', header: 'Multitenant', meta: { filter: 'availableToOtherTenants', noCopy: true }, cell: ({ row }) => <BoolMark value={row.original.availableToOtherTenants} /> },
  { id: 'publicClient', header: 'Public client', meta: { filter: 'publicClient', noCopy: true }, cell: ({ row }) => <BoolMark value={row.original.publicClient} /> },
  { id: 'defines', header: 'Defines', meta: { noCopy: true }, cell: ({ row }) => <Defines roles={row.original.appRoleCount} scopes={row.original.oauth2PermissionCount} /> },
  { id: 'appId', header: 'App ID', meta: { filter: 'appId', defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.appId },
  {
    id: 'homepage',
    header: 'Homepage',
    meta: { defaultHidden: true },
    cell: ({ row }) => {
      const h = row.original.homepage
      return h ? <span className={cn(isRiskyUrl(h) && 'text-regulatory')}>{h}</span> : null
    },
  },
  { id: 'implicit', header: 'Implicit flow', meta: { filter: 'oauth2AllowImplicitFlow', defaultHidden: true, noCopy: true }, cell: ({ row }) => <Flag value={row.original.oauth2AllowImplicitFlow} risky /> },
  { id: 'secrets', header: 'Secrets', meta: { filter: 'passwordCount', defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => row.original.passwordCount },
  { id: 'certificates', header: 'Certificates', meta: { filter: 'keyCount', defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => row.original.keyCount },
  { id: 'owner', header: 'Has owner', meta: { filter: 'hasCustomOwner', defaultHidden: true, noCopy: true }, cell: ({ row }) => <BoolMark value={row.original.hasCustomOwner} /> },
]

export function ApplicationsTable({ query, filters = [] }: { query?: Partial<ApplicationQuery>; filters?: FilterDef[] }) {
  return (
    <DataTable
      route="/api/applications"
      query={query}
      columns={appColumns}
      filters={filters}
      resource="applications"
      searchPlaceholder="Search name, app ID or object ID"
      noun="application"
      defaultSort={{ sort: 'displayName', order: 'asc' }}
    />
  )
}

export function ApplicationsPage() {
  return (
    <ListPage title="Applications" description="App registrations created in this tenant. Their instances, including apps from other tenants, are listed under service principals.">
      <ApplicationsTable />
    </ListPage>
  )
}

export function ApplicationPage() {
  const { id = '' } = useParams()
  const { data: a, isLoading, error } = useApi('/api/applications/{id}', { path: { id } })
  useSetCrumb(a?.displayName)
  const appPermissions: PermissionGroup[] = (a?.requiredResourceAccess ?? [])
    .map((r) => ({ resource: r.resource, values: r.permissions.filter((p) => p.type === 'Role') }))
    .filter((g) => g.values.length > 0)
  return (
    <ObjectPage
      type="application"
      title={a?.displayName}
      loading={isLoading}
      error={error}
      portalUrl={a && `https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationMenuBlade/~/Overview/appId/${a.appId}`}
      badges={
        a && (
          <>
            {a.accountEnabled === false && <EnabledBadge enabled={false} />}
            {a.availableToOtherTenants && <Badge variant="outline">Multitenant</Badge>}
            {a.oauth2AllowImplicitFlow && <Badge variant="regulatory">Implicit flow</Badge>}
            {a.passwordCount + a.keyCount > 0 && <Badge variant="regulatory">Has credentials</Badge>}
          </>
        )
      }
      summary={
        a && [
          ['Application ID', a.appId, { mono: true, copy: a.appId }],
          ['Service principal', a.servicePrincipal && <ObjectLink value={a.servicePrincipal} />],
          ['Publisher', a.publisherName],
          ['Owner tenant', a.appOwnerTenantId, { mono: true, copy: a.appOwnerTenantId ?? undefined }],
          ['Assignment required', flag(a.appRoleAssignmentRequired)],
          ['Public client', flag(a.publicClient)],
          ['Homepage', urls([a.homepage])],
          ['Reply URLs', urls(a.replyUrls)],
          ['Identifier URIs', a.identifierUris],
          ['Object ID', a.id, { mono: true, copy: a.id }],
        ]
      }
      aside={a && <RiskCard credentials={a.credentials} permissions={appPermissions} permissionsTitle="High privilege permissions requested" />}
      raw={a?.raw}
      tabs={[
        { key: 'owners', label: 'Owners', count: a?.counts.owners, render: () => <OwnersTable ownerOf={id} /> },
        { key: 'api', label: 'API permissions', count: a?.requiredResourceAccess.reduce((n, r) => n + r.permissions.length, 0), render: () => a && <RequiredPermissions items={a.requiredResourceAccess} /> },
        { key: 'defined', label: 'Defined permissions', count: a && a.appRoles.length + a.oauth2Permissions.length, render: () => a && <DefinedPermissions appRoles={a.appRoles} scopes={a.oauth2Permissions} /> },
        { key: 'credentials', label: 'Credentials', count: a?.credentials.length, render: () => a && <CredentialList items={a.credentials} /> },
        { key: 'policies', label: 'Policies', count: a?.counts.policies, render: () => <ObjectPolicies type="application" id={id} /> },
        { key: 'metadata', label: 'Metadata', hidden: !a?.metadata.length, render: () => a && <Metadata items={a.metadata} /> },
      ]}
    />
  )
}

// --- Shared ----------------------------------------------------------------

/** Users and service principals owning an object, in one list. */
export function OwnersTable({ ownerOf }: { ownerOf: string }) {
  return (
    <DataTable
      route="/api/owners"
      query={{ ownerOf }}
      noun="owner"
      columns={[
        { id: 'name', header: 'Name', meta: { sort: 'displayName' }, cell: ({ row }) => <ObjectLink value={row.original} /> },
        { id: 'type', header: 'Type', meta: { noCopy: true }, cell: ({ row }) => TYPE_LABEL[row.original.type] },
        { id: 'sub', header: 'UPN or app ID', cell: ({ row }) => orDash(row.original.sub) },
      ] satisfies ColumnDef<ObjectRef>[]}
    />
  )
}

const th = 'px-3 font-semibold text-ink'

function DefinedPermissions({ appRoles, scopes }: { appRoles: AppRoleDefinition[]; scopes: PermissionScopeDefinition[] }) {
  return (
    <div className="flex flex-col gap-6">
      <Section title="App roles" count={appRoles.length}>
        {appRoles.length === 0 ? (
          <p className="text-muted-foreground">No app roles defined.</p>
        ) : (
          <div className="glass overflow-hidden rounded-xl border">
            <Table>
              <TableHeader className="bg-shoulder">
                <TableRow className="hover:bg-transparent">
                  <TableHead className={th}>Value and ID</TableHead>
                  <TableHead className={th}>Name</TableHead>
                  <TableHead className={th}>Description</TableHead>
                  <TableHead className={th}>Assignable to</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {appRoles.map((r) => (
                  <TableRow key={r.id} className={r.isEnabled ? undefined : 'text-muted-foreground'}>
                    <TableCell className={cn('px-3 font-mono text-sm', r.isPrivileged && r.allowedMemberTypes.includes('Application') && 'text-regulatory')}>
                      {r.isPrivileged && r.allowedMemberTypes.includes('Application') && <IconAlertTriangle className="mr-1.5 inline size-4 align-[-3px]" stroke={1.75} aria-label="High privilege" />}
                      {orDash(r.value)}
                      <div className="text-xs text-muted-foreground">{r.id}</div>
                    </TableCell>
                    <TableCell className="px-3 whitespace-normal">{r.displayName}</TableCell>
                    <TableCell className="px-3 whitespace-normal">{orDash(r.description)}</TableCell>
                    <TableCell className="px-3">{r.allowedMemberTypes.join(', ')}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
      <Section title="Delegated permission scopes" count={scopes.length}>
        {scopes.length === 0 ? (
          <p className="text-muted-foreground">No scopes defined.</p>
        ) : (
          <div className="glass overflow-hidden rounded-xl border">
            <Table>
              <TableHeader className="bg-shoulder">
                <TableRow className="hover:bg-transparent">
                  <TableHead className={th}>Value and ID</TableHead>
                  <TableHead className={th}>Consent</TableHead>
                  <TableHead className={th}>Admin consent description</TableHead>
                  <TableHead className={th}>User consent description</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {scopes.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell className="px-3 font-mono text-sm">
                      {p.value}
                      <div className="text-xs text-muted-foreground">{p.id}</div>
                    </TableCell>
                    <TableCell className="px-3">{p.type === 'Admin' ? <Badge variant="outline">Admin only</Badge> : 'Users and admins'}</TableCell>
                    <TableCell className="max-w-[40ch] px-3 whitespace-normal">{orDash(p.adminConsentDescription)}</TableCell>
                    <TableCell className="max-w-[40ch] px-3 whitespace-normal">{orDash(p.userConsentDescription)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
    </div>
  )
}

/** One panel per resource API; application and delegated permissions on separate, labelled rows. */
function RequiredPermissions({ items }: { items: RequiredResourceAccess[] }) {
  if (items.length === 0) return <p className="text-muted-foreground">This application requests no API permissions.</p>
  return (
    <div className="flex flex-col gap-4">
      {items.map((r) => {
        const app = r.permissions.filter((p) => p.type === 'Role')
        const delegated = r.permissions.filter((p) => p.type === 'Scope')
        return (
          <section key={r.resource.id ?? r.resource.displayName} className="glass overflow-hidden rounded-xl border">
            <header className="flex items-center gap-3 border-b bg-shoulder px-4 py-2.5">
              <ObjectLink value={r.resource} sub className="font-semibold" />
              <span className="ml-auto text-muted-foreground tabular-nums">{plural(r.permissions.length, 'permission')}</span>
            </header>
            <div className="divide-y">
              {app.length > 0 && <PermissionRow app values={app} />}
              {delegated.length > 0 && <PermissionRow app={false} values={delegated} />}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function PermissionRow({ app, values }: { app: boolean; values: Permission[] }) {
  const I = app ? IconServerBolt : IconUserShare
  return (
    <div className="grid items-start gap-x-6 gap-y-2 px-4 py-3 sm:grid-cols-[14rem_minmax(0,1fr)]">
      <div className="flex items-start gap-2.5">
        <I className={cn('mt-0.5 size-5 shrink-0', app ? 'text-warning' : 'text-muted-foreground')} stroke={1.75} aria-hidden />
        <div className="flex flex-col">
          <span className="font-medium">
            {app ? 'Application' : 'Delegated'} <span className="font-normal text-muted-foreground tabular-nums">{values.length}</span>
          </span>
          <span className="text-sm text-muted-foreground">{app ? 'Acts as the app, no user' : 'Acts on behalf of a user'}</span>
        </div>
      </div>
      <ul className="flex flex-wrap gap-1.5 pt-0.5">
        {[...values]
          .sort((a, b) => Number(app && b.isPrivileged) - Number(app && a.isPrivileged))
          .map((p) => (
            <li key={p.value}>
              <PermissionChip p={p} app={app} />
            </li>
          ))}
      </ul>
    </div>
  )
}

function Metadata({ items }: { items: MetadataEntry[] }) {
  return (
    <div className="flex flex-col gap-4">
      {items.map((m) => (
        <Section key={m.key} title={m.key}>
          <JsonView value={m.value} />
        </Section>
      ))}
    </div>
  )
}
