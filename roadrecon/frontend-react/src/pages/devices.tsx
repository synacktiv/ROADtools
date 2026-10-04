import { Link, useParams } from 'react-router'
import type { ColumnDef } from '@tanstack/react-table'
import {
  IconBan,
  IconBrandAndroid,
  IconBrandApple,
  IconBrandUbuntu,
  IconBrandWindows,
  IconBug,
  IconCheck,
  IconCircleX,
  IconCloud,
  IconCopy,
  IconDeviceDesktop,
  IconHelpCircle,
  IconKey,
  IconServer2,
  IconClipboardX,
  IconUserCircle,
  type Icon,
} from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable, type FilterDef } from '@/components/data-table'
import { ObjectLink } from '@/components/object-link'
import { ObjectPage } from '@/components/object-page'
import { EnabledBadge, SourceIcon, SourceText, flag } from '@/components/badges'
import { Dash, ListPage, SubViews, orDash, toRef } from '@/components/page-parts'
import { UsersTable } from '@/pages/users'
import { GroupsTable } from '@/pages/groups'
import { RoleAssignmentsTable } from '@/pages/roles'
import { useApi } from '@/api/client'
import type { AdministrativeUnitQuery, AdministrativeUnitRow, BitLockerKey, DeviceQuery, DeviceRow, ObjectRef } from '@/api/types'
import { copy } from '@/lib/copy'
import { fmtDate, fmtNumber } from '@/lib/format'
import { useSetCrumb } from '@/lib/crumb'

const OS_ICON: Record<string, Icon> = { Windows: IconBrandWindows, iOS: IconBrandApple, IPhone: IconBrandApple, MacOS: IconBrandApple, Android: IconBrandAndroid, Linux: IconBrandUbuntu }

function OsName({ type, version }: { type: string | null; version: string | null }) {
  if (!type) return <Dash />
  const I = OS_ICON[type] ?? IconDeviceDesktop
  return (
    <span className="inline-flex items-center gap-2">
      <I className="size-4 shrink-0 text-muted-foreground" stroke={1.75} aria-hidden />
      {type} {version && <span className="font-mono text-sm text-muted-foreground tabular-nums">{version}</span>}
    </span>
  )
}

const TRUST: Record<string, [label: string, icon: Icon, hint: string]> = {
  AzureAd: ['Entra joined', IconCloud, 'Joined to Entra ID only. Organisation owned.'],
  ServerAd: ['Hybrid joined', IconServer2, 'Joined to on-premises AD and registered in Entra ID.'],
  Workplace: ['Registered', IconUserCircle, 'Registered in Entra ID (workplace join). Usually a personal or mobile device.'],
}

function TrustType({ value }: { value: string | null }) {
  if (!value) return <Dash />
  const [label, I, hint] = TRUST[value] ?? [value, IconHelpCircle, value]
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-2">
          <I className="size-4 shrink-0 text-muted-foreground" stroke={1.75} aria-hidden />
          {label}
        </span>
      </TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  )
}

function ModelName({ model, manufacturer }: { model: string | null; manufacturer: string | null }) {
  if (!model && !manufacturer) return <Dash />
  return (
    <span className="inline-flex gap-2 whitespace-nowrap">
      {model} <span className="text-muted-foreground">{manufacturer}</span>
    </span>
  )
}

/** Posture cell: a quiet check when good (`value` true), a red cross when not. */
function PostureMark({ value, yes, no }: { value: boolean | null; yes: string; no: string }) {
  if (value === null) return null
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label={value ? yes : no} className="inline-flex">
          {value ? <IconCheck className="size-4 text-muted-foreground" stroke={2} /> : <IconCircleX className="size-4 text-regulatory" stroke={1.75} />}
        </span>
      </TooltipTrigger>
      <TooltipContent>{value ? yes : no}</TooltipContent>
    </Tooltip>
  )
}

