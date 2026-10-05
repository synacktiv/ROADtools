"""API spec: response models and query models.

The frontend types are generated from the OpenAPI schema of these models
(`frontend-react/src/api/schema.d.ts`), so names and optionality here are the contract.
"""
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar('T')
Raw = dict[str, Any]
Kind = Literal['active', 'eligible']

ObjectType = Literal[
    'user', 'group', 'device', 'servicePrincipal', 'application',
    'administrativeUnit', 'role', 'policy', 'namedLocation',
    'keyword', 'value', 'unknown',
]


class ObjectRef(BaseModel):
    """Every reference to an object, anywhere. `keyword`/`value`/`unknown` are not links."""
    id: str | None
    type: ObjectType
    displayName: str
    sub: str | None = Field(None, description='Secondary identifier: UPN for users, appId for apps and SPs.')


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PageQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=500)
    q: str | None = None
    sort: str | None = None
    order: Literal['asc', 'desc'] = 'asc'
    filter: list[str] = Field([], description='Advanced filters, repeatable: `field:op:value`. '
                              'For `in`/`notIn` the value is a comma list of URI-encoded items.')
    match: Literal['all', 'any'] = Field('all', description='How filters combine.')


# --- Advanced filtering ------------------------------------------------------

FilterType = Literal['text', 'enum', 'bool', 'date', 'number']
FilterOp = Literal['contains', 'notContains', 'eq', 'ne', 'startsWith', 'endsWith',
                   'empty', 'notEmpty', 'in', 'notIn', 'gt', 'lt']
FilterResource = Literal[
    'users', 'groups', 'devices', 'administrative-units', 'service-principals', 'applications',
    'roles', 'role-assignments', 'app-role-assignments', 'oauth2-grants', 'policies', 'named-locations',
    'azure-role-assignments', 'pim-assignments', 'access-package-policies',
]


class FilterOption(BaseModel):
    value: str
    label: str


class FilterField(BaseModel):
    """A field the list endpoint of a resource can filter on."""
    key: str
    label: str
    type: FilterType
    options: list[FilterOption] | None = Field(None, description='Enum values present in the dump (at most 200).')


# --- Users -------------------------------------------------------------------

MfaMethod = Literal['PhoneAppOTP', 'PhoneAppNotification', 'OneWaySms', 'TwoWayVoiceMobile',
                    'TwoWayVoiceOffice', 'TwoWayVoiceAlternateMobile', 'Email']


class MfaSummary(BaseModel):
    methods: list[MfaMethod]
    defaultMethod: MfaMethod | None
    perUserMfa: str | None = Field(description='Legacy per-user MFA state: Enabled, Enforced or null.')
    fido: int
    windowsHello: int


class UserRow(BaseModel):
    id: str
    displayName: str
    userPrincipalName: str
    accountEnabled: bool
    mail: str | None
    department: str | None
    jobTitle: str | None
    mobile: str | None
    lastPasswordChangeDateTime: str | None
    dirSyncEnabled: bool | None
    userType: Literal['Member', 'Guest']
    mfa: MfaSummary


class UserQuery(PageQuery):
    userType: Literal['Member', 'Guest'] | None = None
    accountEnabled: bool | None = None
    dirSyncEnabled: bool | None = None
    memberOf: str | None = Field(None, description='Users that are members of this group.')
    transitive: bool | None = Field(None, description='With memberOf: include members of nested groups.')
    ownerOf: str | None = Field(None, description='Users that own this object.')
    memberOfAu: str | None = Field(None, description='Users in this administrative unit.')
    mfa: Literal['none', 'app', 'phone', 'fido', 'windowsHello'] | None = Field(
        None, description='none = no strong auth method registered.')
    perUserMfa: Literal['Enabled', 'Enforced', 'Disabled'] | None = None
    excludeMailboxOnly: bool | None = Field(None, description='Leave out shared and room mailboxes (the MFA view).')


class UserCounts(BaseModel):
    memberOf: int
    roles: int
    ownedDevices: int
    ownedServicePrincipals: int
    ownedApplications: int
    ownedGroups: int
    administrativeUnits: int
    appRoleAssignments: int
    oauth2Grants: int
    policies: int
    azureRoles: int
    pim: int
    accessPackages: int


