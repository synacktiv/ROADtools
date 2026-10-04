import { useMemo } from 'react'
import { useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import { IconClockHour4, IconPencilCog, IconShieldBolt, IconWorld } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable, type FilterDef } from '@/components/data-table'
import { ObjectLink, TYPE_LABEL, TypeGlyph } from '@/components/object-link'
import { ObjectPage } from '@/components/object-page'
import { MfaMethods } from '@/components/mfa-methods'
import { Flag, flag, KindBadge, SourceIcon } from '@/components/badges'
import { ListPage, Dash, orDash, toRef } from '@/components/page-parts'
import { ObjectPolicies } from '@/components/policy-match-list'
import { useApi } from '@/api/client'
import type { ObjectType, RoleAssignmentQuery, RoleAssignmentRow, RoleQuery, RoleRow } from '@/api/types'
import { useSettings } from '@/lib/settings'
import { useSetCrumb } from '@/lib/crumb'
import { cn } from '@/lib/utils'

function PrivilegedMark() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label="Privileged role" className="inline-flex shrink-0 items-center text-regulatory">
          <IconShieldBolt className="size-4" stroke={1.75} aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent>Privileged role: holders can take control of the tenant</TooltipContent>
    </Tooltip>
  )
}

function CustomMark() {
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-sm text-muted-foreground">
      <IconPencilCog className="size-3.5" stroke={1.75} aria-hidden />
      Custom
    </span>
  )
}

/** Two-segment bar: active in the foreground colour, eligible (PIM) in warning. `scale` is the share of the track it fills. */
function SplitBar({ active, eligible, scale = 1, className }: { active: number; eligible: number; scale?: number; className?: string }) {
  return (
    <span className={cn('flex h-1.5 gap-px overflow-hidden rounded-full', className)} style={{ width: `${scale * 100}%` }} aria-hidden>
      {active > 0 && <span className="rounded-full bg-foreground/75" style={{ flexGrow: active }} />}
      {eligible > 0 && <span className="rounded-full bg-warning/85" style={{ flexGrow: eligible }} />}
    </span>
  )
}

function EligibleCount({ n }: { n: number }) {
  return (
    <span className="inline-flex items-center gap-1 text-warning tabular-nums">
      <IconClockHour4 className="size-3.5" stroke={1.75} aria-hidden />
      {n}
    </span>
  )
}

const roleColumns: ColumnDef<RoleRow>[] = [
  {
    id: 'displayName',
    header: 'Role',
    meta: { sort: 'displayName', filter: 'displayName' },
    cell: ({ row }) => (
      <span className="flex min-w-0 items-center gap-2">
        <ObjectLink value={toRef('role', row.original)} />
        {row.original.isPrivileged && <PrivilegedMark />}
        {!row.original.isBuiltIn && <CustomMark />}
      </span>
    ),
  },
  {
    id: 'assignments',
    header: 'Assignments',
    meta: { sort: 'activeCount', filter: 'activeCount', className: 'w-72', noCopy: true },
    cell: ({ row, table }) => {
      const { activeCount: a, eligibleCount: e } = row.original
      if (!a && !e) return <Dash />
      const max = Math.max(...table.getCoreRowModel().rows.map((r) => r.original.activeCount + r.original.eligibleCount))
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={0} className="grid grid-cols-[1.5rem_2.5rem_1fr] items-center gap-2">
              <span className="text-right tabular-nums">{a || <Dash />}</span>
              <span>{e > 0 && <EligibleCount n={e} />}</span>
              <SplitBar active={a} eligible={e} scale={(a + e) / max} />
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {a} active, {e} eligible
          </TooltipContent>
        </Tooltip>
      )
    },
  },
  { id: 'description', header: 'Description', meta: { className: 'max-w-[60ch] text-muted-foreground' }, cell: ({ row }) => orDash(row.original.description) },
  { id: 'eligibleCount', header: 'Eligible', meta: { sort: 'eligibleCount', filter: 'eligibleCount', defaultHidden: true }, cell: ({ row }) => row.original.eligibleCount },
  { id: 'isBuiltIn', header: 'Built-in', meta: { filter: 'isBuiltIn', defaultHidden: true, noCopy: true }, cell: ({ row }) => <Flag value={row.original.isBuiltIn} /> },
  { id: 'templateId', header: 'Template ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.templateId },
]

export function RolesTable({ query }: { query?: Partial<RoleQuery> }) {
  return <DataTable route="/api/roles" query={query} columns={roleColumns} resource="roles" noun="role" defaultSort={{ sort: 'activeCount', order: 'desc' }} />
}

export function RolesPage() {
  return (
    <ListPage title="Directory roles" description="Entra ID roles with their active and eligible (PIM) assignments. Open a role to see who holds it, directly or through a group.">
      <RolesTable />
    </ListPage>
  )
}

