import type { ColumnDef } from '@tanstack/react-table'
import { IconAlertTriangle, IconArrowRight, IconClock, IconExternalLink, IconFilter, IconInfinity, IconRefresh } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable } from '@/components/data-table'
import { ObjectLink } from '@/components/object-link'
import { Section } from '@/components/object-page'
import { AzureScope, parseAzureScope } from '@/components/azure-scope'
import { ApprovalBadge, Flag, KindBadge } from '@/components/badges'
import { orDash } from '@/components/page-parts'
import { useApi } from '@/api/client'
import type { AccessPackagePolicyRow, AzureRoleAssignmentRow, PimAssignmentRow, PimSubject } from '@/api/types'
import { fmtDate, plural } from '@/lib/format'
import { cn } from '@/lib/utils'

const via = (v: { via: AzureRoleAssignmentRow['via'] }) => (v.via ? <ObjectLink value={v.via} wrap className="max-w-full whitespace-normal" /> : <span className="text-muted-foreground">Direct</span>)

function Explained({ tip, children }: { tip: React.ReactNode; children: React.ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  )
}

/** No end date: standing access, shown as risky. */
function Permanent({ label = 'Permanent' }: { label?: string }) {
  return (
    <Explained tip="No end date. Nothing removes this access over time.">
      <span className="inline-flex items-center gap-1.5 text-regulatory">
        <IconInfinity className="size-4" stroke={1.75} aria-hidden />
        {label}
      </span>
    </Explained>
  )
}

const DAY = 86_400_000

/** Start to end, with a bar for the time already used and the days left. */
function Duration({ start, end }: { start: string | null; end: string | null }) {
  if (!end) return <Permanent />
  const from = start ? new Date(start).getTime() : NaN
  const to = new Date(end).getTime()
  const now = Date.now()
  const left = Math.ceil((to - now) / DAY)
  const used = left <= 0 ? 1 : from < to ? Math.min(1, Math.max(0, (now - from) / (to - from))) : 0
  return (
    <span className="inline-flex items-center gap-3 tabular-nums">
      <span className="inline-flex items-center gap-1.5">
        {fmtDate(start) ?? '…'}
        <IconArrowRight className="size-3.5 text-muted-foreground" stroke={1.75} aria-label="to" />
        {fmtDate(end)}
      </span>
      <span className="inline-flex items-center gap-2 text-muted-foreground">
        <span className="h-1 w-16 overflow-hidden rounded-full bg-muted" aria-hidden>
          <span className="block h-full rounded-full bg-muted-foreground" style={{ width: `${used * 100}%` }} />
        </span>
        {left > 0 ? `${plural(left, 'day')} left` : 'Ended'}
      </span>
    </span>
  )
}

const HIGH_IMPACT_AZURE = new Set(['Owner', 'User Access Administrator', 'Contributor'])
const BREADTH: Record<string, number> = { Root: 4, 'Management group': 4, Subscription: 3, 'Resource group': 2, Resource: 1 }
const BAR_HEIGHT = ['h-1.5', 'h-2.5', 'h-3.5', 'h-4.5']

/** Signal-style bars: four for a management group, one for a single resource. */
function ScopeBreadth({ scope }: { scope: string }) {
  const { type } = parseAzureScope(scope)
  const n = BREADTH[type] ?? 1
  return (
    <Explained tip={`${type}: ${n >= 3 ? 'covers everything below it' : n === 2 ? 'covers the resources in this group' : 'one resource'}`}>
      <span className="inline-flex shrink-0 items-end gap-0.5" role="img" aria-label={`Scope breadth ${n} of 4`}>
        {BAR_HEIGHT.map((h, i) => (
          <span key={h} className={cn('w-1 rounded-[1px]', h, i < n ? 'bg-foreground' : 'bg-muted')} />
        ))}
      </span>
    </Explained>
  )
}