class UserDetail(UserRow):
    onPremisesSamAccountName: str | None = None
    onPremisesSecurityIdentifier: str | None
    createdDateTime: str | None
    lastDirSyncTime: str | None
    counts: UserCounts
    raw: Raw


# --- Groups ------------------------------------------------------------------

class GroupRow(BaseModel):
    id: str
    displayName: str
    description: str | None
    groupTypes: list[str]
    securityEnabled: bool
    mailEnabled: bool
    mail: str | None
    isPublic: bool | None
    isAssignableToRole: bool | None
    membershipRule: str | None
    dirSyncEnabled: bool | None
    createdDateTime: str | None


class GroupQuery(PageQuery):
    memberId: str | None = Field(None, description='Groups this object is a member of.')
    memberOf: str | None = Field(None, description='Child groups of this group.')
    ownerId: str | None = Field(None, description='Groups owned by this object.')
    transitive: bool | None = None
    isAssignableToRole: bool | None = None
    dynamic: bool | None = None
    kind: Literal['security', 'microsoft365'] | None = None
    dirSyncEnabled: bool | None = None
    memberOfAu: str | None = Field(None, description='Groups in this administrative unit.')


class GroupCounts(BaseModel):
    memberUsers: int
    transitiveMemberUsers: int
    memberGroups: int
    memberServicePrincipals: int
    memberDevices: int
    memberOf: int
    owners: int
    roles: int
    administrativeUnits: int
    appRoleAssignments: int
    policies: int
    azureRoles: int


class GroupDetail(GroupRow):
    pimEnabled: bool
    securityIdentifier: str | None
    onPremisesSecurityIdentifier: str | None
    counts: GroupCounts
    raw: Raw


# --- Devices / administrative units -----------------------------------------

class DeviceRow(BaseModel):
    id: str
    displayName: str
    deviceId: str | None
    accountEnabled: bool
    deviceManufacturer: str | None
    deviceModel: str | None
    deviceOSType: str | None
    deviceOSVersion: str | None
    deviceTrustType: str | None
    isCompliant: bool | None
    isManaged: bool | None
    isRooted: bool | None
    dirSyncEnabled: bool | None


class DeviceQuery(PageQuery):
    memberOf: str | None = None
    ownerId: str | None = None
    memberOfAu: str | None = None
    accountEnabled: bool | None = None
    isCompliant: bool | None = None
    isManaged: bool | None = None
    deviceTrustType: str | None = None
    deviceOSType: str | None = None


class BitLockerKey(BaseModel):
    keyIdentifier: str
    keyMaterial: str
    volumeType: str | None
    creationTime: str | None


class DeviceCounts(BaseModel):
    owners: int
    memberOf: int
    administrativeUnits: int


class DeviceDetail(DeviceRow):
    bitLockerKeys: list[BitLockerKey]
    owners: list[ObjectRef]
    counts: DeviceCounts
    raw: Raw


class AdministrativeUnitRow(BaseModel):
    id: str
    displayName: str
    description: str | None
    membershipRule: str | None


class AdministrativeUnitQuery(PageQuery):
    memberId: str | None = None


class AdministrativeUnitCounts(BaseModel):
    memberUsers: int
    memberGroups: int
    memberDevices: int
    scopedRoles: int


class AdministrativeUnitDetail(AdministrativeUnitRow):
    counts: AdministrativeUnitCounts
    raw: Raw


# --- Service principals / applications --------------------------------------

class Credential(BaseModel):
    kind: Literal['password', 'certificate']
    keyId: str
    displayName: str | None
    startDate: str | None
    endDate: str | None


class AppRoleDefinition(BaseModel):
    id: str
    value: str | None
    displayName: str
    description: str | None
    allowedMemberTypes: list[str]
    isEnabled: bool
    isPrivileged: bool = Field(description='High-impact permission (fixed list on the server).')


class PermissionScopeDefinition(BaseModel):
    id: str
    value: str
    type: Literal['User', 'Admin']
    adminConsentDisplayName: str | None
    adminConsentDescription: str | None
    userConsentDisplayName: str | None
    userConsentDescription: str | None
    isEnabled: bool
    isPrivileged: bool = Field(description='High-impact permission (fixed list on the server).')