/** Risk markers shown after the device name in lists. */
const MARKERS: [show: (d: DeviceRow) => boolean, icon: Icon, label: string][] = [
  [(d) => !d.accountEnabled, IconBan, 'Disabled'],
  [(d) => d.isCompliant === false, IconClipboardX, 'Not compliant'],
  [(d) => !!d.isRooted, IconBug, 'Rooted or jailbroken, as reported by the MDM'],
]

function DeviceName({ d }: { d: DeviceRow }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <ObjectLink value={toRef('device', d)} />
      {MARKERS.filter(([show]) => show(d)).map(([, I, label]) => (
        <Tooltip key={label}>
          <TooltipTrigger asChild>
            <span tabIndex={0} aria-label={label} className="inline-flex shrink-0 text-regulatory">
              <I className="size-4" stroke={1.75} />
            </span>
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      ))}
    </span>
  )
}

const mono = (v: string | null) => (v ? <span className="font-mono text-sm">{v}</span> : <Dash />)

const deviceColumns: ColumnDef<DeviceRow>[] = [
  { id: 'displayName', header: 'Name', meta: { sort: 'displayName', filter: 'displayName' }, enableHiding: false, cell: ({ row }) => <DeviceName d={row.original} /> },
  { id: 'os', header: 'Operating system', meta: { sort: 'deviceOSType', filter: 'deviceOSType' }, cell: ({ row }) => <OsName type={row.original.deviceOSType} version={row.original.deviceOSVersion} /> },
  { id: 'trust', header: 'Trust type', meta: { filter: 'deviceTrustType' }, cell: ({ row }) => <TrustType value={row.original.deviceTrustType} /> },
  { id: 'model', header: 'Model', meta: { filter: 'deviceModel' }, cell: ({ row }) => <ModelName model={row.original.deviceModel} manufacturer={row.original.deviceManufacturer} /> },
  { id: 'isManaged', header: 'Managed', meta: { filter: 'isManaged', noCopy: true }, cell: ({ row }) => <PostureMark value={row.original.isManaged} yes="Managed by an MDM" no="Not managed" /> },
  // Extras, off by default. The three posture flags are markers on the name; these columns add header filters.
  { id: 'deviceOSVersion', header: 'OS version', meta: { filter: 'deviceOSVersion', defaultHidden: true }, cell: ({ row }) => mono(row.original.deviceOSVersion) },
  { id: 'deviceManufacturer', header: 'Manufacturer', meta: { filter: 'deviceManufacturer', defaultHidden: true }, cell: ({ row }) => orDash(row.original.deviceManufacturer) },
  { id: 'accountEnabled', header: 'Enabled', meta: { filter: 'accountEnabled', noCopy: true, defaultHidden: true }, cell: ({ row }) => <PostureMark value={row.original.accountEnabled} yes="Enabled" no="Disabled" /> },
  { id: 'isCompliant', header: 'Compliant', meta: { filter: 'isCompliant', noCopy: true, defaultHidden: true }, cell: ({ row }) => <PostureMark value={row.original.isCompliant} yes="Compliant" no="Not compliant" /> },
  {
    id: 'isRooted',
    header: 'Rooted',
    meta: { filter: 'isRooted', noCopy: true, defaultHidden: true },
    cell: ({ row }) => <PostureMark value={row.original.isRooted === null ? null : !row.original.isRooted} yes="Not rooted" no="Rooted or jailbroken" />,
  },
  { id: 'source', header: 'Source', meta: { defaultHidden: true }, cell: ({ row }) => <SourceIcon dirSync={row.original.dirSyncEnabled} /> },
  { id: 'deviceId', header: 'Device ID', meta: { defaultHidden: true }, cell: ({ row }) => mono(row.original.deviceId) },
  { id: 'id', header: 'Object ID', meta: { defaultHidden: true }, cell: ({ row }) => mono(row.original.id) },
]

export function DevicesTable({ query, filters = [] }: { query?: Partial<DeviceQuery>; filters?: FilterDef[] }) {
  return (
    <DataTable
      route="/api/devices"
      query={query}
      columns={deviceColumns}
      filters={filters}
      resource="devices"
      searchPlaceholder="Search name, device ID or object ID"
      noun="device"
      defaultSort={{ sort: 'displayName', order: 'asc' }}
    />
  )
}

