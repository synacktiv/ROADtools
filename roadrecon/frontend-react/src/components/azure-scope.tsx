// Port of the old GUI's utils.parseAzureScope.
export function parseAzureScope(scope: string) {
  const p = scope.split('/').filter(Boolean)
  const at = (k: string) => {
    const i = p.findIndex((s) => s.toLowerCase() === k.toLowerCase())
    return i >= 0 ? p[i + 1] : undefined
  }
  if (p.length === 0) return { type: 'Root', name: '/' }
  if (at('managementGroups')) return { type: 'Management group', name: at('managementGroups')! }
  const sub = at('subscriptions')
  const rg = at('resourceGroups')
  const prov = p.indexOf('providers')
  if (prov >= 0 && rg) return { type: 'Resource', name: p.slice(prov + 1).join('/'), subscription: sub, resourceGroup: rg }
  if (rg) return { type: 'Resource group', name: rg, subscription: sub }
  return { type: 'Subscription', name: sub ?? scope }
}

export function AzureScope({ scope, hideType }: { scope: string; hideType?: boolean }) {
  const s = parseAzureScope(scope)
  return (
    <span className="inline-flex min-w-0 flex-col" title={scope}>
      <span>
        {!hideType && <span className="text-muted-foreground">{s.type} </span>}<span className="font-mono text-xs">{s.name}</span>
      </span>
      {(s.subscription && s.type !== 'Subscription') && (
        <span className="truncate font-mono text-xs text-muted-foreground">
          {s.subscription}
          {s.resourceGroup && s.type === 'Resource' ? ` / ${s.resourceGroup}` : ''}
        </span>
      )}
    </span>
  )
}
