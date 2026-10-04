import { IconCopy } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { copy } from '@/lib/copy'

export type Property = [label: string, value: React.ReactNode, opts?: { mono?: boolean; copy?: string }]

/** Label / value grid. Rows with an empty value are skipped. */
/**
 * Label / value pairs. Rows with an empty value are skipped.
 * `rows`: glass panel with label and value side by side. `plain`: same, without the panel (inside a card).
 * `stacked`: label above value, for the object page side panel.
 */
export function PropertyList({ items, plain, layout = 'rows' }: { items: Property[]; plain?: boolean; layout?: 'rows' | 'stacked' }) {
  const shown = items.filter(([, v]) => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0))
  const copyButton = (label: string, text?: string) =>
    text && (
      <Button variant="ghost" size="icon-xs" className="-my-0.5 text-muted-foreground" onClick={() => copy(text, label)} aria-label={`Copy ${label}`}>
        <IconCopy />
      </Button>
    )
  if (layout === 'stacked')
    return (
      <dl className="flex flex-col divide-y">
        {shown.map(([label, value, opts]) => (
          <div key={label} className="flex flex-col gap-1 py-2.5">
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className={`flex min-w-0 items-start justify-between gap-2 break-words ${opts?.mono ? 'font-mono text-sm' : ''}`}>
              <div className="min-w-0">{Array.isArray(value) ? <List items={value} /> : value}</div>
              {copyButton(label, opts?.copy)}
            </dd>
          </div>
        ))}
      </dl>
    )
  return (
    <dl className={plain ? '' : 'glass max-w-4xl rounded-xl border px-4'}>
      {shown.map(([label, value, opts]) => (
        <div key={label} className="flex gap-6 border-b py-2.5 last:border-b-0">
          <dt className={`shrink-0 text-muted-foreground ${plain ? 'w-48' : 'w-56'}`}>{label}</dt>
          <dd className={`flex min-w-0 flex-1 items-start gap-2 break-words ${opts?.mono ? 'font-mono text-sm' : ''}`}>
            <div className="min-w-0">{Array.isArray(value) ? <List items={value} /> : value}</div>
            {copyButton(label, opts?.copy)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function List({ items }: { items: React.ReactNode[] }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((v, i) => (
        <li key={i} className="font-mono text-sm leading-6">
          {v}
        </li>
      ))}
    </ul>
  )
}