export function DevicesPage() {
  return (
    <ListPage title="Devices">
      <DevicesTable />
    </ListPage>
  )
}

function BitLockerKeys({ items }: { items: BitLockerKey[] }) {
  if (items.length === 0) return <p className="text-muted-foreground">No BitLocker recovery keys were found for this device.</p>
  return (
    <ul className="glass divide-y overflow-hidden rounded-xl border">
      {items.map((k) => (
        <li key={k.keyIdentifier} className="flex items-center gap-4 px-4 py-3.5">
          <IconKey className="size-5 shrink-0 text-muted-foreground" stroke={1.75} aria-hidden />
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <code className="w-fit rounded-md bg-muted/60 px-2.5 py-1 font-mono tracking-wide break-all select-all">{k.keyMaterial}</code>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
              <span>
                Key ID <span className="font-mono">{k.keyIdentifier}</span>
              </span>
              {k.volumeType && <span>{k.volumeType}</span>}
              {k.creationTime && <span>Created {fmtDate(k.creationTime)}</span>}
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => copy(k.keyMaterial, 'Recovery key')}>
            <IconCopy /> Copy key
          </Button>
        </li>
      ))}
    </ul>
  )
}

function Owners({ owners, total }: { owners: ObjectRef[]; total: number }) {
  if (owners.length === 0) return <span className="text-muted-foreground">None</span>
  const more = Math.max(total, owners.length) - 3
  return (
    <div className="flex flex-col gap-1">
      {owners.slice(0, 3).map((o) => (
        <ObjectLink key={o.id} value={o} />
      ))}
      {more > 0 && (
        <Link to="?tab=owners" className="text-sm text-muted-foreground hover:text-foreground">
          {fmtNumber(more)} more
        </Link>
      )}
    </div>
  )
}

export function DevicePage() {
  const { id = '' } = useParams()
  const { data: d, isLoading, error } = useApi('/api/devices/{id}', { path: { id } })
  useSetCrumb(d?.displayName)
  return (
    <ObjectPage
      type="device"
      title={d?.displayName}
      loading={isLoading}
      error={error}
      portalUrl={`https://entra.microsoft.com/#view/Microsoft_AAD_Devices/DeviceDetailsMenuBlade/~/Properties/objectId/${id}`}
      badges={
        d && (
          <>
            {!d.accountEnabled && <EnabledBadge enabled={false} />}
            {d.isCompliant === false && (
              <Badge variant="regulatory">
                <IconClipboardX /> Not compliant
              </Badge>
            )}
            {d.isRooted && (
              <Badge variant="regulatory">
                <IconBug /> Rooted
              </Badge>
            )}
            {d.bitLockerKeys.length > 0 && (
              <Badge variant="warning" asChild>
                <Link to="?tab=bitlocker">
                  <IconKey /> BitLocker key escrowed
                </Link>
              </Badge>
            )}
          </>
        )
      }
      summary={
        d && [
          ['Operating system', <OsName key="os" type={d.deviceOSType} version={d.deviceOSVersion} />],
          ['Trust type', <TrustType key="t" value={d.deviceTrustType} />],
          ['Owner', <Owners key="o" owners={d.owners} total={d.counts.owners} />],
          // Compliance only when the header does not already flag it.
          ['Compliant', d.isCompliant === false ? null : flag(d.isCompliant)],
          ['Managed', flag(d.isManaged, false)],
          ['Model', <ModelName key="m" model={d.deviceModel} manufacturer={d.deviceManufacturer} />],
          ['Source', <SourceText key="src" dirSync={d.dirSyncEnabled} />],
          ['Device ID', d.deviceId, { mono: true, copy: d.deviceId ?? undefined }],
          ['Object ID', d.id, { mono: true, copy: d.id }],
        ]
      }
      raw={d?.raw}
      tabs={[
        { key: 'owners', label: 'Owners', count: d?.counts.owners, render: () => <UsersTable query={{ ownerOf: id }} filters={[]} noun="owner" /> },
        { key: 'memberOf', label: 'Member of', count: d?.counts.memberOf, render: () => <GroupsTable query={{ memberId: id }} noun="group" /> },
        { key: 'units', label: 'Administrative units', count: d?.counts.administrativeUnits, hidden: d?.counts.administrativeUnits === 0, render: () => <AdministrativeUnitsTable query={{ memberId: id }} /> },
        { key: 'bitlocker', label: 'BitLocker keys', count: d?.bitLockerKeys.length, render: () => d && <BitLockerKeys items={d.bitLockerKeys} /> },
      ]}
    />
  )
}

