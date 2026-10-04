import { IconDeviceMobileMessage, IconFaceId, IconFingerprint, IconKey, IconMail, IconMessage2, IconPasswordMobilePhone, IconPhoneCall, IconShieldOff } from '@tabler/icons-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import type { MfaMethod, MfaSummary } from '@/api/types'
import { cn } from '@/lib/utils'

const METHODS: Record<MfaMethod, [React.ComponentType<{ className?: string }>, string]> = {
  PhoneAppNotification: [IconDeviceMobileMessage, 'Authenticator app notification'],
  PhoneAppOTP: [IconPasswordMobilePhone, 'Authenticator app code'],
  OneWaySms: [IconMessage2, 'Text message'],
  TwoWayVoiceMobile: [IconPhoneCall, 'Phone call (mobile)'],
  TwoWayVoiceAlternateMobile: [IconPhoneCall, 'Phone call (alternate mobile)'],
  TwoWayVoiceOffice: [IconPhoneCall, 'Phone call (office)'],
  Email: [IconMail, 'Email'],
}

function Mark({ icon: Icon, label, active }: { icon: React.ComponentType<{ className?: string }>; label: string; active?: boolean }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} aria-label={label} className={cn('rounded-sm p-0.5', active ? 'bg-ink text-paper' : 'text-ink/75')}>
          <Icon className="size-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent>{active ? `${label} (default)` : label}</TooltipContent>
    </Tooltip>
  )
}

/** Registered strong authentication methods; the default one is inverted. */
export function MfaMethods({ mfa }: { mfa: MfaSummary | null | undefined }) {
  if (!mfa) return null
  const none = mfa.methods.length === 0 && mfa.fido === 0 && mfa.windowsHello === 0
  if (none)
    return (
      <Badge variant="regulatory">
        <IconShieldOff /> No MFA
      </Badge>
    )
  return (
    <span className="inline-flex items-center gap-0.5">
      {mfa.methods.map((m) => {
        const [icon, label] = METHODS[m] ?? [IconKey, m]
        return <Mark key={m} icon={icon} label={label} active={m === mfa.defaultMethod} />
      })}
      {mfa.fido > 0 && <Mark icon={IconFingerprint} label={`FIDO2 security key${mfa.fido > 1 ? ` (${mfa.fido})` : ''}`} />}
      {mfa.windowsHello > 0 && <Mark icon={IconFaceId} label={`Windows Hello for Business${mfa.windowsHello > 1 ? ` (${mfa.windowsHello})` : ''}`} />}
    </span>
  )
}
