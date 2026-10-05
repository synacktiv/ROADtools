import {
  IconAdjustments,
  IconAlertTriangle,
  IconApps,
  IconBrowser,
  IconCrown,
  IconDevices,
  IconFilter,
  IconHandClick,
  IconLock,
  IconMapPin,
  IconMinus,
  IconOctagonMinusFilled,
  IconRobot,
  IconRoute,
  IconUserExclamation,
  IconUsers,
  type Icon,
} from '@tabler/icons-react'
import { PolicyRef, grantIcon, sessionIcon } from '@/components/policy-match-list'
import type { Condition, ObjectRef, PolicyDetail } from '@/api/types'
import { cn } from '@/lib/utils'

// Looked up by label first (Directory roles share the Users key), then by policy JSON key.
const CONDITION_ICONS: Record<string, Icon> = {
  'Directory roles': IconCrown,
  Users: IconUsers,
  ServicePrincipals: IconRobot,
  Applications: IconApps,
  UserActions: IconHandClick,
  AuthenticationContext: IconLock,
  Locations: IconMapPin,
  DevicePlatforms: IconDevices,
  ClientTypes: IconBrowser,
  SignInRisks: IconAlertTriangle,
  UserRisks: IconUserExclamation,
  ServicePrincipalRisks: IconAlertTriangle,
  Devices: IconFilter,
  AuthenticationFlows: IconRoute,
}
const conditionIcon = (c: Condition) => CONDITION_ICONS[c.label] ?? CONDITION_ICONS[c.key] ?? IconAdjustments

const LINE = {
  enabled: { stroke: 'border-solid border-ink', dot: 'border-ink', grant: 'border-guide bg-guide' },
  reporting: { stroke: 'border-dashed border-warning', dot: 'border-warning', grant: 'border-warning bg-warning' },
  disabled: { stroke: 'border-dashed border-muted-foreground/50', dot: 'border-muted-foreground/50', grant: 'border-muted-foreground/50 bg-muted-foreground/50' },
}

/**
 * A policy drawn as a route: who → target resources → conditions → grant.
 * The line carries the state: solid when enforced, dashed amber when report-only, dashed grey when disabled.
 * Included items sit under the line; exclusions share one row below, so every exception lines up.
 * Exclusions hang off each stop as a dashed red detour. A block ends the line on a red stop; a grant lets it run on.
 * `compact`: tighter and smaller, for an expanded table row.
 */
export function PolicyFlow({ policy, compact }: { policy: PolicyDetail; compact?: boolean }) {
  const line = LINE[policy.state]
  return (
    <div
      className={cn(
        'grid grid-cols-1 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.1fr)] lg:grid-rows-[auto_auto_auto] lg:gap-y-0',
        compact ? 'gap-y-5 text-sm [--flow-gap:calc(var(--spacing)*2.5)]' : 'gap-y-8 [--flow-gap:calc(var(--spacing)*4)]',
      )}
    >
      <Stop label="Who" line={line} exclude={<Exclusions items={policy.who} />}>
        <Inclusions items={policy.who} empty="No users or workload identities" />
      </Stop>
      <Stop label="Target resources" line={line} exclude={<Exclusions items={policy.targets} />}>
        <Inclusions items={policy.targets} empty="No target resources" />
      </Stop>
      <Stop label="Conditions" line={line} exclude={<Exclusions items={policy.conditions} />}>
        <Inclusions items={policy.conditions} empty="Any platform, location, client app and risk level" />
      </Stop>
      <Stop label={policy.block ? 'Block' : 'Grant'} line={line} end={policy.block ? 'block' : 'grant'}>
        {policy.block ? (
          !compact && <p className="text-pretty text-muted-foreground">Access is denied when every condition matches.</p>
        ) : (
          <Block title={policy.grantControls.length > 1 ? (policy.grantOperator === 'AND' ? 'Require all of' : 'Require one of') : 'Require'}>
            <Refs items={policy.grantControls} icon={grantIcon} empty="No grant control" />
            {policy.authenticationStrengths.map((s) => (
              <Strength key={s.id} strength={s} />
            ))}
          </Block>
        )}
        {policy.session.length > 0 && (
          <Block title="Session">
            <Refs items={policy.session} icon={sessionIcon} />
          </Block>
        )}
      </Stop>
    </div>
  )
}