class MetadataEntry(BaseModel):
    key: str
    value: Any = Field(description='Decoded value: JSON if it parses, text otherwise.')


class ServicePrincipalRow(BaseModel):
    id: str
    displayName: str
    appId: str
    servicePrincipalType: str | None
    publisherName: str | None
    microsoftFirstParty: bool | None
    accountEnabled: bool
    appRoleAssignmentRequired: bool | None
    passwordCount: int
    keyCount: int
    appRoleCount: int
    oauth2PermissionCount: int
    hasCustomOwner: bool


class ServicePrincipalQuery(PageQuery):
    memberOf: str | None = None
    ownerId: str | None = Field(None, description='SPs owned by this object.')
    ownerOf: str | None = Field(None, description='SPs owning this object.')
    servicePrincipalType: str | None = None
    microsoftFirstParty: bool | None = None
    accountEnabled: bool | None = None
    hasCredentials: bool | None = None


class ServicePrincipalCounts(BaseModel):
    owners: int
    memberOf: int
    roles: int
    appRoleAssignments: int
    appRoleAssignedTo: int
    oauth2GrantsAsClient: int
    oauth2GrantsAsResource: int
    policies: int
    azureRoles: int


class ServicePrincipalDetail(ServicePrincipalRow):
    appOwnerTenantId: str | None
    homepage: str | None
    replyUrls: list[str]
    servicePrincipalNames: list[str]
    application: ObjectRef | None
    credentials: list[Credential]
    appRoles: list[AppRoleDefinition]
    oauth2Permissions: list[PermissionScopeDefinition]
    metadata: list[MetadataEntry]
    counts: ServicePrincipalCounts
    raw: Raw


class ApplicationRow(BaseModel):
    id: str
    displayName: str
    appId: str
    availableToOtherTenants: bool | None
    homepage: str | None
    publicClient: bool | None
    oauth2AllowImplicitFlow: bool | None
    passwordCount: int
    keyCount: int
    appRoleCount: int
    oauth2PermissionCount: int
    hasCustomOwner: bool


class ApplicationQuery(PageQuery):
    ownerId: str | None = None
    availableToOtherTenants: bool | None = None
    publicClient: bool | None = None
    hasCredentials: bool | None = None


class RequiredPermission(BaseModel):
    id: str
    value: str
    type: Literal['Role', 'Scope']
    isPrivileged: bool


class RequiredResourceAccess(BaseModel):
    resource: ObjectRef
    permissions: list[RequiredPermission]


class ApplicationCounts(BaseModel):
    owners: int
    policies: int


class ApplicationDetail(ApplicationRow):
    servicePrincipal: ObjectRef | None
    # Copied from the linked service principal (null without one).
    publisherName: str | None
    appOwnerTenantId: str | None
    accountEnabled: bool | None
    appRoleAssignmentRequired: bool | None
    replyUrls: list[str]
    identifierUris: list[str]
    credentials: list[Credential]
    appRoles: list[AppRoleDefinition]
    oauth2Permissions: list[PermissionScopeDefinition]
    requiredResourceAccess: list[RequiredResourceAccess]
    metadata: list[MetadataEntry]
    counts: ApplicationCounts
    raw: Raw


class OwnerQuery(PageQuery):
    """Owners of an object: users and service principals in one list."""
    ownerOf: str


# --- Roles -------------------------------------------------------------------

class RoleRow(BaseModel):
    id: str = Field(description='The role template id (equal to the role definition id).')
    templateId: str
    displayName: str
    description: str | None
    isBuiltIn: bool
    isPrivileged: bool = Field(description='Tier-0 / privileged role (fixed list of template IDs on the server).')
    activeCount: int
    eligibleCount: int
    syncedCount: int = Field(description='Distinct users holding the role (directly or through a group, active or '
                             'eligible) that are synced from on-premises.')


class RoleQuery(PageQuery):
    isBuiltIn: bool | None = None
    hasAssignments: bool | None = None


