import { Fragment } from 'react'
import { Link } from 'react-router'
import {
  IconAdjustments,
  IconApps,
  IconBolt,
  IconChevronRight,
  IconCircleCheck,
  IconCircleCheckFilled,
  IconCircleMinus,
  IconClockHour4,
  IconCookie,
  IconDeviceDesktopCheck,
  IconEye,
  IconFileCertificate,
  IconFingerprint,
  IconKey,
  IconLockCheck,
  IconLockSquare,
  IconMinus,
  IconOctagonMinusFilled,
  IconPasswordUser,
  IconPlus,
  IconRefresh,
  IconServer2,
  IconShieldCheck,
  IconTilde,
  type Icon,
} from '@tabler/icons-react'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { PolicyStateBadge } from '@/components/badges'
import { ObjectLink } from '@/components/object-link'
import { useApi } from '@/api/client'
import type { MatchReason, ObjectRef, PolicyMatch, PolicyRow, PolicyTargetType } from '@/api/types'
import { cn } from '@/lib/utils'

// Grant and session controls arrive as free text (short in rows, long in details): match on keywords.
// Order matters: "Phishing-resistant MFA" is an authentication strength, not plain MFA.
const GRANT_ICONS: [RegExp, Icon][] = [
  [/strength/i, IconFingerprint],
  [/mfa|multifactor/i, IconShieldCheck],
  [/compliant/i, IconDeviceDesktopCheck],
  [/hybrid/i, IconServer2],
  [/terms/i, IconFileCertificate],
  [/password/i, IconPasswordUser],
  [/protection/i, IconLockCheck],
  [/approved|client app/i, IconApps],
]
const SESSION_ICONS: [RegExp, Icon][] = [
  [/frequency/i, IconClockHour4],
  [/persistent|browser/i, IconCookie],
  [/enforced restriction/i, IconLockSquare],
  [/app control|cloud app security/i, IconEye],
  [/continuous|cae/i, IconRefresh],
  [/token/i, IconKey],
]
const pick = (table: [RegExp, Icon][], text: string, fallback: Icon) => table.find(([re]) => re.test(text))?.[1] ?? fallback
export const grantIcon = (text: string) => pick(GRANT_ICONS, text, IconCircleCheck)
export const sessionIcon = (text: string) => pick(SESSION_ICONS, text, IconAdjustments)

/** Icon in front of a short label. */
export function IconText({ icon: I, children, className }: { icon: Icon; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex min-w-0 items-start gap-1.5', className)}>
      <I className="mt-[0.2em] size-4 shrink-0 text-muted-foreground" stroke={1.75} aria-hidden />
      <span>{children}</span>
    </span>
  )
}

/** The red stop sign that ends a blocking policy. */
export function BlockMark({ label = 'Block' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 font-semibold text-regulatory">
      <IconOctagonMinusFilled className="size-4.5 shrink-0" aria-hidden />
      {label}
    </span>
  )
}

/** Keywords (All users, All resources, Any location) are scopes, not objects: a chip, never a link. */
export function KeywordChip({ children }: { children: React.ReactNode }) {
  return (
    <Badge variant="outline" className="h-6 rounded-md px-2 text-sm font-medium">
      {children}
    </Badge>
  )
}

/** One reference inside a policy: keyword chip, plain value, or object link. */
export function PolicyRef({ value, icon, wrap }: { value: ObjectRef; icon?: (text: string) => Icon; wrap?: boolean }) {
  if (value.type === 'keyword') return <KeywordChip>{value.displayName}</KeywordChip>
  if (value.type === 'value') return icon ? <IconText icon={icon(value.displayName)}>{value.displayName}</IconText> : <span className="text-pretty">{value.displayName}</span>
  return <ObjectLink value={value} wrap={wrap} className="max-w-full" />
}

/** Grant controls as icon + word. `wrap` lets long labels break inside narrow table cells. */
export function grantSummary(p: PolicyRow, wrap = false) {
  if (p.block) return <BlockMark />
  if (p.grant.length === 0) return <span className="text-muted-foreground">Session only</span>
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      {p.grant.map((g, i) => (
        <Fragment key={g}>
          {i > 0 && <span className="text-sm text-muted-foreground">{p.grantOperator === 'AND' ? 'and' : 'or'}</span>}
          <IconText icon={grantIcon(g)} className={wrap ? undefined : 'whitespace-nowrap'}>
            {g}
          </IconText>
        </Fragment>
      ))}
    </span>
  )
}

/** Session controls: icons with a tooltip when compact, icon and label otherwise. */
export function SessionControls({ items, compact }: { items: string[]; compact?: boolean }) {
  if (items.length === 0) return null
  if (!compact)
    return (
      <ul className="flex flex-col gap-1">
        {items.map((s) => (
          <li key={s}>
            <IconText icon={sessionIcon(s)}>{s}</IconText>
          </li>
        ))}
      </ul>
    )
  return (
    <span className="inline-flex items-center gap-2">
      {items.map((s) => {
        const I = sessionIcon(s)
        return (
          <Tooltip key={s}>
            <TooltipTrigger asChild>
              <span tabIndex={0} className="rounded-sm text-muted-foreground hover:text-foreground">
                <I className="size-4.5" stroke={1.75} aria-label={s} />
              </span>
            </TooltipTrigger>
            <TooltipContent>{s}</TooltipContent>
          </Tooltip>
        )
      })}
    </span>
  )
}

