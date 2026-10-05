import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Toaster } from '@/components/ui/sonner'
import { AppShell } from '@/components/app-shell'
import { DashboardPage } from '@/pages/dashboard'
import { MfaPage, UserPage, UsersPage } from '@/pages/users'
import { GroupPage, GroupsPage } from '@/pages/groups'
import { AdministrativeUnitPage, AdministrativeUnitsPage, DevicePage, DevicesPage } from '@/pages/devices'
import { ApplicationPage, ApplicationsPage, ServicePrincipalPage, ServicePrincipalsPage } from '@/pages/apps'
import { RolePage, RolesPage } from '@/pages/roles'
import { AppRoleAssignmentsPage, OAuth2GrantsPage } from '@/pages/grants'
import { NamedLocationPage, NamedLocationsPage, PoliciesPage, PolicyPage } from '@/pages/policies'
import { SqlPage } from '@/pages/sql'
import './index.css'

const queryClient = new QueryClient({
  // The dump never changes while the GUI runs.
  defaultOptions: { queries: { staleTime: Infinity, retry: 1, refetchOnWindowFocus: false } },
})

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: '/', element: <DashboardPage /> },
      { path: '/users', element: <UsersPage /> },
      { path: '/users/:id', element: <UserPage /> },
      { path: '/groups', element: <GroupsPage /> },
      { path: '/groups/:id', element: <GroupPage /> },
      { path: '/devices', element: <DevicesPage /> },
      { path: '/devices/:id', element: <DevicePage /> },
      { path: '/administrative-units', element: <AdministrativeUnitsPage /> },
      { path: '/administrative-units/:id', element: <AdministrativeUnitPage /> },
      { path: '/service-principals', element: <ServicePrincipalsPage /> },
      { path: '/service-principals/:id', element: <ServicePrincipalPage /> },
      { path: '/applications', element: <ApplicationsPage /> },
      { path: '/applications/:id', element: <ApplicationPage /> },
      { path: '/roles', element: <RolesPage /> },
      { path: '/roles/:id', element: <RolePage /> },
      { path: '/policies', element: <PoliciesPage /> },
      { path: '/policies/:id', element: <PolicyPage /> },
      { path: '/named-locations', element: <NamedLocationsPage /> },
      { path: '/named-locations/:id', element: <NamedLocationPage /> },
      { path: '/app-role-assignments', element: <AppRoleAssignmentsPage /> },
      { path: '/oauth2-grants', element: <OAuth2GrantsPage /> },
      { path: '/mfa', element: <MfaPage /> },
      { path: '/sql', element: <SqlPage /> },
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
