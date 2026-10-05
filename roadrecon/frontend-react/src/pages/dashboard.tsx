import { Link } from 'react-router'
import { IconAlertTriangle, IconFingerprintOff, IconKey, IconUserOff, IconUserShield, IconWorld } from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ObjectLink, TypeGlyph } from '@/components/object-link'
import { copy } from '@/components/object-page'
import { PropertyList } from '@/components/property-list'
import { toRef } from '@/components/page-parts'
import { Flag, SourceIcon } from '@/components/badges'
import { useApi } from '@/api/client'
import type { ObjectType, Route, Tenant } from '@/api/types'
import { fmtNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useSetCrumb } from '@/lib/crumb'

type ListRoute = Extract<Route, '/api/users' | '/api/service-principals' | '/api/applications' | '/api/policies' | '/api/roles'>

/** A filtered list: the count comes from the API, the link opens the same filter on the list page. */
interface Slice {
  page: string
  filter: string[]
  match?: 'any'
}

const href = ({ page, filter, match }: Slice) => {
  const qs = new URLSearchParams(filter.map((f) => ['filter', f]))
  if (match) qs.set('match', match)
  return `${page}?${qs}`
}

function useCount(route: ListRoute, s: Slice) {
  return useApi(route, { query: { filter: s.filter, match: s.match, page_size: 1 } }).data?.total
}

const num = (n: number | undefined) => (n === undefined ? '-' : fmtNumber(n))

/** Label, n of total and a thin bar. The whole row links to the filtered list. */
function Meter({ to, icon: Icon, label, help, n, of, showOf, risky }: { to: string; icon: typeof IconKey; label: string; help: string; n?: number; of?: number; showOf?: boolean; risky?: boolean }) {
  const pct = n && of ? Math.max(2, (n / of) * 100) : 0
  const bad = risky && !!n
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link to={to} className="group -mx-2 grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1.5 rounded-md px-2 py-1.5 transition-colors hover:bg-accent">
          <span className={cn('flex items-center gap-2', bad ? 'text-regulatory' : 'text-muted-foreground group-hover:text-foreground')}>
            <Icon className="size-4 shrink-0" stroke={1.75} aria-hidden />
            {label}
          </span>
          <span className="tabular-nums">
            <span className={cn('font-semibold', bad && 'text-regulatory')}>{num(n)}</span>
            {showOf && <span className="text-muted-foreground"> / {num(of)}</span>}
          </span>
          <span className="col-span-2 flex h-1.5 overflow-hidden rounded-full bg-muted">
            <span className={cn('rounded-full transition-[width] duration-500 motion-reduce:transition-none', bad ? 'bg-regulatory' : 'bg-foreground/60')} style={{ width: `${pct}%` }} />
          </span>
        </Link>
      </TooltipTrigger>
      <TooltipContent side="bottom">{help}</TooltipContent>
    </Tooltip>
  )
}

function BigCount({ to, type, label, value }: { to: string; type: ObjectType; label: string; value?: number }) {
  return (
    <Link to={to} className="group flex flex-col gap-0.5">
      <span className="flex items-center gap-1.5 text-muted-foreground group-hover:text-foreground">
        <TypeGlyph type={type} />
        {label}
      </span>
      <span className="text-4xl font-semibold tracking-tight tabular-nums">{num(value)}</span>
    </Link>
  )
}

const noMfa: Slice = { page: '/users', filter: ['hasMfa:eq:false', 'accountEnabled:eq:true'] }
const enabledUsers: Slice = { page: '/users', filter: ['accountEnabled:eq:true'] }
const disabledUsers: Slice = { page: '/users', filter: ['accountEnabled:eq:false'] }
const guests: Slice = { page: '/users', filter: ['userType:in:Guest'] }
const spCreds: Slice = { page: '/service-principals', filter: ['passwordCount:gt:0', 'keyCount:gt:0'], match: 'any' }
const spOwned: Slice = { page: '/service-principals', filter: ['hasCustomOwner:eq:true'] }
const appCreds: Slice = { page: '/applications', filter: ['passwordCount:gt:0', 'keyCount:gt:0'], match: 'any' }

function UsersCard({ total, guestCount }: { total?: number; guestCount?: number }) {
  const enabled = useCount('/api/users', enabledUsers)
  const missing = useCount('/api/users', noMfa)
  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <BigCount to="/users" type="user" label="Users" value={total} />
        <div className="flex flex-col gap-1">
          <Meter to={href(noMfa)} icon={IconFingerprintOff} label="Without MFA" help="Enabled accounts with no strong authentication method registered, out of all enabled accounts" n={missing} of={enabled} showOf risky />
          <Meter to={href(guests)} icon={IconWorld} label="Guests" help="External accounts invited into the tenant" n={guestCount} of={total} />
          <Meter to={href(disabledUsers)} icon={IconUserOff} label="Disabled" help="Accounts that cannot sign in" n={total !== undefined && enabled !== undefined ? total - enabled : undefined} of={total} />
        </div>
      </CardContent>
    </Card>
  )
}

