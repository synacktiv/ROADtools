import { IconAlertTriangle, IconBan, IconCheck, IconCircleCheckFilled, IconCircleX, IconClipboardX, IconCloud, IconMinus, IconServer2, IconShieldOff, type Icon } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { PolicyState } from '@/api/types'
import { useSettings } from '@/lib/settings'

export function PolicyStateBadge({ state }: { state: PolicyState }) {
  if (state === 'enabled') return <Badge variant="guide">Enabled</Badge>
  if (state === 'reporting') return <Badge variant="warning">Report-only</Badge>
  return <Badge variant="outline" className="text-muted-foreground">Disabled</Badge>
}

export function EnabledBadge({ enabled }: { enabled: boolean | null | undefined }) {
  return enabled === false ? <Badge variant="regulatory">Disabled</Badge> : <Badge variant="guide">Enabled</Badge>
}

export function KindBadge({ kind }: { kind: 'active' | 'eligible' }) {
  return kind === 'eligible' ? <Badge variant="warning">Eligible</Badge> : <Badge variant="outline">Active</Badge>
}

/** Red team: no approval is the interesting case. Blue team: the risky case is no approval too, but shown as a warning. */
export function ApprovalBadge({ required }: { required: boolean | null }) {
  const { blueTeam } = useSettings()
  if (required === null) return <span className="text-muted-foreground">Unknown</span>
  if (required) return <Badge variant="outline">Approval required</Badge>
  return <Badge variant={blueTeam ? 'regulatory' : 'guide'}>No approval</Badge>
}

/** Boolean cell: a check for true, a dash for false, nothing for unknown. */
export function BoolMark({ value }: { value: boolean | null | undefined }) {
  if (value === null || value === undefined) return null
  return value ? (
    <IconCheck className="size-4" stroke={2} aria-label="Yes" />
  ) : (
    <IconMinus className="size-4 text-muted-foreground/50" aria-label="No" />
  )
}

export function SourceText({ dirSync }: { dirSync: boolean | null | undefined }) {
  return <SourceIcon dirSync={dirSync} />
}

/**
 * Visual yes/no. `risky` marks the case worth attention: true = "yes is risky" (red check),
 * false = "no is risky" (red cross). Unset = neutral.
 */
export function Flag({ value, risky, label }: { value: boolean | null | undefined; risky?: boolean; label?: string }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">Unknown</span>
  const bad = risky === undefined ? false : value === risky
  const Icon = value ? IconCircleCheckFilled : IconCircleX
  return (
    <span className={cn('inline-flex items-center gap-1.5', bad ? 'text-regulatory' : value ? 'text-foreground' : 'text-muted-foreground')} title={label}>
      <Icon className="size-4" stroke={1.75} aria-hidden />
      <span>{value ? 'Yes' : 'No'}</span>
    </span>
  )
}

/** flag() returns null for unknown values so property lists skip the row. */
export const flag = (value: boolean | null | undefined, risky?: boolean) => (value === null || value === undefined ? null : <Flag value={value} risky={risky} />)

export function StatusDot({ enabled }: { enabled: boolean | null | undefined }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={cn('size-2 rounded-full', enabled === false ? 'bg-regulatory' : 'bg-guide')} aria-hidden />
      {enabled === false ? 'Disabled' : 'Enabled'}
    </span>
  )
}

export function SourceIcon({ dirSync, withLabel = true }: { dirSync: boolean | null | undefined; withLabel?: boolean }) {
  const Icon = dirSync ? IconServer2 : IconCloud
  const label = dirSync ? 'Synced from AD' : 'Cloud'
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center gap-1.5">
          <Icon className="size-4 text-muted-foreground" stroke={1.75} aria-hidden />
          {withLabel ? label : <span className="sr-only">{label}</span>}
        </span>
      </TooltipTrigger>
      {!withLabel && <TooltipContent>{label}</TooltipContent>}
    </Tooltip>
  )
}

/** Icon-only marker after a name; the label is in aria-label (not text) so the cell copy button copies only the name. */
export function Marker({ icon: I, label, className }: { icon: Icon; label: string; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label={label} className={cn('inline-flex shrink-0', className)}>
          <I className="size-4" stroke={1.75} aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

const STATUS = {
  disabled: [IconBan, 'Disabled'],
  noMfa: [IconShieldOff, 'No MFA registered'],
  notCompliant: [IconClipboardX, 'Not compliant'],
  risky: [IconAlertTriangle, 'Risky'],
} satisfies Record<string, [Icon, string]>

/** Status marker after a name, the same icon, colour and tooltip on every page. `label` refines the tooltip, `muted` tones it down. */
export function StatusMark({ status, label, muted }: { status: keyof typeof STATUS; label?: string; muted?: boolean }) {
  const [icon, text] = STATUS[status]
  return <Marker icon={icon} label={label ?? text} className={muted ? 'text-muted-foreground' : 'text-regulatory'} />
}