export function AzureRolesTable({ principalId }: { principalId: string }) {
  const columns: ColumnDef<AzureRoleAssignmentRow>[] = [
    {
      id: 'role',
      header: 'Role',
      meta: { filter: 'role' },
      cell: ({ row }) => {
        const r = row.original.role
        const name = <span>{r.displayName}</span>
        return (
          <span className="inline-flex items-center gap-2">
            {r.description ? <Explained tip={r.description}>{name}</Explained> : name}
            {HIGH_IMPACT_AZURE.has(r.displayName) && (
              <Explained tip="High impact: can change resources or grant access to them">
                <IconAlertTriangle className="size-4 text-regulatory" stroke={1.75} aria-label="High impact" />
              </Explained>
            )}
            {!r.isBuiltIn && <Badge variant="outline">Custom</Badge>}
            {row.original.conditional && (
              <Explained tip="Conditional: an attribute condition limits what this assignment allows">
                <IconFilter className="size-4 text-warning" stroke={1.75} aria-label="Conditional" />
              </Explained>
            )}
          </span>
        )
      },
    },
    { id: 'kind', header: 'Assignment', meta: { filter: 'kind', noCopy: true }, cell: ({ row }) => <KindBadge kind={row.original.kind} /> },
    {
      id: 'scope',
      header: 'Scope',
      // The breadth bars carry the scope level (with a tooltip), so the label is hidden.
      meta: { filter: 'scopeType', noCopy: true, className: 'max-w-[22rem]' },
      cell: ({ row }) => (
        <span className="inline-flex min-w-0 items-center gap-2.5">
          <ScopeBreadth scope={row.original.scope} />
          <AzureScope scope={row.original.scope} hideType />
        </span>
      ),
    },
    { id: 'via', header: 'Through', meta: { filter: 'viaGroup', className: 'max-w-44' }, cell: ({ row }) => via(row.original) },
    { id: 'conditional', header: 'Conditional', meta: { filter: 'conditional', defaultHidden: true, noCopy: true }, cell: ({ row }) => <Flag value={row.original.conditional} /> },
    { id: 'scopePath', header: 'Scope path', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.scope },
  ]
  return <DataTable route="/api/azure-role-assignments" query={{ principalId, transitive: true }} columns={columns} resource="azure-role-assignments" noun="Azure role assignment" hideSearch />
}

const RESOURCE_TYPE: Record<PimAssignmentRow['resourceType'], string> = { directoryRole: 'Directory role', group: 'Group', other: 'Other' }

