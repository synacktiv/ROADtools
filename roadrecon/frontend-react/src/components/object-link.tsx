import { useState } from 'react'
import { Link } from 'react-router'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { PolicyStateBadge } from '@/components/badges'
import { Skeleton } from '@/components/ui/skeleton'
import { useApi } from '@/api/client'
import type { ObjectRef, ObjectType, PolicyState, Route } from '@/api/types'
import { cn } from '@/lib/utils'
import {
  IconAppWindow,
  IconCrown,
  IconDeviceLaptop,
  IconHelpCircle,
  IconHierarchy2,
  IconMapPin,
  IconRobot,
  IconShieldLock,
  IconUser,
  IconUsersGroup,
  type Icon,
} from '@tabler/icons-react'

// One road-sign shape per object type (ROADMAP.md appendix B).
const ICONS: Partial<Record<ObjectType, Icon>> = {
  user: IconUser,
  group: IconUsersGroup,
  device: IconDeviceLaptop,
  servicePrincipal: IconRobot,
  application: IconAppWindow,
  administrativeUnit: IconHierarchy2,
  role: IconCrown,
  policy: IconShieldLock,
  namedLocation: IconMapPin,
  unknown: IconHelpCircle,
}

export const TYPE_LABEL: Record<ObjectType, string> = {
  user: 'User',
  group: 'Group',
  device: 'Device',
  servicePrincipal: 'Service principal',
  application: 'Application',
  administrativeUnit: 'Administrative unit',
  role: 'Directory role',
  policy: 'Conditional Access policy',
  namedLocation: 'Named location',
  keyword: 'Keyword',
  value: 'Value',
  unknown: 'Unresolved reference',
}

const BASE: Partial<Record<ObjectType, string>> = {
  user: '/users',
  group: '/groups',
  device: '/devices',
  servicePrincipal: '/service-principals',
  application: '/applications',
  administrativeUnit: '/administrative-units',
  role: '/roles',
  policy: '/policies',
  namedLocation: '/named-locations',
}

const DETAIL_ROUTE: Partial<Record<ObjectType, Route>> = {
  user: '/api/users/{id}',
  group: '/api/groups/{id}',
  device: '/api/devices/{id}',
  servicePrincipal: '/api/service-principals/{id}',
  application: '/api/applications/{id}',
  administrativeUnit: '/api/administrative-units/{id}',
  role: '/api/roles/{id}',
  policy: '/api/policies/{id}',
  namedLocation: '/api/named-locations/{id}',
}

export function objectHref(ref: Pick<ObjectRef, 'type' | 'id'>) {
  const base = BASE[ref.type]
  return base && ref.id ? `${base}/${encodeURIComponent(ref.id)}` : null
}

/** One Tabler icon per object type, used wherever an object is mentioned. */
export function TypeGlyph({ type, className }: { type: ObjectType; className?: string }) {
  const I = ICONS[type]
  return I ? <I aria-hidden stroke={1.75} className={cn('size-4 shrink-0', className)} /> : null
}

interface ObjectLinkProps {
  value: ObjectRef
  /** Show the secondary identifier (UPN, appId) after the name. */
  sub?: boolean
  /** Let long names wrap instead of truncating (narrow columns). */
  wrap?: boolean
  className?: string
}

/** The only way an object is ever mentioned in the UI. */
export function ObjectLink({ value, sub, wrap, className }: ObjectLinkProps) {
  const href = objectHref(value)
  const content = (
    <>
      <TypeGlyph type={value.type} className="text-muted-foreground" />
      <span data-copy className={cn('min-w-0', wrap ? 'break-words' : 'truncate')}>{value.displayName}</span>
      {sub && value.sub && <span className="min-w-0 shrink-[4] truncate text-muted-foreground">{value.sub}</span>}
    </>
  )
  if (value.type === 'keyword')
    return <span className={cn('inline-flex items-center gap-1.5 font-semibold', className)}>{value.displayName}</span>
  if (!href)
    return (
      <span
        className={cn('inline-flex min-w-0 items-center gap-1.5', value.type === 'unknown' && 'text-muted-foreground', className)}
        title={value.type === 'unknown' ? `${TYPE_LABEL.unknown}: ${value.id}` : undefined}
      >
        {content}
      </span>
    )
  return (
    <ObjectPreview value={value}>
      <Link
        to={href}
        className={cn(
          'inline-flex min-w-0 items-center gap-1.5 rounded-sm decoration-muted-foreground/50 underline-offset-4 hover:underline',
          className,
        )}
      >
        {content}
      </Link>
    </ObjectPreview>
  )
}

