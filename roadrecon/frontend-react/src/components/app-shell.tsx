import { useEffect, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { useTheme } from 'next-themes'
import { type Icon, IconFingerprint, IconKey, IconLayoutDashboard, IconMoon, IconSearch, IconSun, IconTerminal2, IconTicket } from '@tabler/icons-react'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { Breadcrumb, BreadcrumbItem, BreadcrumbLink, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import { Kbd } from '@/components/ui/kbd'
import { Separator } from '@/components/ui/separator'
import { CommandDialog, Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { ObjectLink, TYPE_LABEL, TypeGlyph, objectHref } from '@/components/object-link'
import { useApi } from '@/api/client'
import type { ObjectType, Stats } from '@/api/types'
import { useCrumb } from '@/lib/crumb'
import logo from '@/assets/roadrecon-logo.svg'
import { fmtNumber } from '@/lib/format'

interface NavItem {
  to: string
  label: string
  type?: ObjectType
  icon?: Icon
  stat?: keyof Stats
}

export const NAV: { label?: string; items: NavItem[] }[] = [
  { items: [{ to: '/', label: 'Overview', icon: IconLayoutDashboard }] },
  {
    label: 'Directory',
    items: [
      { to: '/users', label: 'Users', type: 'user', stat: 'users' },
      { to: '/groups', label: 'Groups', type: 'group', stat: 'groups' },
      { to: '/devices', label: 'Devices', type: 'device', stat: 'devices' },
      { to: '/administrative-units', label: 'Administrative units', type: 'administrativeUnit', stat: 'administrativeUnits' },
    ],
  },
  {
    label: 'Applications',
    items: [
      { to: '/service-principals', label: 'Service principals', type: 'servicePrincipal', stat: 'servicePrincipals' },
      { to: '/applications', label: 'Applications', type: 'application', stat: 'applications' },
      { to: '/app-role-assignments', label: 'App role assignments', icon: IconTicket },
      { to: '/oauth2-grants', label: 'OAuth2 grants', icon: IconKey },
    ],
  },
  {
    label: 'Access',
    items: [
      { to: '/roles', label: 'Directory roles', type: 'role', stat: 'roles' },
      { to: '/policies', label: 'Conditional Access', type: 'policy', stat: 'policies' },
      { to: '/named-locations', label: 'Named locations', type: 'namedLocation', stat: 'namedLocations' },
      { to: '/mfa', label: 'MFA', icon: IconFingerprint },
    ],
  },
  { label: 'Tools', items: [{ to: '/sql', label: 'SQL query', icon: IconTerminal2 }] },
]

const SECTIONS = Object.fromEntries(NAV.flatMap((g) => g.items).map((i) => [i.to, i.label]))

export function AppShell() {
  const { data: stats } = useApi('/api/stats')
  const { pathname } = useLocation()
  const [paletteOpen, setPaletteOpen] = useState(false)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <SidebarProvider style={{ "--sidebar-width": "17.5rem" } as React.CSSProperties}>
      <Sidebar variant="inset">
        <SidebarHeader className="px-4 pt-5 pb-3">
          <Link to="/" className="flex items-center gap-3 text-[1.05rem] font-semibold tracking-tight">
            <img src={logo} alt="" className="h-8 w-auto" />
            ROADrecon
          </Link>
        </SidebarHeader>
        <SidebarContent>
          {NAV.map((g, i) => (
            <SidebarGroup key={i} className="py-1.5">
              {g.label && <SidebarGroupLabel className="px-3 text-[0.8rem]">{g.label}</SidebarGroupLabel>}
              <SidebarMenu>
                {g.items.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild isActive={item.to === '/' ? pathname === '/' : pathname.startsWith(item.to)} className="h-10 gap-3 px-3 text-[0.95rem] font-normal data-[active=true]:font-medium [&>svg]:size-[1.15rem]">
                      <Link to={item.to}>
                        {item.type ? <TypeGlyph type={item.type} className="size-[1.15rem]" /> : item.icon && <item.icon className="size-[1.15rem]" stroke={1.75} />}
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                    {item.stat && stats && <SidebarMenuBadge className="top-2.5! text-[0.8rem] font-normal text-muted-foreground tabular-nums">{fmtNumber(stats[item.stat])}</SidebarMenuBadge>}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroup>
          ))}
        </SidebarContent>
      </Sidebar>
      <SidebarInset className="min-w-0 bg-background/50 backdrop-blur-2xl md:peer-data-[variant=inset]:shadow-none md:peer-data-[variant=inset]:ring-1 md:peer-data-[variant=inset]:ring-border">
        <header className="sticky top-0 z-10 flex h-13 items-center gap-2 border-b px-4 backdrop-blur-xl md:rounded-t-xl">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
          <Crumbs />
          <Button variant="outline" size="sm" className="ml-auto w-64 justify-start gap-2 bg-transparent text-muted-foreground" onClick={() => setPaletteOpen(true)}>
            <IconSearch className="size-4" />
            Search the dump
            <Kbd className="ml-auto">Ctrl K</Kbd>
          </Button>
          <ThemeToggle />
        </header>
        {/* Keyed by path: each page fades in once when opened, not on filter or tab changes. */}
        <div key={pathname} className="min-w-0 px-6 py-6 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300">
          <Outlet />
        </div>
      </SidebarInset>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </SidebarProvider>
  )
}

function Crumbs() {
  const { pathname } = useLocation()
  const crumb = useCrumb()
  const base = '/' + (pathname.split('/')[1] ?? '')
  const section = SECTIONS[base] ?? null
  const isDetail = pathname.split('/').filter(Boolean).length > 1
  return (
    <Breadcrumb>
      <BreadcrumbList>
        {isDetail && section ? (
          <>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to={base}>{section}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage className="max-w-96 truncate">{crumb ?? '…'}</BreadcrumbPage>
            </BreadcrumbItem>
          </>
        ) : (
          <BreadcrumbItem>
            <BreadcrumbPage>{section ?? 'Overview'}</BreadcrumbPage>
          </BreadcrumbItem>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme === 'dark'
  return (
    <Button variant="ghost" size="icon-sm" aria-label={dark ? 'Use light theme' : 'Use dark theme'} onClick={() => setTheme(dark ? 'light' : 'dark')}>
      {dark ? <IconSun /> : <IconMoon />}
    </Button>
  )
}

function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 150)
    return () => clearTimeout(t)
  }, [text])
  const { data } = useApi('/api/search', { query: { q, limit: 6 } }, q.length >= 2)
  const go = (to: string) => {
    onOpenChange(false)
    setText('')
    navigate(to)
  }
  return (
    <CommandDialog className="sm:max-w-2xl" open={open} onOpenChange={onOpenChange} title="Search the dump" description="Find any object by name, UPN, app ID or object ID">
      <Command shouldFilter={false}>
        <CommandInput value={text} onValueChange={setText} placeholder="Name, UPN, app ID or object ID" />
        <CommandList className="max-h-[28rem]">
          {q.length >= 2 && <CommandEmpty>Nothing matches “{q}”.</CommandEmpty>}
          {q.length < 2 &&
            NAV.map((g, i) => (
              <CommandGroup key={i} heading={g.label ?? 'Go to'}>
                {g.items.map((item) => (
                  <CommandItem key={item.to} value={item.to} onSelect={() => go(item.to)}>
                    {item.type ? <TypeGlyph type={item.type} /> : item.icon && <item.icon className="size-4" stroke={1.75} />}
                    {item.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          {q.length >= 2 &&
            data?.groups
              .filter((g) => g.items.length > 0)
              .map((g) => (
                <CommandGroup key={g.type} heading={`${TYPE_LABEL[g.type]}s${g.total > g.items.length ? ` (${fmtNumber(g.total)})` : ''}`}>
                  {g.items.map((r) => (
                    <CommandItem key={r.id} value={`${g.type}:${r.id}`} onSelect={() => go(objectHref(r)!)}>
                      <ObjectLink value={{ ...r, id: null }} sub className="pointer-events-none" />
                    </CommandItem>
                  ))}
                </CommandGroup>
              ))}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