class RoleHolderCount(BaseModel):
    """Number of direct assignments of a role with this kind, principal type and scope."""
    kind: Kind
    principalType: Literal['user', 'group', 'servicePrincipal', 'unknown']
    scope: Literal['directory', 'administrativeUnit', 'application']
    count: int


class RoleDetail(RoleRow):
    allowedResourceActions: list[str]
    holders: list[RoleHolderCount]
    raw: Raw


class RoleAssignmentRow(BaseModel):
    id: str
    kind: Kind
    role: ObjectRef
    principal: ObjectRef
    via: ObjectRef | None = Field(description='Group the principal holds the role through, when expanded.')
    scope: ObjectRef = Field(description='Directory (keyword), an administrative unit or an application.')
    principalEnabled: bool | None
    principalDirSync: bool | None
    principalMfa: MfaSummary | None


class RoleAssignmentQuery(PageQuery):
    roleId: str | None = None
    principalId: str | None = None
    transitive: bool | None = Field(None, description='With principalId: also roles held through groups.')
    expandGroups: bool | None = Field(None, description='List group members as principals (with via = the group).')
    scopeId: str | None = None
    kind: Kind | None = None


# --- Grants ------------------------------------------------------------------

class AppRoleAssignmentRow(BaseModel):
    id: str
    principal: ObjectRef
    resource: ObjectRef
    appRoleId: str
    value: str = Field(description='Role value, or "Default access" for the zero GUID.')
    description: str | None
    isPrivileged: bool
    createdDateTime: str | None


class AppRoleAssignmentQuery(PageQuery):
    principalId: str | None = None
    resourceId: str | None = None
    principalType: Literal['User', 'Group', 'ServicePrincipal'] | None = None


class OAuth2GrantRow(BaseModel):
    id: str
    consentType: Literal['AllPrincipals', 'Principal']
    principal: ObjectRef | None
    client: ObjectRef
    resource: ObjectRef
    scopes: list[str]
    privilegedScopes: list[str] = Field(description='The scopes that are high-impact permissions.')
    expiryTime: str | None


class OAuth2GrantQuery(PageQuery):
    clientId: str | None = None
    resourceId: str | None = None
    principalId: str | None = None
    consentType: Literal['AllPrincipals', 'Principal'] | None = None


# --- Governance --------------------------------------------------------------

class AzureRole(BaseModel):
    displayName: str
    description: str | None
    isBuiltIn: bool


class AzureRoleAssignmentRow(BaseModel):
    id: str
    kind: Kind
    role: AzureRole
    principal: ObjectRef
    via: ObjectRef | None
    scope: str
    conditional: bool


class AzureRoleAssignmentQuery(PageQuery):
    principalId: str
    transitive: bool | None = None
    kind: Kind | None = None


class PimAssignmentRow(BaseModel):
    id: str
    kind: Kind
    resourceType: Literal['directoryRole', 'group', 'other']
    resource: ObjectRef
    role: str = Field(description='Role name, or Member / Owner for groups.')
    via: ObjectRef | None
    approvalRequired: bool | None
    startDateTime: str | None
    endDateTime: str | None = Field(description='null = permanent.')


class PimAssignmentQuery(PageQuery):
    principalId: str
    transitive: bool | None = None


class PimSubject(BaseModel):
    subject: ObjectRef
    kind: Kind
    startDateTime: str | None
    endDateTime: str | None


class GroupPim(BaseModel):
    onboardedDateTime: str | None
    memberApprovalRequired: bool | None
    ownerApprovalRequired: bool | None
    members: list[PimSubject]
    owners: list[PimSubject]


class AccessPackageResource(BaseModel):
    kind: str
    resource: ObjectRef
    role: str | None


class AccessPackagePolicyRow(BaseModel):
    id: str
    packageName: str
    packageDescription: str | None
    policyName: str
    resources: list[AccessPackageResource]
    approvalRequired: bool
    approvers: list[str]
    durationDays: int | None
    renewable: bool
    via: ObjectRef = Field(description='Why the user can request it: direct, a group, or a keyword like "All members".')


class AccessPackagePolicyQuery(PageQuery):
    userId: str


# --- Conditional Access ------------------------------------------------------

PolicyState = Literal['enabled', 'reporting', 'disabled']


