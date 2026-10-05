import type { ColumnDef } from '@tanstack/react-table'
import { IconBolt, IconClockX, IconUsersGroup } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable } from '@/components/data-table'
import { ObjectLink, TYPE_LABEL } from '@/components/object-link'
import { ListPage, orDash } from '@/components/page-parts'
import type { AppRoleAssignmentQuery, AppRoleAssignmentRow, OAuth2GrantQuery, OAuth2GrantRow } from '@/api/types'
import { fmtDate } from '@/lib/format'

interface AppRoleAssignmentsTableProps {
  query?: Partial<AppRoleAssignmentQuery>
  hidePrincipal?: boolean
  hideResource?: boolean
}

const DEFAULT_ACCESS = '00000000-0000-0000-0000-000000000000'

function RoleValue({ row }: { row: AppRoleAssignmentRow }) {
  if (row.appRoleId === DEFAULT_ACCESS) return <span className="text-muted-foreground">Default access</span>
  if (row.principal.type !== 'servicePrincipal') return <Badge variant="secondary" className="font-mono font-normal">{row.value}</Badge>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="regulatory" className="font-mono font-normal">
          <IconBolt stroke={1.75} aria-label="Application permission" />
          {row.value}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Application permission. The app uses it on its own, without a signed-in user.</TooltipContent>
    </Tooltip>
  )
}

export function AppRoleAssignmentsTable({ query, hidePrincipal, hideResource }: AppRoleAssignmentsTableProps) {
  const columns: ColumnDef<AppRoleAssignmentRow>[] = [
    // The principal type is the glyph in front of the name.
    ...(hidePrincipal ? [] : [{ id: 'principal', header: 'Principal', meta: { sort: 'principal', filter: 'principalType' }, cell: ({ row }) => <ObjectLink value={row.original.principal} /> } as ColumnDef<AppRoleAssignmentRow>]),
    ...(hidePrincipal ? [] : [{ id: 'principalType', header: 'Principal type', meta: { defaultHidden: true }, cell: ({ row }) => TYPE_LABEL[row.original.principal.type] } as ColumnDef<AppRoleAssignmentRow>]),
    ...(hideResource ? [] : [{ id: 'resource', header: 'Application', meta: { sort: 'resource', filter: 'resource' }, cell: ({ row }) => <ObjectLink value={row.original.resource} /> } as ColumnDef<AppRoleAssignmentRow>]),
    { id: 'value', header: 'Role', meta: { filter: 'value' }, cell: ({ row }) => <RoleValue row={row.original} /> },
    // The copy wrapper truncates, so the text opts back into wrapping.
    { id: 'description', header: 'Description', meta: { className: 'max-w-[36ch]' }, cell: ({ row }) => <span className="whitespace-normal">{orDash(row.original.description)}</span> },
    { id: 'created', header: 'Assigned', meta: { sort: 'createdDateTime', filter: 'createdDateTime', className: 'tabular-nums' }, cell: ({ row }) => orDash(fmtDate(row.original.createdDateTime)) },
    { id: 'appRoleId', header: 'App role ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.appRoleId },
    { id: 'id', header: 'Assignment ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.id },
  ]
  return <DataTable route="/api/app-role-assignments" query={query} columns={columns} resource="app-role-assignments" searchPlaceholder="Search principal, application or role" noun="app role assignment" />
}

export function AppRoleAssignmentsPage() {
  return (
    <ListPage
      title="App role assignments"
      description="Application roles assigned to users, groups and service principals. Roles held by service principals are application permissions: they act without a signed-in user."
    >
      <AppRoleAssignmentsTable />
    </ListPage>
  )
}

function Scopes({ scopes, privileged }: { scopes: string[]; privileged: string[] }) {
  const risky = (s: string) => privileged.includes(s)
  const sorted = [...scopes].sort((a, b) => Number(risky(b)) - Number(risky(a)))
  return (
    <span className="inline-flex flex-wrap gap-1">
      {sorted.map((s) =>
        risky(s) ? (
          <Tooltip key={s}>
            <TooltipTrigger asChild>
              <Badge variant="regulatory" className="font-mono font-normal">
                {s}
              </Badge>
            </TooltipTrigger>
            <TooltipContent>High impact scope</TooltipContent>
          </Tooltip>
        ) : (
          <Badge key={s} variant="secondary" className="font-mono font-normal">
            {s}
          </Badge>
        ),
      ).flatMap((b) => [b, ' '])}
    </span>
  )
}

const expired = (value: string | null) => !!value && new Date(value).getTime() <= Date.now()

function Expiry({ value }: { value: string | null }) {
  if (!expired(value)) return <span className="tabular-nums">{orDash(fmtDate(value))}</span>
  return (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground tabular-nums">
      <IconClockX className="size-4" stroke={1.75} aria-hidden />
      {fmtDate(value)}
      <span>Expired</span>
    </span>
  )
}

export function OAuth2GrantsTable({ query }: { query?: Partial<OAuth2GrantQuery> }) {
  const columns: ColumnDef<OAuth2GrantRow>[] = [
    {
      id: 'principal',
      header: 'Consented for',
      meta: { filter: 'consentType' },
      cell: ({ row }) =>
        row.original.principal ? (
          <ObjectLink value={row.original.principal} />
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge variant="warning">
                <IconUsersGroup stroke={1.75} aria-hidden />
                All users
              </Badge>
            </TooltipTrigger>
            <TooltipContent>Admin consent. Applies to every user who signs in to the app.</TooltipContent>
          </Tooltip>
        ),
    },
    {
      id: 'consentType',
      header: 'Consent type',
      meta: { defaultHidden: true },
      cell: ({ row }) => (row.original.consentType === 'AllPrincipals' ? 'All users (admin consent)' : 'One user'),
    },
    {
      id: 'client',
      header: 'Granted to',
      meta: { sort: 'client', filter: 'client' },
      // The expiry date is rarely useful, so it only shows here once it has passed.
      cell: ({ row }) => (
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <ObjectLink value={row.original.client} />
          {expired(row.original.expiryTime) && (
            <Tooltip>
              <TooltipTrigger asChild>
                <IconClockX className="size-4 shrink-0 text-muted-foreground" stroke={1.75} aria-label="Expired" />
              </TooltipTrigger>
              <TooltipContent>Grant expired on {fmtDate(row.original.expiryTime)}</TooltipContent>
            </Tooltip>
          )}
        </span>
      ),
    },
    { id: 'resource', header: 'On API', meta: { sort: 'resource', filter: 'resource' }, cell: ({ row }) => <ObjectLink value={row.original.resource} /> },
    { id: 'scopes', header: 'Scopes', meta: { filter: 'scope', className: 'max-w-[60ch] whitespace-normal' }, cell: ({ row }) => <Scopes scopes={row.original.scopes} privileged={row.original.privilegedScopes} /> },
    { id: 'expiry', header: 'Expires', meta: { filter: 'expiryTime', defaultHidden: true }, cell: ({ row }) => <Expiry value={row.original.expiryTime} /> },
    { id: 'id', header: 'Grant ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.id },
  ]
  return (
    <DataTable
      route="/api/oauth2-grants"
      query={query}
      columns={columns}
      resource="oauth2-grants"
      searchPlaceholder="Search application, user or scope"
      noun="grant"
    />
  )
}

export function OAuth2GrantsPage() {
  return (
    <ListPage
      title="OAuth2 grants"
      description="Delegated permissions consented to applications, either by an administrator for all users or by individual users for themselves. The app can use these scopes whenever a covered user signs in to it."
    >
      <OAuth2GrantsTable />
    </ListPage>
  )
}
