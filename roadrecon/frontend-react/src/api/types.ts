// API types, generated from the backend spec (roadtools/roadrecon/api/models.py).
// Regenerate after a spec change:
//   podman compose run --rm py python -m roadtools.roadrecon.api --openapi roadrecon/frontend-react/openapi.json
//   podman compose run --rm node npm run gen:api
import type { components, paths } from './schema'

type S = components['schemas']

export type ObjectRef = S['ObjectRef']
export type ObjectType = ObjectRef['type']

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// --- Advanced filtering ----------------------------------------------------

export type FilterField = S['FilterField']
export type FilterType = FilterField['type']
export type FilterOp = 'contains' | 'notContains' | 'eq' | 'ne' | 'startsWith' | 'endsWith' | 'empty' | 'notEmpty' | 'in' | 'notIn' | 'gt' | 'lt'
export type FilterResource = paths['/api/filters/{resource}']['get']['parameters']['path']['resource']

// --- Objects ---------------------------------------------------------------

export type MfaSummary = S['MfaSummary']
export type MfaMethod = MfaSummary['methods'][number]
export type UserRow = S['UserRow']
export type UserDetail = S['UserDetail']
export type GroupRow = S['GroupRow']
export type GroupDetail = S['GroupDetail']
export type DeviceRow = S['DeviceRow']
export type BitLockerKey = S['BitLockerKey']
export type DeviceDetail = S['DeviceDetail']
export type AdministrativeUnitRow = S['AdministrativeUnitRow']
export type AdministrativeUnitDetail = S['AdministrativeUnitDetail']
export type Credential = S['Credential']
export type AppRoleDefinition = S['AppRoleDefinition']
export type PermissionScopeDefinition = S['PermissionScopeDefinition']
export type MetadataEntry = S['MetadataEntry']
export type ServicePrincipalRow = S['ServicePrincipalRow']
export type ServicePrincipalDetail = S['ServicePrincipalDetail']
export type ApplicationRow = S['ApplicationRow']
export type RequiredResourceAccess = S['RequiredResourceAccess']
export type ApplicationDetail = S['ApplicationDetail']
export type RoleRow = S['RoleRow']
export type RoleDetail = S['RoleDetail']
export type RoleAssignmentRow = S['RoleAssignmentRow']
export type AppRoleAssignmentRow = S['AppRoleAssignmentRow']
export type OAuth2GrantRow = S['OAuth2GrantRow']
export type AzureRoleAssignmentRow = S['AzureRoleAssignmentRow']
export type PimAssignmentRow = S['PimAssignmentRow']
export type PimSubject = S['PimSubject']
export type GroupPim = S['GroupPim']
export type AccessPackagePolicyRow = S['AccessPackagePolicyRow']
export type PolicyRow = S['PolicyRow']
export type PolicyState = PolicyRow['state']
export type Condition = S['Condition']
export type PolicyDetail = S['PolicyDetail']
export type MatchReason = S['MatchReason']
export type PolicyMatch = S['PolicyMatch']
export type PolicyTargetType = paths['/api/policies/affecting/{type}/{id}']['get']['parameters']['path']['type']
export type NamedLocationRow = S['NamedLocationRow']
export type NamedLocationDetail = S['NamedLocationDetail']
export type DeviceComplianceSettings = S['DeviceComplianceSettings']
export type CompliancePolicyRow = S['CompliancePolicyRow']
export type CompliancePolicyDetail = S['CompliancePolicyDetail']
export type Stats = S['Stats']
export type Tenant = S['Tenant']
export type SearchResult = S['SearchResult']
export type SqlResult = S['SqlResult']
export type SqlSchema = S['SqlSchema']

// --- Route map: path template -> query and response ------------------------

type Get<P extends keyof paths> = paths[P] extends { get: infer G } ? G : never
type QueryOf<G> = G extends { parameters: { query?: infer Q } } ? ([Q] extends [undefined] ? object : NonNullable<Q>) : object
type ResOf<G> = G extends { responses: { 200: { content: { 'application/json': infer R } } } } ? R : never

export type Routes = { [P in keyof paths]: { query: QueryOf<Get<P>>; res: ResOf<Get<P>> } }
export type Route = keyof Routes

export type PageQuery = Routes['/api/named-locations']['query']
export type UserQuery = Routes['/api/users']['query']
export type GroupQuery = Routes['/api/groups']['query']
export type DeviceQuery = Routes['/api/devices']['query']
export type AdministrativeUnitQuery = Routes['/api/administrative-units']['query']
export type ServicePrincipalQuery = Routes['/api/service-principals']['query']
export type ApplicationQuery = Routes['/api/applications']['query']
export type OwnerQuery = Routes['/api/owners']['query']
export type RoleQuery = Routes['/api/roles']['query']
export type RoleAssignmentQuery = Routes['/api/role-assignments']['query']
export type AppRoleAssignmentQuery = Routes['/api/app-role-assignments']['query']
export type OAuth2GrantQuery = Routes['/api/oauth2-grants']['query']
export type AzureRoleAssignmentQuery = Routes['/api/azure-role-assignments']['query']
export type PolicyQuery = Routes['/api/policies']['query']
export type PolicyUserQuery = Routes['/api/policies/{id}/users']['query']