function Stop({ label, line, end, exclude, children }: { label: string; line: (typeof LINE)['enabled']; end?: 'block' | 'grant'; exclude?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-(--flow-gap) lg:row-span-3 lg:grid lg:grid-cols-[minmax(0,1fr)] lg:grid-rows-subgrid lg:gap-0">
      <h3 className="flex h-6 items-center gap-2 font-semibold">
        {end === 'block' ? (
          <IconOctagonMinusFilled className="size-5 shrink-0 text-regulatory" aria-hidden />
        ) : (
          <span className={cn('size-3 shrink-0 rounded-full border-2', end === 'grant' ? line.grant : line.dot)} aria-hidden />
        )}
        <span className={cn('shrink-0', end === 'block' && 'text-regulatory')}>{label}</span>
        {end !== 'block' && <span className={cn('h-0 flex-1 border-t-2', line.stroke)} aria-hidden />}
      </h3>
      <div className="flex flex-col gap-(--flow-gap) pl-5 lg:pt-(--flow-gap) lg:pr-5">{children}</div>
      <div className="pl-[5px] empty:hidden lg:pt-[calc(var(--flow-gap)*1.5)] lg:pr-5">{exclude}</div>
    </section>
  )
}

function Inclusions({ items, empty }: { items: Condition[]; empty: string }) {
  if (items.length === 0) return <p className="text-muted-foreground">{empty}</p>
  return items.map((c) => (
    <Block key={c.key + c.label} title={c.label} icon={conditionIcon(c)}>
      <Refs items={c.include} empty="None" />
    </Block>
  ))
}

/** Exceptions: a dashed red detour off the route. */
function Exclusions({ items }: { items: Condition[] }) {
  const excl = items.filter((c) => c.exclude.length > 0)
  if (excl.length === 0) return null
  return (
    <div className="flex flex-col gap-(--flow-gap)">
      {excl.map((c) => (
        <div key={c.key + c.label} className="flex flex-col gap-1.5 border-l-2 border-dashed border-regulatory/60 pl-3">
          <span className="inline-flex items-center gap-1.5 text-sm font-medium text-regulatory">
            <IconMinus className="size-4" stroke={2.25} aria-hidden />
            Excluded {c.label.toLowerCase()}
          </span>
          <Refs items={c.exclude} />
        </div>
      ))}
    </div>
  )
}

function Block({ title, icon: I, children }: { title: string; icon?: Icon; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
        {I && <I className="size-4" stroke={1.75} aria-hidden />}
        {title}
      </span>
      {children}
    </div>
  )
}

/** What an authentication strength accepts. An unresolved custom one (no type-44 row collected) has no combinations:
 * counted as MFA, approximately. Built-in and resolved custom strengths list their combinations. */
function Strength({ strength: s }: { strength: PolicyDetail['authenticationStrengths'][number] }) {
  if (!s.builtIn && s.combinations.length === 0)
    return <p className="text-sm text-pretty text-warning">Custom authentication strength: combinations not collected, counted as MFA.</p>
  return (
    <details className="text-sm text-muted-foreground">
      <summary className="cursor-pointer hover:text-foreground">
        {s.displayName}: {s.combinations.length} allowed combinations
      </summary>
      <ul className="mt-1 flex flex-col gap-0.5 pl-4">
        {s.combinations.map((c) => (
          <li key={c}>{c}</li>
        ))}
      </ul>
    </details>
  )
}

function Refs({ items, empty, icon }: { items: ObjectRef[]; empty?: string; icon?: (text: string) => Icon }) {
  if (items.length === 0) return empty ? <span className="text-muted-foreground">{empty}</span> : null
  return (
    <ul className="flex flex-col items-start gap-1.5">
      {items.map((r, i) => (
        <li key={`${r.id ?? r.displayName}-${i}`} className="max-w-full min-w-0">
          <PolicyRef value={r} icon={icon} wrap />
        </li>
      ))}
    </ul>
  )
}