class PolicyRow(BaseModel):
    id: str
    displayName: str
    state: PolicyState
    targetsAllUsers: bool
    targetsAllApps: bool
    block: bool
    grant: list[str]
    grantOperator: Literal['AND', 'OR']
    sessionControls: list[str]
    modifiedDateTime: str | None
    parseError: str | None


class PolicyQuery(PageQuery):
    state: PolicyState | None = None
    block: bool | None = None


class Condition(BaseModel):
    key: str = Field(description='Key in the policy JSON, e.g. Users, Applications, Locations.')
    label: str
    include: list[ObjectRef]
    exclude: list[ObjectRef]


class PolicyCounts(BaseModel):
    inScope: int
    excluded: int


class PolicyDetail(PolicyRow):
    who: list[Condition] = Field(description='Users, workload identities.')
    targets: list[Condition] = Field(description='Applications, user actions, authentication contexts.')
    conditions: list[Condition] = Field(description='Platforms, locations, client apps, device filters, risks.')
    grantControls: list[ObjectRef] = Field(description='Grant controls and authentication strengths, as value refs.')
    session: list[ObjectRef]
    counts: PolicyCounts
    raw: Raw


class PolicyUserQuery(UserQuery):
    effect: Literal['applies', 'excluded'] | None = None


class MatchReason(BaseModel):
    """Why a policy side (include or exclude) matches an object."""
    condition: str = Field(description='Condition label, e.g. Users, Directory roles, Resources.')
    via: list[ObjectRef] = Field(description='Chain from the object to what the policy references, '
                                 'e.g. [group, parent group]. Empty = direct.')
    approximate: bool
    eligibleOnly: bool = Field(description='Only through an eligible (PIM) role assignment.')


class PolicyMatch(BaseModel):
    """One policy that concerns an object. Exclusion wins over inclusion."""
    policy: PolicyRow
    effect: Literal['included', 'excluded']
    included: list[MatchReason]
    excluded: list[MatchReason]


PolicyTargetType = Literal['user', 'group', 'role', 'servicePrincipal', 'application']


class NamedLocationRow(BaseModel):
    id: str
    displayName: str
    kind: Literal['ip', 'country']
    trusted: bool
    ipRanges: list[str]
    countries: list[str]
    includeUnknownCountries: bool
    policyCount: int
    policies: list[ObjectRef] = Field(description='Policies that reference this location.')
    excludedBy: list[str] = Field(description='Ids of the policies in `policies` that exclude this location.')


class NamedLocationDetail(NamedLocationRow):
    policyMatches: list[PolicyMatch]
    raw: Raw


# --- Meta --------------------------------------------------------------------

class Stats(BaseModel):
    users: int
    guests: int
    groups: int
    devices: int
    servicePrincipals: int
    applications: int
    administrativeUnits: int
    roles: int
    policies: int
    namedLocations: int


class Domain(BaseModel):
    name: str
    type: str
    capabilities: list[str]
    isDefault: bool
    isInitial: bool


class AuthorizationPolicySummary(BaseModel):
    selfServicePasswordReset: bool | None
    blockMsolPowerShell: bool | None
    usersCanRegisterApps: bool | None
    usersCanCreateSecurityGroups: bool | None
    usersCanReadOtherUsers: bool | None
    userConsent: str
    guestAccess: str
    guestInvites: str
    userConsentPolicy: Literal['none', 'verifiedPublishers', 'all']
    guestRole: Literal['member', 'limited', 'restricted']
    guestInvitesFrom: Literal['none', 'admins', 'adminsAndGuestInviters', 'members', 'everyone']


class SettingValue(BaseModel):
    name: str
    value: str


class DirectorySettingSummary(BaseModel):
    name: str
    values: list[SettingValue]


class Tenant(BaseModel):
    displayName: str
    tenantId: str
    dirSyncEnabled: bool | None
    domains: list[Domain]
    authorizationPolicy: AuthorizationPolicySummary | None
    directorySettings: list[DirectorySettingSummary]
    raw: Raw


class SearchGroup(BaseModel):
    type: ObjectType
    total: int
    items: list[ObjectRef]


class SearchResult(BaseModel):
    groups: list[SearchGroup]
