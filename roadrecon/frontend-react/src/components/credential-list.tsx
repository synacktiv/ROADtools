import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { Credential } from '@/api/types'
import { fmtDate } from '@/lib/format'

const DAY = 86_400_000

export type ExpiryState = 'never' | 'expired' | 'soon' | 'valid'

/** Credential expiry state; soon = within 30 days. */
export function expiryState(end: string | null): ExpiryState {
  if (!end) return 'never'
  const left = new Date(end).getTime() - Date.now()
  return left < 0 ? 'expired' : left < 30 * DAY ? 'soon' : 'valid'
}

function Expiry({ end }: { end: string | null }) {
  if (!end) return <span className="text-muted-foreground">Never</span>
  const left = new Date(end).getTime() - Date.now()
  return (
    <span className="inline-flex items-center gap-2">
      {fmtDate(end)}
      {left < 0 ? <Badge variant="outline">Expired</Badge> : left < 30 * DAY ? <Badge variant="warning">Expires soon</Badge> : <Badge variant="guide">Valid</Badge>}
    </span>
  )
}

export function CredentialList({ items }: { items: Credential[] }) {
  if (items.length === 0) return <p className="text-muted-foreground">No passwords or certificates.</p>
  return (
    <div className="glass overflow-hidden rounded-xl border">
      <Table>
        <TableHeader className="bg-shoulder">
          <TableRow className="hover:bg-transparent">
            <TableHead className="px-3 font-semibold text-ink">Kind</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Description</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Key ID</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Valid from</TableHead>
            <TableHead className="px-3 font-semibold text-ink">Expires</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((c) => (
            <TableRow key={c.keyId}>
              <TableCell className="px-3">{c.kind === 'password' ? 'Client secret' : 'Certificate'}</TableCell>
              <TableCell className="px-3">{c.displayName ?? <span className="text-muted-foreground/60">·</span>}</TableCell>
              <TableCell className="px-3 font-mono text-xs">{c.keyId}</TableCell>
              <TableCell className="px-3">{fmtDate(c.startDate)}</TableCell>
              <TableCell className="px-3">
                <Expiry end={c.endDate} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
