// Draft API spec (Phase 2). Phase 3 turns these into Pydantic models and
// replaces this file with re-exports from the generated schema.d.ts.

export type ObjectType =
  | 'user' | 'group' | 'device' | 'servicePrincipal' | 'application'
  | 'administrativeUnit' | 'role' | 'policy' | 'namedLocation'
  | 'keyword' | 'value' | 'unknown'

/** Every reference to an object, anywhere. `keyword`/`value`/`unknown` are not links. */
export interface ObjectRef {
  id: string | null
  type: ObjectType
  displayName: string
  /** Secondary identifier: UPN for users, appId for apps and SPs. */
  sub?: string | null
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface PageQuery {
  page?: number
  page_size?: number
  q?: string
  sort?: string
  order?: 'asc' | 'desc'
  /** Advanced filters, repeatable: `field:op:value`. For `in`/`notIn` the value is a comma list of URI-encoded items. */
  filter?: string[]
  /** How filters combine. Default all. */
  match?: 'all' | 'any'
}

// --- Advanced filtering ----------------------------------------------------

export type FilterType = 'text' | 'enum' | 'bool' | 'date' | 'number'
export type FilterOp = 'contains' | 'notContains' | 'eq' | 'ne' | 'startsWith' | 'endsWith' | 'empty' | 'notEmpty' | 'in' | 'notIn' | 'gt' | 'lt'

/** A field the list endpoint of a resource can filter on. */
export interface FilterField {
  key: string
  label: string
  type: FilterType
  /** Enum values present in the dump (at most 200). */
  options?: { value: string; label: string }[]
}

export type FilterResource =
  | 'users' | 'groups' | 'devices' | 'administrative-units' | 'service-principals' | 'applications'
  | 'roles' | 'role-assignments' | 'app-role-assignments' | 'oauth2-grants' | 'policies' | 'named-locations'
  | 'azure-role-assignments' | 'pim-assignments' | 'access-package-policies'

type Raw = Record<string, unknown>

// --- Users -----------------------------------------------------------------

export type MfaMethod = 'PhoneAppOTP' | 'PhoneAppNotification' | 'OneWaySms' | 'TwoWayVoiceMobile' | 'TwoWayVoiceOffice' | 'TwoWayVoiceAlternateMobile' | 'Email'

export interface MfaSummary {
  methods: MfaMethod[]
  defaultMethod: MfaMethod | null
  /** Legacy per-user MFA state: Enabled, Enforced or null. */
  perUserMfa: string | null
  fido: number
  windowsHello: number
}

export interface UserRow {
  id: string
  displayName: string
  userPrincipalName: string
  accountEnabled: boolean
  mail: string | null
  department: string | null
  jobTitle: string | null
  mobile: string | null
  lastPasswordChangeDateTime: string | null
  dirSyncEnabled: boolean | null
  userType: 'Member' | 'Guest'
  mfa: MfaSummary
}

export interface UserQuery extends PageQuery {
  userType?: 'Member' | 'Guest'
  accountEnabled?: boolean
  dirSyncEnabled?: boolean
  /** Users that are members of this group. */
  memberOf?: string
  /** With memberOf: include members of nested groups. */
  transitive?: boolean
  /** Users that own this object. */
  ownerOf?: string
  /** Users in this administrative unit. */
  memberOfAu?: string
  /** none = no strong auth method registered. */
  mfa?: 'none' | 'app' | 'phone' | 'fido' | 'windowsHello'
  perUserMfa?: 'Enabled' | 'Enforced' | 'Disabled'
  /** Leave out shared and room mailboxes (the MFA view). */
  excludeMailboxOnly?: boolean
}

export interface UserDetail extends UserRow {
  onPremisesSamAccountName?: string | null
  onPremisesSecurityIdentifier: string | null
  createdDateTime: string | null
  lastDirSyncTime: string | null
  counts: {
    memberOf: number
    roles: number
    ownedDevices: number
    ownedServicePrincipals: number
    ownedApplications: number
    ownedGroups: number
    administrativeUnits: number
    appRoleAssignments: number
    oauth2Grants: number
    policies: number
    azureRoles: number
    pim: number
    accessPackages: number
  }
  raw: Raw
}

// --- Groups ----------------------------------------------------------------

export interface GroupRow {
  id: string
  displayName: string
  description: string | null
  groupTypes: string[]
  securityEnabled: boolean
  mailEnabled: boolean
  mail: string | null
  isPublic: boolean | null
  isAssignableToRole: boolean | null
  membershipRule: string | null
  dirSyncEnabled: boolean | null
  createdDateTime: string | null
}

export interface GroupQuery extends PageQuery {
  /** Groups this object is a member of. */
  memberId?: string
  /** Child groups of this group. */
  memberOf?: string
  /** Groups owned by this object. */
  ownerId?: string
  transitive?: boolean
  isAssignableToRole?: boolean
  dynamic?: boolean
  kind?: 'security' | 'microsoft365'
  dirSyncEnabled?: boolean
  /** Groups in this administrative unit. */
  memberOfAu?: string
}

export interface GroupDetail extends GroupRow {
  pimEnabled: boolean
  securityIdentifier: string | null
  onPremisesSecurityIdentifier: string | null
  counts: {
    memberUsers: number
    transitiveMemberUsers: number
    memberGroups: number
    memberServicePrincipals: number
    memberDevices: number
    memberOf: number
    owners: number
    roles: number
    administrativeUnits: number
    appRoleAssignments: number
    policies: number
    azureRoles: number
  }
  raw: Raw
}

// --- Devices / administrative units ---------------------------------------

export interface DeviceRow {
  id: string
  displayName: string
  deviceId: string | null
  accountEnabled: boolean
  deviceManufacturer: string | null
  deviceModel: string | null
  deviceOSType: string | null
  deviceOSVersion: string | null
  deviceTrustType: string | null
  isCompliant: boolean | null
  isManaged: boolean | null
  isRooted: boolean | null
  dirSyncEnabled: boolean | null
}

export interface DeviceQuery extends PageQuery {
  memberOf?: string
  ownerId?: string
  memberOfAu?: string
  accountEnabled?: boolean
  isCompliant?: boolean
  isManaged?: boolean
  deviceTrustType?: string
  deviceOSType?: string
}

export interface BitLockerKey {
  keyIdentifier: string
  keyMaterial: string
  volumeType: string | null
  creationTime: string | null
}

export interface DeviceDetail extends DeviceRow {
  bitLockerKeys: BitLockerKey[]
  owners: ObjectRef[]
  counts: { owners: number; memberOf: number; administrativeUnits: number }
  raw: Raw
}

export interface AdministrativeUnitRow {
  id: string
  displayName: string
  description: string | null
  membershipRule: string | null
}

export interface AdministrativeUnitQuery extends PageQuery {
  memberId?: string
}

export interface AdministrativeUnitDetail extends AdministrativeUnitRow {
  counts: { memberUsers: number; memberGroups: number; memberDevices: number; scopedRoles: number }
  raw: Raw
}

// --- Service principals / applications ------------------------------------

export interface Credential {
  kind: 'password' | 'certificate'
  keyId: string
  displayName: string | null
  startDate: string | null
  endDate: string | null
}

export interface AppRoleDefinition {
  id: string
  value: string | null
  displayName: string
  description: string | null
  allowedMemberTypes: string[]
  isEnabled: boolean
}

export interface PermissionScopeDefinition {
  id: string
  value: string
  type: 'User' | 'Admin'
  adminConsentDisplayName: string | null
  adminConsentDescription: string | null
  userConsentDisplayName: string | null
  userConsentDescription: string | null
  isEnabled: boolean
}

export interface MetadataEntry {
  key: string
  /** Decoded value: JSON if it parses, text otherwise. */
  value: unknown
}

export interface ServicePrincipalRow {
  id: string
  displayName: string
  appId: string
  servicePrincipalType: string | null
  publisherName: string | null
  microsoftFirstParty: boolean | null
  accountEnabled: boolean
  appRoleAssignmentRequired: boolean | null
  passwordCount: number
  keyCount: number
  appRoleCount: number
  oauth2PermissionCount: number
  hasCustomOwner: boolean
}

export interface ServicePrincipalQuery extends PageQuery {
  memberOf?: string
  /** SPs owned by this object. */
  ownerId?: string
  /** SPs owning this object. */
  ownerOf?: string
  servicePrincipalType?: string
  microsoftFirstParty?: boolean
  accountEnabled?: boolean
  hasCredentials?: boolean
}

export interface ServicePrincipalDetail extends ServicePrincipalRow {
  appOwnerTenantId: string | null
  homepage: string | null
  replyUrls: string[]
  servicePrincipalNames: string[]
  application: ObjectRef | null
  credentials: Credential[]
  appRoles: AppRoleDefinition[]
  oauth2Permissions: PermissionScopeDefinition[]
  metadata: MetadataEntry[]
  counts: {
    owners: number
    memberOf: number
    roles: number
    appRoleAssignments: number
    appRoleAssignedTo: number
    oauth2GrantsAsClient: number
    oauth2GrantsAsResource: number
    policies: number
    azureRoles: number
  }
  raw: Raw
}

export interface ApplicationRow {
  id: string
  displayName: string
  appId: string
  availableToOtherTenants: boolean | null
  homepage: string | null
  publicClient: boolean | null
  oauth2AllowImplicitFlow: boolean | null
  passwordCount: number
  keyCount: number
  appRoleCount: number
  oauth2PermissionCount: number
  hasCustomOwner: boolean
}

export interface ApplicationQuery extends PageQuery {
  ownerId?: string
  availableToOtherTenants?: boolean
  publicClient?: boolean
  hasCredentials?: boolean
}

export interface RequiredResourceAccess {
  resource: ObjectRef
  permissions: { id: string; value: string; type: 'Role' | 'Scope' }[]
}

export interface ApplicationDetail extends ApplicationRow {
  servicePrincipal: ObjectRef | null
  replyUrls: string[]
  identifierUris: string[]
  credentials: Credential[]
  appRoles: AppRoleDefinition[]
  oauth2Permissions: PermissionScopeDefinition[]
  requiredResourceAccess: RequiredResourceAccess[]
  metadata: MetadataEntry[]
  counts: { owners: number; policies: number }
  raw: Raw
}

/** Owners of an object: users and service principals in one list. */
export interface OwnerQuery extends PageQuery {
  ownerOf: string
}

// --- Roles -----------------------------------------------------------------

export interface RoleRow {
  id: string
  templateId: string
  displayName: string
  description: string | null
  isBuiltIn: boolean
  /** Tier-0 / privileged role (fixed list of template IDs on the server). */
  isPrivileged: boolean
  activeCount: number
  eligibleCount: number
}

export interface RoleQuery extends PageQuery {
  isBuiltIn?: boolean
  hasAssignments?: boolean
}

export interface RoleDetail extends RoleRow {
  allowedResourceActions: string[]
  raw: Raw
}

export interface RoleAssignmentRow {
  id: string
  kind: 'active' | 'eligible'
  role: ObjectRef
  principal: ObjectRef
  /** Group the principal holds the role through, when expanded. */
  via: ObjectRef | null
  /** Directory (keyword), an administrative unit or an application. */
  scope: ObjectRef
  principalEnabled: boolean | null
  principalDirSync: boolean | null
  principalMfa: MfaSummary | null
}

export interface RoleAssignmentQuery extends PageQuery {
  roleId?: string
  principalId?: string
  /** With principalId: also roles held through groups. */
  transitive?: boolean
  /** List group members as principals (with via = the group). */
  expandGroups?: boolean
  scopeId?: string
  kind?: 'active' | 'eligible'
}

// --- Grants ----------------------------------------------------------------

export interface AppRoleAssignmentRow {
  id: string
  principal: ObjectRef
  resource: ObjectRef
  appRoleId: string
  /** Role value, or "Default access" for the zero GUID. */
  value: string
  description: string | null
  createdDateTime: string | null
}

export interface AppRoleAssignmentQuery extends PageQuery {
  principalId?: string
  resourceId?: string
  principalType?: 'User' | 'Group' | 'ServicePrincipal'
}

export interface OAuth2GrantRow {
  id: string
  consentType: 'AllPrincipals' | 'Principal'
  principal: ObjectRef | null
  client: ObjectRef
  resource: ObjectRef
  scopes: string[]
  expiryTime: string | null
}

export interface OAuth2GrantQuery extends PageQuery {
  clientId?: string
  resourceId?: string
  principalId?: string
  consentType?: 'AllPrincipals' | 'Principal'
}

// --- Governance ------------------------------------------------------------

export interface AzureRoleAssignmentRow {
  id: string
  kind: 'active' | 'eligible'
  role: { displayName: string; description: string | null; isBuiltIn: boolean }
  principal: ObjectRef
  via: ObjectRef | null
  scope: string
  conditional: boolean
}

export interface AzureRoleAssignmentQuery extends PageQuery {
  principalId: string
  transitive?: boolean
  kind?: 'active' | 'eligible'
}

export interface PimAssignmentRow {
  id: string
  kind: 'active' | 'eligible'
  resourceType: 'directoryRole' | 'group' | 'other'
  resource: ObjectRef
  /** Role name, or Member / Owner for groups. */
  role: string
  via: ObjectRef | null
  approvalRequired: boolean | null
  startDateTime: string | null
  /** null = permanent. */
  endDateTime: string | null
}

export interface PimSubject {
  subject: ObjectRef
  kind: 'active' | 'eligible'
  startDateTime: string | null
  endDateTime: string | null
}

export interface GroupPim {
  onboardedDateTime: string | null
  memberApprovalRequired: boolean | null
  ownerApprovalRequired: boolean | null
  members: PimSubject[]
  owners: PimSubject[]
}

export interface AccessPackagePolicyRow {
  id: string
  packageName: string
  packageDescription: string | null
  policyName: string
  resources: { kind: string; resource: ObjectRef; role: string | null }[]
  approvalRequired: boolean
  approvers: string[]
  durationDays: number | null
  renewable: boolean
  /** Why the user can request it: direct, a group, or a keyword like "All members". */
  via: ObjectRef
}

// --- Conditional Access ----------------------------------------------------

export type PolicyState = 'enabled' | 'reporting' | 'disabled'

export interface PolicyRow {
  id: string
  displayName: string
  state: PolicyState
  targetsAllUsers: boolean
  targetsAllApps: boolean
  block: boolean
  grant: string[]
  grantOperator: 'AND' | 'OR'
  sessionControls: string[]
  modifiedDateTime: string | null
  parseError: string | null
}

export interface PolicyQuery extends PageQuery {
  state?: PolicyState
  block?: boolean
}

export interface Condition {
  /** Key in the policy JSON, e.g. Users, Applications, Locations. */
  key: string
  label: string
  include: ObjectRef[]
  exclude: ObjectRef[]
}

export interface PolicyDetail extends PolicyRow {
  /** Users, workload identities. */
  who: Condition[]
  /** Applications, user actions, authentication contexts. */
  targets: Condition[]
  /** Platforms, locations, client apps, device filters, risks. */
  conditions: Condition[]
  /** Grant controls and authentication strengths, as value refs. */
  grantControls: ObjectRef[]
  session: ObjectRef[]
  counts: { inScope: number; excluded: number }
  raw: Raw
}

export interface PolicyUserQuery extends UserQuery {
  effect?: 'applies' | 'excluded'
}

/** Why a policy side (include or exclude) matches an object. */
export interface MatchReason {
  /** Condition label, e.g. Users, Directory roles, Resources. */
  condition: string
  /** Chain from the object to what the policy references, e.g. [group, parent group]. Empty = direct. */
  via: ObjectRef[]
  approximate: boolean
  /** Only through an eligible (PIM) role assignment. */
  eligibleOnly: boolean
}

/** One policy that concerns an object. Exclusion wins over inclusion. */
export interface PolicyMatch {
  policy: PolicyRow
  effect: 'included' | 'excluded'
  included: MatchReason[]
  excluded: MatchReason[]
}

export type PolicyTargetType = 'user' | 'group' | 'role' | 'servicePrincipal' | 'application'

export interface NamedLocationRow {
  id: string
  displayName: string
  kind: 'ip' | 'country'
  trusted: boolean
  ipRanges: string[]
  countries: string[]
  includeUnknownCountries: boolean
  policyCount: number
}

export interface NamedLocationDetail extends NamedLocationRow {
  policies: PolicyMatch[]
  raw: Raw
}

// --- Meta ------------------------------------------------------------------

export interface Stats {
  users: number
  guests: number
  groups: number
  devices: number
  servicePrincipals: number
  applications: number
  administrativeUnits: number
  roles: number
  policies: number
  namedLocations: number
}

export interface Tenant {
  displayName: string
  tenantId: string
  dirSyncEnabled: boolean | null
  domains: { name: string; type: string; capabilities: string[]; isDefault: boolean; isInitial: boolean }[]
  authorizationPolicy: {
    selfServicePasswordReset: boolean | null
    blockMsolPowerShell: boolean | null
    usersCanRegisterApps: boolean | null
    usersCanCreateSecurityGroups: boolean | null
    usersCanReadOtherUsers: boolean | null
    userConsent: string
    guestAccess: string
    guestInvites: string
    /** Machine-readable forms of the three strings above. */
    userConsentPolicy: 'none' | 'verifiedPublishers' | 'all'
    guestRole: 'member' | 'limited' | 'restricted'
    guestInvitesFrom: 'none' | 'admins' | 'adminsAndGuestInviters' | 'members' | 'everyone'
  } | null
  directorySettings: { name: string; values: { name: string; value: string }[] }[]
  raw: Raw
}

export interface SearchResult {
  groups: { type: ObjectType; total: number; items: ObjectRef[] }[]
}

// --- Route map: path template -> query and response ------------------------

export interface Routes {
  '/api/filters/{resource}': { query: object; res: FilterField[] }
  '/api/stats': { query: object; res: Stats }
  '/api/tenant': { query: object; res: Tenant }
  '/api/search': { query: { q: string; limit?: number }; res: SearchResult }
  '/api/users': { query: UserQuery; res: Page<UserRow> }
  '/api/users/{id}': { query: object; res: UserDetail }
  '/api/groups': { query: GroupQuery; res: Page<GroupRow> }
  '/api/groups/{id}': { query: object; res: GroupDetail }
  '/api/groups/{id}/pim': { query: object; res: GroupPim | null }
  '/api/devices': { query: DeviceQuery; res: Page<DeviceRow> }
  '/api/devices/{id}': { query: object; res: DeviceDetail }
  '/api/administrative-units': { query: AdministrativeUnitQuery; res: Page<AdministrativeUnitRow> }
  '/api/administrative-units/{id}': { query: object; res: AdministrativeUnitDetail }
  '/api/service-principals': { query: ServicePrincipalQuery; res: Page<ServicePrincipalRow> }
  '/api/service-principals/{id}': { query: object; res: ServicePrincipalDetail }
  '/api/applications': { query: ApplicationQuery; res: Page<ApplicationRow> }
  '/api/applications/{id}': { query: object; res: ApplicationDetail }
  '/api/owners': { query: OwnerQuery; res: Page<ObjectRef> }
  '/api/roles': { query: RoleQuery; res: Page<RoleRow> }
  '/api/roles/{id}': { query: object; res: RoleDetail }
  '/api/role-assignments': { query: RoleAssignmentQuery; res: Page<RoleAssignmentRow> }
  '/api/app-role-assignments': { query: AppRoleAssignmentQuery; res: Page<AppRoleAssignmentRow> }
  '/api/oauth2-grants': { query: OAuth2GrantQuery; res: Page<OAuth2GrantRow> }
  '/api/azure-role-assignments': { query: AzureRoleAssignmentQuery; res: Page<AzureRoleAssignmentRow> }
  '/api/pim-assignments': { query: PageQuery & { principalId: string; transitive?: boolean }; res: Page<PimAssignmentRow> }
  '/api/access-package-policies': { query: PageQuery & { userId: string }; res: Page<AccessPackagePolicyRow> }
  '/api/policies': { query: PolicyQuery; res: Page<PolicyRow> }
  '/api/policies/{id}': { query: object; res: PolicyDetail }
  '/api/policies/{id}/users': { query: PolicyUserQuery; res: Page<UserRow> }
  '/api/policies/affecting/{type}/{id}': { query: object; res: PolicyMatch[] }
  '/api/named-locations': { query: PageQuery; res: Page<NamedLocationRow> }
  '/api/named-locations/{id}': { query: object; res: NamedLocationDetail }
}

export type Route = keyof Routes