// --- Administrative units --------------------------------------------------

const auColumns: ColumnDef<AdministrativeUnitRow>[] = [
  { id: 'displayName', header: 'Name', meta: { sort: 'displayName', filter: 'displayName' }, enableHiding: false, cell: ({ row }) => <ObjectLink value={toRef('administrativeUnit', row.original)} /> },
  { id: 'description', header: 'Description', meta: { filter: 'description' }, cell: ({ row }) => orDash(row.original.description) },
  {
    id: 'membershipRule',
    header: 'Membership rule',
    meta: { filter: 'dynamic' },
    cell: ({ row }) => (row.original.membershipRule ? <span className="font-mono text-sm">{row.original.membershipRule}</span> : <span className="text-muted-foreground">Assigned</span>),
  },
  { id: 'id', header: 'Object ID', meta: { defaultHidden: true }, cell: ({ row }) => mono(row.original.id) },
]

export function AdministrativeUnitsTable({ query }: { query?: Partial<AdministrativeUnitQuery> }) {
  return <DataTable route="/api/administrative-units" query={query} columns={auColumns} resource="administrative-units" noun="administrative unit" defaultSort={{ sort: 'displayName', order: 'asc' }} />
}

export function AdministrativeUnitsPage() {
  return (
    <ListPage title="Administrative units">
      <AdministrativeUnitsTable />
    </ListPage>
  )
}

export function AdministrativeUnitPage() {
  const { id = '' } = useParams()
  const { data: a, isLoading, error } = useApi('/api/administrative-units/{id}', { path: { id } })
  useSetCrumb(a?.displayName)
  const c = a?.counts
  const total = c ? c.memberUsers + c.memberGroups + c.memberDevices : 0
  return (
    <ObjectPage
      type="administrativeUnit"
      title={a?.displayName}
      loading={isLoading}
      error={error}
      badges={a?.membershipRule && <Badge variant="outline">Dynamic</Badge>}
      summary={
        a && [
          ['Membership rule', a.membershipRule ?? 'Assigned', a.membershipRule ? { mono: true, copy: a.membershipRule } : undefined],
          ['Description', a.description],
          ['Object ID', a.id, { mono: true, copy: a.id }],
        ]
      }
      raw={a?.raw}
      tabs={[
        {
          key: 'members',
          label: 'Members',
          count: c && total,
          render: () => (
            // Empty member types are hidden unless the unit has no members at all.
            <SubViews
              views={[
                { key: 'users', label: 'Users', count: c?.memberUsers, hidden: total > 0 && c?.memberUsers === 0, render: () => <UsersTable query={{ memberOfAu: id }} noun="member" /> },
                { key: 'groups', label: 'Groups', count: c?.memberGroups, hidden: total > 0 && c?.memberGroups === 0, render: () => <GroupsTable query={{ memberOfAu: id }} noun="member group" /> },
                { key: 'devices', label: 'Devices', count: c?.memberDevices, hidden: total > 0 && c?.memberDevices === 0, render: () => <DevicesTable query={{ memberOfAu: id }} /> },
              ]}
            />
          ),
        },
        { key: 'roles', label: 'Scoped roles', count: c?.scopedRoles, render: () => <RoleAssignmentsTable query={{ scopeId: id }} /> },
      ]}
    />
  )
}