function Hint({ icon: I, label, tip }: { icon: Icon; label: string; tip: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="warning" tabIndex={0} className="cursor-help">
          <I stroke={2} aria-hidden />
          {label}
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  )
}

function Reason({ r, excluded }: { r: MatchReason; excluded?: boolean }) {
  const Side = excluded ? IconMinus : IconPlus
  return (
    <li className="flex items-start gap-1.5">
      <Side className={cn('mt-1 size-4 shrink-0', excluded ? 'text-regulatory' : 'text-muted-foreground')} stroke={2.25} aria-label={excluded ? 'Excluded' : 'Included'} />
      <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1">
        {r.via.length === 0 ? (
          <span className="text-muted-foreground">Directly</span>
        ) : (
          r.via.map((v, j) => (
            <span key={j} className="inline-flex min-w-0 items-center gap-1.5">
              {j > 0 && <IconChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-label="then" />}
              <PolicyRef value={v} wrap />
            </span>
          ))
        )}
        {r.condition !== 'Users' && <span className="text-sm text-muted-foreground">({r.condition.toLowerCase()})</span>}
        {r.eligibleOnly && <Hint icon={IconBolt} label="If activated" tip="Only through an eligible PIM assignment. Applies once the role is activated." />}
        {r.approximate && <Hint icon={IconTilde} label="Approximate" tip="Matched from an approximation, for example guest status from the user type. The real evaluation may differ." />}
      </div>
    </li>
  )
}

/** Applies vs excluded. An inclusion that only holds through eligible or approximate matches is shown as conditional. */
function Effect({ m }: { m: PolicyMatch }) {
  if (m.effect === 'excluded')
    return (
      <span className="inline-flex items-center gap-1.5 font-medium text-regulatory">
        <IconCircleMinus className="size-4.5" stroke={2} aria-hidden />
        Excluded
      </span>
    )
  const conditional = m.included.length > 0 && m.included.every((r) => r.eligibleOnly || r.approximate)
  return (
    <span className={cn('inline-flex items-center gap-1.5 font-medium', conditional ? 'text-warning' : 'text-guide')}>
      {conditional ? <IconCircleCheck className="size-4.5" stroke={2} aria-hidden /> : <IconCircleCheckFilled className="size-4.5" aria-hidden />}
      {conditional ? 'May apply' : 'Applies'}
    </span>
  )
}

export function PolicyMatchList({ matches, showReasons = true }: { matches: PolicyMatch[]; showReasons?: boolean }) {
  if (matches.length === 0) return <p className="text-muted-foreground">No Conditional Access policy references this object.</p>
  return (
    <div className="glass overflow-hidden rounded-xl border">
      <Table>
        <TableHeader className="bg-shoulder">
          <TableRow className="hover:bg-transparent">
            <TableHead className="px-3 font-semibold text-ink">Effect</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Policy</TableHead>
            <TableHead className="px-3 font-semibold text-ink">State</TableHead>
            {showReasons && <TableHead className="px-3 font-semibold text-ink">Why</TableHead>}
            <TableHead className="px-3 font-semibold text-ink">Grant</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {matches.map((m) => (
            <TableRow key={m.policy.id} className={cn('align-top', m.effect === 'excluded' && 'bg-regulatory/4')}>
              <TableCell className="px-3 py-2.5">
                <Effect m={m} />
              </TableCell>
              <TableCell className={cn('px-3 py-2.5 whitespace-normal', showReasons ? 'min-w-52 max-w-72' : 'max-w-96')}>
                <ObjectLink value={{ id: m.policy.id, type: 'policy', displayName: m.policy.displayName }} wrap className="max-w-full" />
              </TableCell>
              <TableCell className="px-3 py-2.5">
                <PolicyStateBadge state={m.policy.state} />
              </TableCell>
              {showReasons && (
                <TableCell className="px-3 py-2.5 whitespace-normal">
                  <ul className="flex flex-col gap-1.5">
                    {m.excluded.map((r, i) => (
                      <Reason key={`e${i}`} r={r} excluded />
                    ))}
                    {m.included.map((r, i) => (
                      <Reason key={`i${i}`} r={r} />
                    ))}
                  </ul>
                </TableCell>
              )}
              <TableCell className="min-w-36 px-3 py-2.5 whitespace-normal">{grantSummary(m.policy, true)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** Policies tab of an object page. */
export function ObjectPolicies({ type, id }: { type: PolicyTargetType; id: string }) {
  const { data, isLoading } = useApi('/api/policies/affecting/{type}/{id}', { path: { type, id } })
  if (isLoading || !data) return <Skeleton className="h-32 w-full" />
  const excluded = data.filter((m) => m.effect === 'excluded').length
  const noun = type === 'servicePrincipal' ? 'service principal' : type
  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-[72ch] text-muted-foreground">
        {data.length - excluded} {data.length - excluded === 1 ? 'policy applies' : 'policies apply'} to this {noun}
        {excluded > 0 && `, ${excluded} ${excluded === 1 ? 'excludes' : 'exclude'} it`}. Only user and target scope are evaluated: platform, location and client app conditions still decide whether a
        sign-in is affected. <Link to="/policies" className="text-info hover:underline">All policies</Link>
      </p>
      <PolicyMatchList matches={data} />
    </div>
  )
}
