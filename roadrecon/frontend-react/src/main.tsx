import { type ComponentType, lazy, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { AppShell } from '@/components/app-shell'
import './index.css'

// Each page module is a separate chunk, fetched on first visit (Suspense fallback in AppShell).
function page<M>(load: () => Promise<M>, name: keyof M) {
  const Page = lazy(() => load().then((m) => ({ default: m[name] as ComponentType })))
  return <Page />
}
const dashboard = () => import('@/pages/dashboard')
const users = () => import('@/pages/users')
const groups = () => import('@/pages/groups')
const devices = () => import('@/pages/devices')
const apps = () => import('@/pages/apps')
const roles = () => import('@/pages/roles')
const grants = () => import('@/pages/grants')
const policies = () => import('@/pages/policies')
const sql = () => import('@/pages/sql')

const queryClient = new QueryClient({
  // The dump never changes while the GUI runs.
  defaultOptions: { queries: { staleTime: Infinity, retry: 1, refetchOnWindowFocus: false } },
})

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: page(dashboard, 'DashboardPage') },
      { path: '/users', element: page(users, 'UsersPage') },
      { path: '/users/:id', element: page(users, 'UserPage') },
      { path: '/groups', element: page(groups, 'GroupsPage') },
      { path: '/groups/:id', element: page(groups, 'GroupPage') },
      { path: '/devices', element: page(devices, 'DevicesPage') },
      { path: '/devices/:id', element: page(devices, 'DevicePage') },
      { path: '/administrative-units', element: page(devices, 'AdministrativeUnitsPage') },
      { path: '/administrative-units/:id', element: page(devices, 'AdministrativeUnitPage') },
      { path: '/service-principals', element: page(apps, 'ServicePrincipalsPage') },
      { path: '/service-principals/:id', element: page(apps, 'ServicePrincipalPage') },
      { path: '/applications', element: page(apps, 'ApplicationsPage') },
      { path: '/applications/:id', element: page(apps, 'ApplicationPage') },
      { path: '/roles', element: page(roles, 'RolesPage') },
      { path: '/roles/:id', element: page(roles, 'RolePage') },
      { path: '/policies', element: page(policies, 'PoliciesPage') },
      { path: '/policies/:id', element: page(policies, 'PolicyPage') },
      { path: '/named-locations', element: page(policies, 'NamedLocationsPage') },
      { path: '/named-locations/:id', element: page(policies, 'NamedLocationPage') },
      { path: '/app-role-assignments', element: page(grants, 'AppRoleAssignmentsPage') },
      { path: '/oauth2-grants', element: page(grants, 'OAuth2GrantsPage') },
      { path: '/mfa', element: page(users, 'MfaPage') },
      { path: '/sql', element: page(sql, 'SqlPage') },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={300}>
          <RouterProvider router={router} />
          <Toaster position="bottom-right" />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