export function PimAssignmentsTable({ principalId }: { principalId: string }) {
  const columns: ColumnDef<PimAssignmentRow>[] = [
    {
      id: 'resource',
      header: 'Role',
      meta: { filter: 'role' },
      cell: ({ row }) => (
        <span className="inline-flex min-w-0 items-center gap-1.5">
          <ObjectLink value={row.original.resource} />
          {row.original.role !== row.original.resource.displayName && <span className="text-muted-foreground">as {row.original.role}</span>}
        </span>
      ),
    },
    { id: 'kind', header: 'Assignment', meta: { filter: 'kind', noCopy: true }, cell: ({ row }) => <KindBadge kind={row.original.kind} /> },
    { id: 'approval', header: 'Activation', meta: { filter: 'approvalRequired', noCopy: true }, cell: ({ row }) => (row.original.kind === 'eligible' ? <ApprovalBadge required={row.original.approvalRequired} /> : null) },
    { id: 'duration', header: 'Duration', meta: { filter: 'permanent', noCopy: true }, cell: ({ row }) => <Duration start={row.original.startDateTime} end={row.original.endDateTime} /> },
    { id: 'via', header: 'Through', cell: ({ row }) => via(row.original) },
    { id: 'resourceType', header: 'Resource type', meta: { filter: 'resourceType', defaultHidden: true }, cell: ({ row }) => RESOURCE_TYPE[row.original.resourceType] },
    { id: 'start', header: 'Start', meta: { defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => orDash(fmtDate(row.original.startDateTime)) },
    { id: 'end', header: 'End', meta: { defaultHidden: true, className: 'tabular-nums' }, cell: ({ row }) => orDash(fmtDate(row.original.endDateTime)) },
  ]
  return <DataTable route="/api/pim-assignments" query={{ principalId, transitive: true }} columns={columns} resource="pim-assignments" noun="PIM assignment" hideSearch />
}

function GrantedResource({ r }: { r: AccessPackagePolicyRow['resources'][number] }) {
  const url = r.resource.type === 'value' && /^https?:\/\//.test(r.resource.displayName) ? r.resource.displayName : null
  return (
    <li className="flex min-w-0 items-center gap-1.5">
      {url ? (
        <Explained tip={`${r.kind}: ${url}`}>
          <a href={url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1.5 underline-offset-4 hover:underline">
            <IconExternalLink className="size-4 shrink-0 text-muted-foreground" stroke={1.75} aria-hidden />
            <span className="max-w-[20ch] truncate">{url.replace(/^https?:\/\//, '')}</span>
          </a>
        </Explained>
      ) : (
        <ObjectLink value={r.resource} />
      )}
      {r.role && <span className="shrink-0 text-muted-foreground">as {r.role}</span>}
    </li>
  )
}

export function AccessPackagesTable({ userId }: { userId: string }) {
  const columns: ColumnDef<AccessPackagePolicyRow>[] = [
    {
      id: 'package',
      header: 'Access package',
      meta: { filter: 'packageName', className: 'min-w-[18ch] max-w-[32ch] whitespace-normal' },
      cell: ({ row }) => {
        const name = <span className="font-semibold">{row.original.packageName}</span>
        return (
          <div className="flex flex-col items-start whitespace-normal">
            {row.original.packageDescription ? <Explained tip={row.original.packageDescription}>{name}</Explained> : name}
            <span className="text-muted-foreground">{row.original.policyName}</span>
            {/* Who can request it, kept here instead of a column so the table fits next to the summary. */}
            <span className="inline-flex max-w-full items-center gap-1.5">
              <span className="shrink-0 text-muted-foreground">Open to</span>
              <ObjectLink value={row.original.via} />
            </span>
          </div>
        )
      },
    },
    {
      id: 'resources',
      header: 'Grants',
      meta: { noCopy: true, className: 'whitespace-normal' },
      cell: ({ row }) => (
        <ul className="flex flex-col gap-0.5">
          {row.original.resources.map((r, i) => (
            <GrantedResource key={i} r={r} />
          ))}
        </ul>
      ),
    },
    {
      id: 'approval',
      header: 'Approval',
      meta: { filter: 'approvalRequired', noCopy: true, className: 'whitespace-normal' },
      cell: ({ row }) => (
        <div className="flex flex-col items-start gap-1">
          <ApprovalBadge required={row.original.approvalRequired} />
          {row.original.approvers.map((a) => (
            <span key={a} className="text-sm text-muted-foreground">
              {a}
            </span>
          ))}
        </div>
      ),
    },
    {
      id: 'duration',
      header: 'Duration',
      meta: { filter: 'renewable', noCopy: true },
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-2">
          {row.original.durationDays ? (
            <span className="inline-flex items-center gap-1.5 tabular-nums">
              <IconClock className="size-4 text-muted-foreground" stroke={1.75} aria-hidden />
              {plural(row.original.durationDays, 'day')}
            </span>
          ) : (
            <Permanent label="No expiry" />
          )}
          {row.original.renewable && (
            <Explained tip="Renewable: the user can extend it before it ends">
              <IconRefresh className="size-4 text-muted-foreground" stroke={1.75} aria-label="Renewable" />
            </Explained>
          )}
        </span>
      ),
    },
    { id: 'description', header: 'Description', meta: { defaultHidden: true, className: 'max-w-[40ch] whitespace-normal' }, cell: ({ row }) => orDash(row.original.packageDescription) },
  ]
  return <DataTable route="/api/access-package-policies" query={{ userId }} columns={columns} resource="access-package-policies" noun="access package" hideSearch />
}

function Subjects({ items }: { items: PimSubject[] }) {
  if (items.length === 0) return <p className="text-muted-foreground">None.</p>
  return (
    <div className="glass overflow-hidden rounded-xl border">
      <Table>
        <TableHeader className="bg-shoulder">
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-full px-3 font-semibold text-ink">Principal</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Assignment</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Duration</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((s) => (
            <TableRow key={`${s.subject.id}-${s.kind}`}>
              <TableCell className="max-w-0 px-3">
                <ObjectLink value={s.subject} sub className="max-w-full [&>span:first-of-type]:shrink-0" />
              </TableCell>
              <TableCell className="px-3">
                <KindBadge kind={s.kind} />
              </TableCell>
              <TableCell className="px-3">
                <Duration start={s.startDateTime} end={s.endDateTime} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** PIM for groups: who can activate membership or ownership of this group. */
export function GroupPimView({ groupId }: { groupId: string }) {
  const { data, isLoading } = useApi('/api/groups/{id}/pim', { path: { id: groupId } })
  if (isLoading) return <Skeleton className="h-32 w-full" />
  if (!data) return <p className="text-muted-foreground">This group is not managed by PIM.</p>
  return (
    <div className="flex flex-col gap-6">
      <p className="text-muted-foreground">Managed by PIM since {orDash(fmtDate(data.onboardedDateTime))}.</p>
      <Section title="Members" count={data.members.length} aside={<span className="inline-flex items-center gap-2">Activation <ApprovalBadge required={data.memberApprovalRequired} /></span>}>
        <Subjects items={data.members} />
      </Section>
      <Section title="Owners" count={data.owners.length} aside={<span className="inline-flex items-center gap-2">Activation <ApprovalBadge required={data.ownerApprovalRequired} /></span>}>
        <Subjects items={data.owners} />
      </Section>
    </div>
  )
}