function AppsCard({ sps, apps }: { sps?: number; apps?: number }) {
  const spWithCreds = useCount('/api/service-principals', spCreds)
  const spWithOwner = useCount('/api/service-principals', spOwned)
  const appWithCreds = useCount('/api/applications', appCreds)
  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        <div className="flex gap-10">
          <BigCount to="/service-principals" type="servicePrincipal" label="Service principals" value={sps} />
          <BigCount to="/applications" type="application" label="App registrations" value={apps} />
        </div>
        <div className="flex flex-col gap-1">
          <Meter to={href(spCreds)} icon={IconKey} label="Service principals with credentials" help="Hold at least one secret or certificate" n={spWithCreds} of={sps} />
          <Meter to={href(appCreds)} icon={IconKey} label="App registrations with credentials" help="Hold at least one secret or certificate" n={appWithCreds} of={apps} />
          <Meter to={href(spOwned)} icon={IconUserShield} label="Service principals with an owner" help="Owners can add credentials and act as the app" n={spWithOwner} of={sps} />
        </div>
      </CardContent>
    </Card>
  )
}

const stateSlice = (state: string): Slice => ({ page: '/policies', filter: [`state:in:${state}`] })

function ConditionalAccessCard() {
  const counts = {
    enabled: useCount('/api/policies', stateSlice('enabled')),
    reporting: useCount('/api/policies', stateSlice('reporting')),
    disabled: useCount('/api/policies', stateSlice('disabled')),
  }
  const parts = (
    [
      ['enabled', 'Enforced', 'bg-guide', 'text-guide'],
      ['reporting', 'Report-only', 'bg-warning', 'text-warning'],
      ['disabled', 'Disabled', 'bg-muted-foreground/40', 'text-muted-foreground'],
    ] as const
  ).map(([state, label, bar, text]) => ({ state, label, bar, text, to: href(stateSlice(state)), n: counts[state] ?? 0 }))
  const blockSlice: Slice = { page: '/policies', filter: ['block:eq:true', 'state:in:enabled'] }
  const blocking = useCount('/api/policies', blockSlice)
  const total = parts.reduce((s, p) => s + p.n, 0)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Conditional Access</CardTitle>
        <CardDescription>{fmtNumber(total)} policies</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" asChild>
            <Link to="/policies">View policies</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex h-2 gap-0.5 overflow-hidden rounded-full" role="img" aria-label={parts.map((p) => `${p.n} ${p.label}`).join(', ')}>
          {parts.map((p) => p.n > 0 && <div key={p.state} className={cn('rounded-full', p.bar)} style={{ width: `${(p.n / Math.max(total, 1)) * 100}%` }} />)}
        </div>
        <div className="-mx-2 grid grid-cols-3 gap-1">
          {parts.map((p) => (
            <Link key={p.state} to={p.to} className="flex flex-col rounded-md px-2 py-1.5 transition-colors hover:bg-accent">
              <span className={cn('text-2xl font-semibold tabular-nums', p.text)}>{fmtNumber(p.n)}</span>
              <span className="text-muted-foreground">{p.label}</span>
            </Link>
          ))}
        </div>
        {blocking !== undefined && (
          <Link to={href(blockSlice)} className="-mx-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
            <span className="font-semibold text-foreground tabular-nums">{fmtNumber(blocking)}</span> enforced {blocking === 1 ? 'policy blocks' : 'policies block'} access
          </Link>
        )}
      </CardContent>
    </Card>
  )
}