interface RoleAssignmentsTableProps {
  query: Partial<RoleAssignmentQuery>
  /** On a principal's page, the principal column is redundant. */
  hidePrincipal?: boolean
  hideRole?: boolean
}

export function RoleAssignmentsTable({ query, hidePrincipal, hideRole }: RoleAssignmentsTableProps) {
  const { mfaColumns } = useSettings()
  // One cached page of the assigned roles gives the privileged mark for the role column.
  const { data: assigned } = useApi('/api/roles', { query: { hasAssignments: true, page_size: 500 } }, !hideRole)
  const privileged = useMemo(() => new Set(assigned?.items.filter((r) => r.isPrivileged).map((r) => r.id)), [assigned])
  const columns: ColumnDef<RoleAssignmentRow>[] = [
    ...(hideRole
      ? []
      : [
          {
            id: 'role',
            header: 'Role',
            meta: { filter: 'role' },
            cell: ({ row }) => (
              <span className="flex min-w-0 items-center gap-2">
                <ObjectLink value={row.original.role} />
                {privileged.has(row.original.role.id ?? '') && <PrivilegedMark />}
              </span>
            ),
          } as ColumnDef<RoleAssignmentRow>,
        ]),
    // The principal type is the glyph in ObjectLink (and the header filter); disabled sits next to the name.
    ...(hidePrincipal
      ? []
      : [
          {
            id: 'principal',
            header: 'Principal',
            meta: { sort: 'principal', filter: 'principalType', className: 'max-w-80' },
            cell: ({ row }) => (
              <span className="flex min-w-0 items-center gap-2">
                <ObjectLink value={row.original.principal} sub />
                {row.original.principalEnabled === false && (
                  <Badge variant="regulatory" className="shrink-0">
                    Disabled
                  </Badge>
                )}
              </span>
            ),
          } as ColumnDef<RoleAssignmentRow>,
        ]),
    { id: 'kind', header: 'Assignment', meta: { filter: 'kind', noCopy: true }, cell: ({ row }) => <KindBadge kind={row.original.kind} /> },
    { id: 'scope', header: 'Scope', meta: { filter: 'scopeType' }, cell: ({ row }) => <ObjectLink value={row.original.scope} /> },
    {
      id: 'via',
      header: 'Through',
      meta: { filter: 'viaGroup' },
      cell: ({ row }) => (row.original.via ? <ObjectLink value={row.original.via} /> : <span className="text-muted-foreground">Direct</span>),
    },
    ...(hidePrincipal
      ? []
      : ([
          { id: 'source', header: 'Source', meta: { noCopy: true }, cell: ({ row }) => (row.original.principal.type === 'user' ? <SourceIcon dirSync={row.original.principalDirSync} withLabel={false} /> : null) },
          ...(mfaColumns ? [{ id: 'mfa', header: 'MFA', meta: { noCopy: true }, cell: ({ row }) => <MfaMethods mfa={row.original.principalMfa} /> } as ColumnDef<RoleAssignmentRow>] : []),
          {
            id: 'principalEnabled',
            header: 'Principal enabled',
            meta: { filter: 'principalEnabled', defaultHidden: true, noCopy: true },
            cell: ({ row }) => flag(row.original.principalEnabled, false),
          },
        ] as ColumnDef<RoleAssignmentRow>[])),
    { id: 'id', header: 'Assignment ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.id },
  ]
  const filters: FilterDef[] = []
  if (query.roleId) filters.push({ kind: 'toggle', key: 'expandGroups', label: 'List members of assigned groups' })
  return <DataTable route="/api/role-assignments" query={query} columns={columns} filters={filters} resource="role-assignments" noun="role assignment" hideSearch={!!hidePrincipal} />
}

/** Active / eligible counts with a full-width split bar, for the summary panel. */
function AssignmentSummary({ active, eligible }: { active: number; eligible: number }) {
  return (
    <div className="flex flex-col gap-2 pt-0.5">
      <div className="flex items-center gap-4 tabular-nums">
        <span>
          <span className="font-semibold">{active}</span> <span className="text-muted-foreground">active</span>
        </span>
        <span className={cn('inline-flex items-center gap-1', eligible ? 'text-warning' : 'text-muted-foreground')}>
          <IconClockHour4 className="size-3.5" stroke={1.75} aria-hidden />
          <span className="font-semibold">{eligible}</span> eligible
        </span>
      </div>
      {active + eligible > 0 && <SplitBar active={active} eligible={eligible} />}
    </div>
  )
}

type Tally = { key: string; label: string; icon: React.ReactNode; active: number; eligible: number }

function tally(rows: RoleAssignmentRow[], buckets: Omit<Tally, 'active' | 'eligible'>[], keyOf: (r: RoleAssignmentRow) => string): Tally[] {
  return buckets.map((b) => {
    const mine = rows.filter((r) => keyOf(r) === b.key)
    return { ...b, active: mine.filter((r) => r.kind === 'active').length, eligible: mine.filter((r) => r.kind === 'eligible').length }
  })
}

const glyph = (t: ObjectType) => <TypeGlyph type={t} className="text-muted-foreground" />

function Breakdown({ title, items, total }: { title: string; items: Tally[]; total: number }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-muted-foreground">{title}</h3>
      <ul className="flex flex-col gap-1.5">
        {items.map((t) => {
          const n = t.active + t.eligible
          return (
            <li key={t.key} className={cn('grid grid-cols-[minmax(0,11rem)_1fr_1.5rem] items-center gap-3', !n && 'text-muted-foreground')}>
              <span className="flex min-w-0 items-center gap-2">
                {t.icon}
                <span className="truncate">{t.label}</span>
              </span>
              <SplitBar active={t.active} eligible={t.eligible} scale={total ? n / total : 0} />
              <span className="text-right tabular-nums">{n}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** Who holds the role and where, from the direct assignments (groups are not expanded). */
function HolderBreakdown({ roleId, active, eligible }: { roleId: string; active: number; eligible: number }) {
  // ponytail: one large page; a real backend should return these counts with the role.
  const { data } = useApi('/api/role-assignments', { query: { roleId, page_size: 1000 } })
  const rows = data?.items ?? []
  return (
    <Card className="gap-4 py-4">
      <CardHeader className="px-4">
        <CardTitle>Holders</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5 px-4 text-base">
        <AssignmentSummary active={active} eligible={eligible} />
        {!data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            <Breakdown
              title="By principal type"
              total={rows.length}
              items={tally(
                rows,
                (['user', 'group', 'servicePrincipal'] as const).map((t) => ({ key: t, label: `${TYPE_LABEL[t]}s`, icon: glyph(t) })),
                (r) => r.principal.type,
              )}
            />
            <Breakdown
              title="By scope"
              total={rows.length}
              items={tally(
                rows,
                [
                  { key: 'keyword', label: 'Directory', icon: <IconWorld className="size-4 shrink-0 text-muted-foreground" stroke={1.75} aria-hidden /> },
                  { key: 'administrativeUnit', label: 'Administrative units', icon: glyph('administrativeUnit') },
                  { key: 'application', label: 'Applications', icon: glyph('application') },
                ],
                (r) => r.scope.type,
              )}
            />
          </>
        )}
      </CardContent>
    </Card>
  )
}

export function RolePage() {
  const { id = '' } = useParams()
  const { data: r, isLoading, error } = useApi('/api/roles/{id}', { path: { id } })
  useSetCrumb(r?.displayName)
  const holders = r ? r.activeCount + r.eligibleCount : 0
  return (
    <ObjectPage
      type="role"
      title={r?.displayName}
      id={id}
      loading={isLoading}
      error={error}
      badges={
        r && (
          <>
            {r.isPrivileged && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant="regulatory" tabIndex={0}>
                    <IconShieldBolt stroke={1.75} /> Privileged
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>Tier 0: holders can take control of the tenant</TooltipContent>
              </Tooltip>
            )}
            {!r.isBuiltIn && (
              <Badge variant="outline">
                <IconPencilCog stroke={1.75} /> Custom
              </Badge>
            )}
          </>
        )
      }
      raw={r?.raw}
      summary={
        r && [
          ['Description', r.description],
          ['Role definition ID', r.id, { mono: true, copy: r.id }],
          // Built-in roles use the template ID as their ID: show it only when it differs.
          ['Template ID', r.templateId !== r.id ? r.templateId : null, { mono: true, copy: r.templateId }],
        ]
      }
      aside={holders > 0 && r && <HolderBreakdown roleId={id} active={r.activeCount} eligible={r.eligibleCount} />}
      tabs={[
        {
          key: 'assignments',
          label: 'Assignments',
          count: r && r.activeCount + r.eligibleCount,
          render: () => <RoleAssignmentsTable query={{ roleId: id }} hideRole />,
        },
        {
          key: 'actions',
          label: 'Allowed actions',
          count: r?.allowedResourceActions.length,
          render: () =>
            r && (
              <ul className="glass columns-1 gap-8 rounded-xl border p-4 font-mono text-sm leading-7 lg:columns-2">
                {r.allowedResourceActions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            ),
        },
        { key: 'policies', label: 'Policies', render: () => <ObjectPolicies type="role" id={id} /> },
      ]}
    />
  )
}
