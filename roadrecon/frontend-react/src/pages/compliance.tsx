import { Link, useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import { IconClipboardCheck } from '@tabler/icons-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { DataTable } from '@/components/data-table'
import { ObjectLink } from '@/components/object-link'
import { ObjectPage } from '@/components/object-page'
import { PropertyList, type Property } from '@/components/property-list'
import { JsonView } from '@/components/json-view'
import { Flag, Setting, flag } from '@/components/badges'
import { ListPage, orDash } from '@/components/page-parts'
import { useApi } from '@/api/client'
import type { CompliancePolicyDetail, CompliancePolicyRow, ObjectRef } from '@/api/types'
import { camelBreaks, fmtDate, fmtNumber, plural } from '@/lib/format'
import { useSetCrumb } from '@/lib/crumb'

const KIND = { label: 'Compliance policy', icon: IconClipboardCheck }

/** Hours before a non-compliant device is marked as such; null when the policy has no block action. */
const grace = (h: number | null) => (h === null ? null : h === 0 ? 'Immediately' : h % 24 ? `${fmtNumber(h)} h` : plural(h / 24, 'day'))

/** Groups or All users / All devices; null when empty so cells show a dash and property rows are skipped. */
const refs = (items: ObjectRef[]) =>
  items.length === 0 ? null : (
    <span className="flex flex-col gap-1">
      {items.map((r, i) => (
        <ObjectLink key={r.id ?? i} value={r} wrap className="max-w-full" />
      ))}
    </span>
  )

/** Not a directory object, so no ObjectLink: same look, compliance icon. */
function PolicyLink({ p }: { p: CompliancePolicyRow }) {
  return (
    <Link
      to={`/device-compliance/${encodeURIComponent(p.id)}`}
      className="inline-flex min-w-0 items-center gap-1.5 rounded-sm decoration-muted-foreground/50 underline-offset-4 hover:underline"
    >
      <IconClipboardCheck aria-hidden stroke={1.75} className="size-4 shrink-0 text-muted-foreground" />
      <span data-copy className="min-w-0 truncate">
        {p.displayName}
      </span>
    </Link>
  )
}

const columns: ColumnDef<CompliancePolicyRow>[] = [
  { id: 'displayName', header: 'Policy', meta: { sort: 'displayName', filter: 'displayName' }, enableHiding: false, cell: ({ row }) => <PolicyLink p={row.original} /> },
  { id: 'platform', header: 'Platform', meta: { sort: 'platform', filter: 'platform' }, cell: ({ row }) => row.original.platform },
  { id: 'assignments', header: 'Assigned to', meta: { noCopy: true, className: 'max-w-80 whitespace-normal' }, cell: ({ row }) => orDash(refs(row.original.assignments)) },
  { id: 'exclusions', header: 'Excluded', meta: { noCopy: true, className: 'max-w-80 whitespace-normal' }, cell: ({ row }) => orDash(refs(row.original.exclusions)) },
  {
    id: 'grace',
    header: 'Marked non-compliant',
    meta: { sort: 'gracePeriodHours', filter: 'gracePeriodHours', className: 'tabular-nums' },
    cell: ({ row }) => orDash(grace(row.original.gracePeriodHours)),
  },
  { id: 'modified', header: 'Modified', meta: { sort: 'lastModifiedDateTime', filter: 'lastModifiedDateTime', className: 'tabular-nums' }, cell: ({ row }) => orDash(fmtDate(row.original.lastModifiedDateTime)) },
  { id: 'id', header: 'Policy ID', meta: { defaultHidden: true, className: 'font-mono text-sm' }, cell: ({ row }) => row.original.id },
]

function TenantSettings() {
  const { data: s } = useApi('/api/device-compliance/settings')
  if (!s) return null
  return (
    <Card className="max-w-4xl">
      <CardHeader>
        <CardTitle>Tenant settings</CardTitle>
        <CardDescription>Compliance policy settings that apply to every enrolled device</CardDescription>
      </CardHeader>
      <CardContent>
        <PropertyList
          plain
          items={[
            [
              'Mark devices with no compliance policy assigned as',
              s.noPolicyDevicesCompliant === null ? null : <Setting text={s.noPolicyDevicesCompliant ? 'Compliant' : 'Not compliant'} risky={s.noPolicyDevicesCompliant} />,
            ],
            ['Compliance status validity period', s.checkinThresholdDays === null ? null : plural(s.checkinThresholdDays, 'day')],
            ['Enhanced jailbreak detection', flag(s.enhancedJailBreak)],
            ['Scheduled actions for non-compliance', flag(s.isScheduledActionEnabled)],
          ]}
        />
      </CardContent>
    </Card>
  )
}

export function DeviceCompliancePage() {
  return (
    <ListPage
      title="Device compliance"
      description="Intune compliance policies. Conditional Access policies that require a compliant device trust the result, so a lenient policy or a device with no policy can pass."
    >
      <div className="flex flex-col gap-6">
        <TenantSettings />
        <DataTable route="/api/device-compliance" columns={columns} resource="device-compliance" searchPlaceholder="Search policy name" noun="compliance policy" defaultSort={{ sort: 'displayName', order: 'asc' }} />
      </div>
    </ListPage>
  )
}

// Intune admin center labels.
const ACTION: Record<string, string> = {
  block: 'Mark device non-compliant',
  notification: 'Send email to end user',
  pushNotification: 'Send push notification to end user',
  remoteLock: 'Remotely lock the non-compliant device',
  retire: 'Add device to retire list',
  wipe: 'Wipe the device',
}

function SettingValue({ v }: { v: unknown }) {
  if (typeof v === 'boolean') return <Flag value={v} />
  if (v !== null && typeof v === 'object') return <JsonView value={v} depth={1} />
  return String(v)
}

function Actions({ items }: { items: CompliancePolicyDetail['actions'] }) {
  if (items.length === 0) return <p className="text-muted-foreground">None.</p>
  return (
    <div className="glass overflow-hidden rounded-xl border">
      <Table>
        <TableHeader className="bg-shoulder">
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-full px-3 font-semibold text-ink">Action</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Schedule</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((a, i) => (
            <TableRow key={i}>
              <TableCell className="px-3">{ACTION[a.actionType] ?? a.actionType}</TableCell>
              <TableCell className="px-3 tabular-nums">{a.gracePeriodHours === 0 ? 'Immediately' : `After ${grace(a.gracePeriodHours)}`}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export function CompliancePolicyPage() {
  const { id = '' } = useParams()
  const { data: p, isLoading, error } = useApi('/api/device-compliance/{id}', { path: { id } })
  useSetCrumb(p?.displayName)
  return (
    <ObjectPage
      type={KIND}
      title={p?.displayName}
      loading={isLoading}
      error={error}
      raw={p?.raw}
      summary={p && [
        ['Platform', p.platform],
        ['Description', p.description],
        ['Assigned to', refs(p.assignments) ?? <span key="a" className="text-muted-foreground">Not assigned</span>],
        ['Excluded', refs(p.exclusions)],
        ['Marked non-compliant', grace(p.gracePeriodHours)],
        ['Created', fmtDate(p.createdDateTime, true)],
        ['Modified', fmtDate(p.lastModifiedDateTime, true)],
        ['Version', p.version],
        ['Policy ID', p.id, { mono: true, copy: p.id }],
      ]}
      tabs={[
        {
          key: 'settings',
          label: 'Settings',
          count: p?.settings.length,
          render: () => p && <PropertyList items={p.settings.map((s) => [camelBreaks(s.name), <SettingValue key={s.name} v={s.value} />] as Property)} />,
        },
        { key: 'actions', label: 'Actions for non-compliance', count: p?.actions.length, render: () => p && <Actions items={p.actions} /> },
      ]}
    />
  )
}