function ObjectPreview({ value, children }: { value: ObjectRef; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <HoverCard openDelay={450} closeDelay={80} onOpenChange={setOpen}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent align="start" className="w-80 p-3">
        {open && <PreviewBody value={value} />}
      </HoverCardContent>
    </HoverCard>
  )
}

function PreviewBody({ value }: { value: ObjectRef }) {
  const route = DETAIL_ROUTE[value.type]!
  const { data, isLoading } = useApi(route, { path: { id: value.id! } })
  const facts = data ? previewFacts(value.type, data as unknown as Record<string, unknown>) : []
  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2">
        <TypeGlyph type={value.type} className="mt-0.5 size-4" />
        <div className="min-w-0">
          <div className="font-semibold leading-tight">{value.displayName}</div>
          <div className="text-xs text-muted-foreground">{TYPE_LABEL[value.type]}</div>
        </div>
      </div>
      {isLoading ? (
        <Skeleton className="h-10 w-full" />
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {facts.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="truncate">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

function previewFacts(type: ObjectType, d: Record<string, unknown>): [string, React.ReactNode][] {
  const yes = (v: unknown) => (v ? 'Yes' : 'No')
  const counts = (d.counts ?? {}) as Record<string, number>
  switch (type) {
    case 'user':
      return [
        ['UPN', d.userPrincipalName as string],
        ['Type', d.userType as string],
        ['Status', <StatusText key="s" enabled={d.accountEnabled as boolean} />],
        ['Groups', counts.memberOf],
        ['Roles', counts.roles],
      ]
    case 'group':
      return [
        ['Members', counts.transitiveMemberUsers],
        ['Role assignable', yes(d.isAssignableToRole)],
        ['Source', d.dirSyncEnabled ? 'Synced' : 'Cloud'],
      ]
    case 'servicePrincipal':
      return [
        ['App ID', <span key="a" className="font-mono">{d.appId as string}</span>],
        ['Publisher', (d.publisherName as string) ?? '·'],
        ['Credentials', (d.passwordCount as number) + (d.keyCount as number)],
      ]
    case 'application':
      return [
        ['App ID', <span key="a" className="font-mono">{d.appId as string}</span>],
        ['Multitenant', yes(d.availableToOtherTenants)],
        ['Credentials', (d.passwordCount as number) + (d.keyCount as number)],
      ]
    case 'device':
      return [
        ['OS', `${d.deviceOSType ?? ''} ${d.deviceOSVersion ?? ''}`],
        ['Trust type', (d.deviceTrustType as string) ?? '·'],
        ['Compliant', yes(d.isCompliant)],
      ]
    case 'role':
      return [
        ['Active', d.activeCount as number],
        ['Eligible', d.eligibleCount as number],
        ['Built-in', yes(d.isBuiltIn)],
      ]
    case 'policy':
      return [
        ['State', <PolicyStateBadge key="s" state={d.state as PolicyState} />],
        ['Grant', d.block ? 'Block' : (d.grant as string[]).join(d.grantOperator === 'AND' ? ' and ' : ' or ') || '·'],
        ['Users in scope', (d.counts as Record<string, number>)?.inScope],
      ]
    default:
      return [['ID', <span key="i" className="font-mono">{d.id as string}</span>]]
  }
}

function StatusText({ enabled }: { enabled: boolean }) {
  return <span className={enabled ? 'text-guide' : 'text-regulatory'}>{enabled ? 'Enabled' : 'Disabled'}</span>
}