function RolesCard() {
  const { data } = useApi('/api/roles', { query: { sort: 'activeCount', order: 'desc', page_size: 6, hasAssignments: true } })
  const max = Math.max(1, ...(data?.items ?? []).map((r) => r.activeCount + r.eligibleCount))
  const inUse: Slice = { page: '/roles', filter: ['activeCount:gt:0', 'eligibleCount:gt:0'], match: 'any' }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Directory roles</CardTitle>
        <CardDescription className="flex items-center gap-3">
          Most assigned
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-foreground/70" aria-hidden />
            Active
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-warning" aria-hidden />
            Eligible
          </span>
        </CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" asChild>
            <Link to={href(inUse)}>{data ? `${fmtNumber(data.total)} in use` : 'All roles'}</Link>
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {!data && <Skeleton className="h-40 w-full" />}
        {data?.items.map((r) => (
          <div key={r.id} className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between gap-3">
              <ObjectLink value={toRef('role', r)} />
              <span className="shrink-0 tabular-nums">
                {r.activeCount}
                {r.eligibleCount > 0 && <span className="text-warning"> +{r.eligibleCount}</span>}
              </span>
            </div>
            <div className="flex h-1.5 gap-0.5 overflow-hidden rounded-full">
              <div className="rounded-full bg-foreground/70" style={{ width: `${(r.activeCount / max) * 100}%` }} />
              {r.eligibleCount > 0 && <div className="rounded-full bg-warning" style={{ width: `${(r.eligibleCount / max) * 100}%` }} />}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

/** Setting text with a warning mark when the value is the risky option. */
function Setting({ text, risky }: { text: string; risky: boolean }) {
  return (
    <span className={cn('inline-flex items-start gap-1.5', risky && 'text-regulatory')}>
      {risky && <IconAlertTriangle className="mt-1 size-4 shrink-0" stroke={1.75} aria-label="Risky" />}
      {text}
    </span>
  )
}

function AuthorizationPolicyCard({ ap }: { ap: Tenant['authorizationPolicy'] }) {
  const consentRisky = ap?.userConsentPolicy === 'all'
  const guestRisky = ap?.guestRole === 'member'
  const inviteRisky = ap?.guestInvitesFrom === 'everyone' || ap?.guestInvitesFrom === 'members'
  const risky = ap ? [ap.usersCanRegisterApps === true, ap.blockMsolPowerShell === false, consentRisky, guestRisky, inviteRisky].filter(Boolean).length : 0
  const flag = (value: boolean | null, bad?: boolean) => (value === null ? null : <Flag value={value} risky={bad} />)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Authorization policy</CardTitle>
        <CardDescription>Defaults that apply to every user</CardDescription>
        {risky > 0 && (
          <CardAction>
            <Badge variant="regulatory">
              <IconAlertTriangle stroke={1.75} />
              {risky} risky
            </Badge>
          </CardAction>
        )}
      </CardHeader>
      <CardContent>
        {ap ? (
          <PropertyList
            plain
            items={[
              ['Users can register apps', flag(ap.usersCanRegisterApps, true)],
              ['User consent to apps', <Setting text={ap.userConsent} risky={consentRisky} />],
              ['MSOnline PowerShell blocked', flag(ap.blockMsolPowerShell, false)],
              ['Users can create security groups', flag(ap.usersCanCreateSecurityGroups)],
              ['Users can read other users', flag(ap.usersCanReadOtherUsers)],
              ['Guest access', <Setting text={ap.guestAccess} risky={guestRisky} />],
              ['Who can invite guests', <Setting text={ap.guestInvites} risky={inviteRisky} />],
              ['Self-service password reset', flag(ap.selfServicePasswordReset)],
            ]}
          />
        ) : (
          <p className="text-muted-foreground">Not in the dump.</p>
        )}
      </CardContent>
    </Card>
  )
}

function DomainsCard({ domains }: { domains?: Tenant['domains'] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Domains</CardTitle>
        <CardDescription>{domains ? `${domains.length} verified` : ' '}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader className="bg-shoulder">
              <TableRow className="hover:bg-transparent">
                <TableHead className="px-3">Domain</TableHead>
                <TableHead className="px-3">Type</TableHead>
                <TableHead className="px-3">Capabilities</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {domains?.map((d) => (
                <TableRow key={d.name}>
                  <TableCell className="px-3">
                    <span className="inline-flex items-center gap-2">
                      {d.name}
                      {d.isDefault && <Badge variant="outline">Default</Badge>}
                      {d.isInitial && <Badge variant="outline">Initial</Badge>}
                    </span>
                  </TableCell>
                  <TableCell className="px-3">{d.type}</TableCell>
                  <TableCell className="px-3 whitespace-normal text-muted-foreground">{d.capabilities.join(', ')}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}


// Setting names are CamelCase: a zero-width space before each word lets them wrap between words.
const camelBreaks = (s: string) => s.replace(/(?<=[a-z])(?=[A-Z])/g, '\u200b')

export function DashboardPage() {
  const { data: t, isLoading } = useApi('/api/tenant')
  const { data: stats } = useApi('/api/stats')
  useSetCrumb(t?.displayName)
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        {isLoading ? <Skeleton className="h-8 w-80" /> : <h1 className="text-2xl font-semibold tracking-tight">{t?.displayName}</h1>}
        {t && (
          <div className="flex flex-wrap items-center gap-x-4 text-muted-foreground">
            <Button variant="ghost" size="xs" className="-ml-2 font-mono font-normal text-muted-foreground" onClick={() => copy(t.tenantId, 'Tenant ID')} title="Copy tenant ID">
              {t.tenantId}
            </Button>
            <SourceIcon dirSync={t.dirSyncEnabled} />
          </div>
        )}
      </header>

      <div className="grid gap-4 xl:grid-cols-2">
        <UsersCard total={stats?.users} guestCount={stats?.guests} />
        <AppsCard sps={stats?.servicePrincipals} apps={stats?.applications} />
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-12">
        <div className="flex flex-col gap-4 xl:col-span-7">
          <AuthorizationPolicyCard ap={t?.authorizationPolicy ?? null} />
          <DomainsCard domains={t?.domains} />
        </div>
        <div className="flex flex-col gap-4 xl:col-span-5">
          <ConditionalAccessCard />
          <RolesCard />
          {t?.directorySettings.map((s) => (
            <Card key={s.name}>
              <CardHeader>
                <CardTitle>{s.name}</CardTitle>
              </CardHeader>
              <CardContent>
                <PropertyList plain items={s.values.map((v) => [camelBreaks(v.name), v.value] as [string, string])} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
