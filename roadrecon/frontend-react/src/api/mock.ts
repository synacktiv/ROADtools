// Mock backend for the mockup phase (VITE_MOCK=1). Deleted at the switch.
// A seeded fake tenant, typed against the draft spec in types.ts.
import type {
  AccessPackagePolicyRow,
  AdministrativeUnitDetail,
  AppRoleAssignmentRow,
  AppRoleDefinition,
  ApplicationDetail,
  AzureRoleAssignmentRow,
  Condition,
  FilterField,
  FilterResource,
  FilterType,
  Credential,
  DeviceDetail,
  GroupDetail,
  GroupPim,
  MfaMethod,
  MfaSummary,
  NamedLocationDetail,
  OAuth2GrantRow,
  ObjectRef,
  ObjectType,
  Page,
  PermissionScopeDefinition,
  PimAssignmentRow,
  PolicyDetail,
  MatchReason,
  PolicyMatch,
  PolicyRow,
  RoleAssignmentRow,
  RoleDetail,
  SearchResult,
  ServicePrincipalDetail,
  Stats,
  Tenant,
  UserDetail,
  UserRow,
} from './types'

// --- Seeded randomness -----------------------------------------------------

let seed = 0x5eed
const rand = () => {
  seed = (seed + 0x6d2b79f5) | 0
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296
}
const pick = <T,>(a: readonly T[]) => a[Math.floor(rand() * a.length)]
const chance = (p: number) => rand() < p
const hex = (n: number) => Array.from({ length: n }, () => Math.floor(rand() * 16).toString(16)).join('')
const guid = () => `${hex(8)}-${hex(4)}-4${hex(3)}-${pick(['8', '9', 'a', 'b'])}${hex(3)}-${hex(12)}`
const daysAgo = (d: number) => new Date(Date.UTC(2026, 8, 30) - d * 86_400_000).toISOString()
const sample = <T,>(a: readonly T[], n: number) => [...a].sort(() => rand() - 0.5).slice(0, n)

const DOMAIN = 'halvorsen-maritime.com'
const TENANT_ID = 'b3f1c9e2-7a4d-4e8b-9c21-5d6e7f8a9b0c'

// --- Users -----------------------------------------------------------------

const FIRST = ['Ingrid', 'Lars', 'Amara', 'Tomasz', 'Yuki', 'Rafael', 'Sanne', 'Kwame', 'Elif', 'Mateo', 'Freya', 'Dmitri', 'Leila', 'Oskar', 'Priya', 'Henrik', 'Noor', 'Jonas', 'Chiara', 'Emeka', 'Astrid', 'Pavel', 'Mei', 'Tobias', 'Ines', 'Viktor', 'Zainab', 'Magnus', 'Lucía', 'Arne']
const LAST = ['Halvorsen', 'Nakamura', 'Okafor', 'Kowalski', 'Lindqvist', 'Moreau', 'Haddad', 'Berg', 'Castillo', 'Yilmaz', 'Mensah', 'Novak', 'Andersen', 'Rossi', 'Sato', 'Dubois', 'Iversen', 'Petrov', 'Fischer', 'Osei']
const DEPTS = ['Finance', 'Operations', 'Fleet', 'IT', 'Legal', 'HR', 'Sales', 'Chartering', null]
const TITLES = ['Analyst', 'Engineer', 'Manager', 'Coordinator', 'Specialist', 'Director', null]
const METHODS: MfaMethod[] = ['PhoneAppNotification', 'PhoneAppOTP', 'OneWaySms', 'TwoWayVoiceMobile']

function mfa(strong: boolean): MfaSummary {
  if (!strong && chance(0.6)) return { methods: [], defaultMethod: null, perUserMfa: chance(0.1) ? 'Enabled' : null, fido: 0, windowsHello: 0 }
  const methods = sample(METHODS, 1 + Math.floor(rand() * 3))
  return {
    methods,
    defaultMethod: methods[0],
    perUserMfa: chance(0.15) ? pick(['Enabled', 'Enforced']) : null,
    fido: chance(0.12) ? 1 : 0,
    windowsHello: chance(0.3) ? 1 : 0,
  }
}

const users: UserDetail[] = []
function addUser(displayName: string, upn: string, o: Partial<UserDetail> = {}) {
  const u: UserDetail = {
    id: guid(),
    displayName,
    userPrincipalName: upn,
    accountEnabled: true,
    mail: upn.includes('#EXT#') ? null : upn,
    department: pick(DEPTS),
    jobTitle: pick(TITLES),
    mobile: chance(0.4) ? `+47 9${Math.floor(rand() * 9e6 + 1e6)}` : null,
    lastPasswordChangeDateTime: daysAgo(Math.floor(rand() * 400)),
    dirSyncEnabled: chance(0.55),
    userType: 'Member',
    mfa: mfa(chance(0.7)),
    onPremisesSamAccountName: null,
    onPremisesSecurityIdentifier: null,
    createdDateTime: daysAgo(400 + Math.floor(rand() * 1500)),
    lastDirSyncTime: null,
    counts: { memberOf: 0, roles: 0, ownedDevices: 0, ownedServicePrincipals: 0, ownedApplications: 0, ownedGroups: 0, administrativeUnits: 0, appRoleAssignments: 0, oauth2Grants: 0, policies: 0, azureRoles: 0, pim: 0, accessPackages: 0 },
    raw: {},
    ...o,
  }
  if (u.dirSyncEnabled) {
    u.onPremisesSamAccountName = upn.split('@')[0].replace('.', '').slice(0, 20)
    u.onPremisesSecurityIdentifier = `S-1-5-21-3623811015-3361044348-30300820-${1100 + users.length}`
    u.lastDirSyncTime = daysAgo(0.1)
  }
  users.push(u)
  return u
}

const breakGlass1 = addUser('Break Glass 01', `bg01@${DOMAIN}`, { dirSyncEnabled: false, department: null, jobTitle: null, mfa: { methods: [], defaultMethod: null, perUserMfa: null, fido: 1, windowsHello: 0 } })
const breakGlass2 = addUser('Break Glass 02', `bg02@${DOMAIN}`, { dirSyncEnabled: false, department: null, jobTitle: null, mfa: { methods: [], defaultMethod: null, perUserMfa: null, fido: 1, windowsHello: 0 } })
const syncAccount = addUser('On-Premises Directory Synchronization Service Account', `Sync_DC01_8f2a1c@${DOMAIN}`, { dirSyncEnabled: false, department: null, jobTitle: null, mfa: mfa(false) })
for (let i = 0; i < 236; i++) {
  const f = pick(FIRST)
  const l = pick(LAST)
  if (i % 11 === 10) {
    addUser(`${f} ${l} (Partner)`, `${f.toLowerCase()}.${l.toLowerCase()}_seaworks.no#EXT#@${DOMAIN}`, { userType: 'Guest', dirSyncEnabled: false, department: null, jobTitle: null })
  } else {
    addUser(`${f} ${l}`, `${f.toLowerCase()}.${l.toLowerCase()}${i > 120 ? i : ''}@${DOMAIN}`, { accountEnabled: !chance(0.07) })
  }
}
const [alice, bob, carol, dave] = users.slice(3, 7)
alice.displayName = 'Ingrid Halvorsen'
alice.userPrincipalName = alice.mail = `ingrid.halvorsen@${DOMAIN}`
alice.department = 'IT'
alice.jobTitle = 'Head of IT'

// --- Groups ----------------------------------------------------------------

const groups: GroupDetail[] = []
const members = new Map<string, Set<string>>() // group -> direct member ids (any type)
function addGroup(displayName: string, o: Partial<GroupDetail> = {}) {
  const g: GroupDetail = {
    id: guid(),
    displayName,
    description: null,
    groupTypes: [],
    securityEnabled: true,
    mailEnabled: false,
    mail: null,
    isPublic: null,
    isAssignableToRole: false,
    membershipRule: null,
    dirSyncEnabled: false,
    createdDateTime: daysAgo(100 + Math.floor(rand() * 1200)),
    pimEnabled: false,
    securityIdentifier: `S-1-12-1-${Math.floor(rand() * 4e9)}-${Math.floor(rand() * 4e9)}-${Math.floor(rand() * 4e9)}-${Math.floor(rand() * 4e9)}`,
    onPremisesSecurityIdentifier: null,
    counts: { memberUsers: 0, transitiveMemberUsers: 0, memberGroups: 0, memberServicePrincipals: 0, memberDevices: 0, memberOf: 0, owners: 0, roles: 0, administrativeUnits: 0, appRoleAssignments: 0, policies: 0, azureRoles: 0 },
    raw: {},
    ...o,
  }
  groups.push(g)
  members.set(g.id, new Set())
  return g
}
const add = (g: GroupDetail, ...ids: string[]) => ids.forEach((id) => members.get(g.id)!.add(id))

const allStaff = addGroup('All staff', { description: 'Every member account', membershipRule: '(user.userType -eq "Member") and (user.accountEnabled -eq true)' })
const tier0 = addGroup('Tier 0 admins', { description: 'Holds privileged directory roles', isAssignableToRole: true, pimEnabled: true })
const bgGroup = addGroup('CA exclusion - break glass', { description: 'Excluded from every Conditional Access policy', isAssignableToRole: true })
const mfaExcl = addGroup('CA exclusion - MFA', { description: 'Temporary MFA exemptions. Review monthly.' })
const finance = addGroup('Finance', { dirSyncEnabled: true, description: 'GG-Finance (synced)' })
const payables = addGroup('Finance - Payables', { dirSyncEnabled: true })
const opsA = addGroup('Operations - Bergen')
const opsB = addGroup('Operations - Haugesund')
const helpdesk = addGroup('IT Helpdesk', { isAssignableToRole: true })
const m365 = addGroup('Fleet Management', { groupTypes: ['Unified'], mailEnabled: true, mail: `fleet@${DOMAIN}`, isPublic: true, description: 'Teams workspace for fleet management' })
const devAdmins = addGroup('Azure subscription owners', { description: 'Owner on production subscriptions' })
const guestsGroup = addGroup('External partners', { membershipRule: '(user.userType -eq "Guest")' })
for (const n of ['Legal', 'HR', 'Sales', 'Chartering', 'VPN users', 'Intune - pilot', 'Printers', 'SharePoint - Board', 'Shipyard contractors', 'License - E5'])
  addGroup(n, { dirSyncEnabled: chance(0.5), groupTypes: chance(0.3) ? ['Unified'] : [], mailEnabled: chance(0.3) })

const memberUsers = users.filter((u) => u.userType === 'Member')
add(allStaff, ...memberUsers.filter((u) => u.accountEnabled).map((u) => u.id))
add(tier0, alice.id, bob.id)
add(bgGroup, breakGlass1.id, breakGlass2.id)
add(mfaExcl, dave.id, syncAccount.id)
add(finance, payables.id, ...sample(memberUsers, 18).map((u) => u.id))
add(payables, carol.id, ...sample(memberUsers, 9).map((u) => u.id))
add(opsA, opsB.id, ...sample(memberUsers, 25).map((u) => u.id))
add(opsB, opsA.id, ...sample(memberUsers, 14).map((u) => u.id)) // membership cycle, on purpose
add(helpdesk, carol.id, ...sample(memberUsers, 4).map((u) => u.id))
add(m365, ...sample(memberUsers, 30).map((u) => u.id))
add(devAdmins, alice.id, dave.id, tier0.id)
add(guestsGroup, ...users.filter((u) => u.userType === 'Guest').map((u) => u.id))
for (const g of groups.slice(12)) add(g, ...sample(memberUsers, 3 + Math.floor(rand() * 20)).map((u) => u.id))

// --- Devices ---------------------------------------------------------------

const devices: DeviceDetail[] = []
const deviceOwner = new Map<string, string>()
for (let i = 0; i < 64; i++) {
  const os = pick(['Windows', 'Windows', 'Windows', 'iOS', 'Android', 'MacOS'])
  const owner = pick(memberUsers)
  const d: DeviceDetail = {
    id: guid(),
    displayName: os === 'Windows' ? `HM-${pick(['LT', 'WS'])}-${(1000 + i).toString()}` : `${owner.displayName.split(' ')[0]}'s ${os === 'iOS' ? 'iPhone' : os === 'MacOS' ? 'MacBook' : 'Pixel'}`,
    deviceId: guid(),
    accountEnabled: !chance(0.05),
    deviceManufacturer: os === 'Windows' ? pick(['Dell Inc.', 'LENOVO', 'HP']) : os === 'Android' ? 'Google' : 'Apple',
    deviceModel: os === 'Windows' ? pick(['Latitude 7440', 'ThinkPad T14 Gen 4', 'EliteBook 840 G10']) : os === 'iOS' ? 'iPhone 15' : os === 'MacOS' ? 'MacBookPro18,3' : 'Pixel 8',
    deviceOSType: os,
    deviceOSVersion: os === 'Windows' ? pick(['10.0.22631.4317', '10.0.26100.2033', '10.0.19045.5011']) : os === 'iOS' ? '18.0.1' : os === 'MacOS' ? '14.6.1' : '15',
    deviceTrustType: os === 'Windows' ? pick(['AzureAd', 'ServerAd']) : 'Workplace',
    isCompliant: chance(0.75),
    isManaged: chance(0.85),
    isRooted: os === 'Android' && chance(0.3),
    dirSyncEnabled: false,
    bitLockerKeys: [],
    owners: [],
    counts: { owners: 1, memberOf: 0, administrativeUnits: 0 },
    raw: {},
  }
  if (os === 'Windows' && chance(0.6))
    d.bitLockerKeys.push({
      keyIdentifier: guid(),
      keyMaterial: Array.from({ length: 8 }, () => String(Math.floor(rand() * 999999)).padStart(6, '0')).join('-'),
      volumeType: 'Operating system volume',
      creationTime: daysAgo(Math.floor(rand() * 300)),
    })
  devices.push(d)
  deviceOwner.set(d.id, owner.id)
}
const intunePilot = groups.find((g) => g.displayName === 'Intune - pilot')!
add(intunePilot, ...devices.slice(0, 12).map((d) => d.id))

// --- Applications and service principals -----------------------------------

const role = (value: string, displayName: string, types = ['Application']): AppRoleDefinition => ({ id: guid(), value, displayName, description: displayName, allowedMemberTypes: types, isEnabled: true })
const scope = (value: string, admin: boolean): PermissionScopeDefinition => ({
  id: guid(),
  value,
  type: admin ? 'Admin' : 'User',
  adminConsentDisplayName: value,
  adminConsentDescription: `Allows the app to ${value.replace(/\./g, ' ').toLowerCase()} on behalf of the signed-in user.`,
  userConsentDisplayName: admin ? null : value,
  userConsentDescription: admin ? null : `Allows the app to ${value.replace(/\./g, ' ').toLowerCase()} for you.`,
  isEnabled: true,
})
const cred = (kind: Credential['kind'], name: string | null, endInDays: number): Credential => ({
  kind,
  keyId: guid(),
  displayName: name,
  startDate: daysAgo(365),
  endDate: new Date(Date.UTC(2026, 8, 30) + endInDays * 86_400_000).toISOString(),
})

const sps: ServicePrincipalDetail[] = []
const apps: ApplicationDetail[] = []
const owners = new Map<string, string[]>() // object -> owner ids

function addSp(displayName: string, appId: string, o: Partial<ServicePrincipalDetail> = {}) {
  const s: ServicePrincipalDetail = {
    id: guid(),
    displayName,
    appId,
    servicePrincipalType: 'Application',
    publisherName: 'Microsoft Services',
    microsoftFirstParty: true,
    accountEnabled: true,
    appRoleAssignmentRequired: false,
    passwordCount: 0,
    keyCount: 0,
    appRoleCount: 0,
    oauth2PermissionCount: 0,
    hasCustomOwner: false,
    appOwnerTenantId: 'f8cdef31-a31e-4b4a-93e4-5f571e91255a',
    homepage: null,
    replyUrls: [],
    servicePrincipalNames: [appId],
    application: null,
    credentials: [],
    appRoles: [],
    oauth2Permissions: [],
    metadata: [],
    counts: { owners: 0, memberOf: 0, roles: 0, appRoleAssignments: 0, appRoleAssignedTo: 0, oauth2GrantsAsClient: 0, oauth2GrantsAsResource: 0, policies: 0, azureRoles: 0 },
    raw: {},
    ...o,
  }
  s.appRoleCount = s.appRoles.length
  s.oauth2PermissionCount = s.oauth2Permissions.length
  s.passwordCount = s.credentials.filter((c) => c.kind === 'password').length
  s.keyCount = s.credentials.filter((c) => c.kind === 'certificate').length
  sps.push(s)
  return s
}

const graph = addSp('Microsoft Graph', '00000003-0000-0000-c000-000000000000', {
  appRoles: [role('User.Read.All', 'Read all users full profiles'), role('Directory.ReadWrite.All', 'Read and write directory data'), role('Mail.Read', 'Read mail in all mailboxes'), role('RoleManagement.ReadWrite.Directory', 'Read and write all directory RBAC settings'), role('Application.ReadWrite.All', 'Read and write all applications')],
  oauth2Permissions: [scope('User.Read', false), scope('Mail.Read', false), scope('Files.ReadWrite.All', false), scope('Directory.AccessAsUser.All', true), scope('offline_access', false)],
})
const exo = addSp('Office 365 Exchange Online', '00000002-0000-0ff1-ce00-000000000000', { appRoles: [role('full_access_as_app', 'Use Exchange Web Services with full access to all mailboxes')], oauth2Permissions: [scope('EWS.AccessAsUser.All', false)] })
const spo = addSp('Office 365 SharePoint Online', '00000003-0000-0ff1-ce00-000000000000', { appRoles: [role('Sites.FullControl.All', 'Have full control of all site collections')] })
const azPortal = addSp('Azure Portal', 'c44b4083-3bb0-49c1-b47d-974e53cbdf3c')
const azCli = addSp('Microsoft Azure CLI', '04b07795-8ddb-461a-bbee-02f9e1bf7b46')
const azPs = addSp('Microsoft Azure PowerShell', '1950a258-227b-4e31-a9cf-717495945fc2')
const teams = addSp('Microsoft Teams', '1fec8e78-bce4-4aaf-ab1b-5451cc387264')
const intune = addSp('Microsoft Intune', '0000000a-0000-0000-c000-000000000000')
const msAdmin = addSp('Microsoft Admin Portals', '497effe9-df71-4043-a8bb-14cf78c4b63b')
for (const [n, id] of [['Office 365 Management APIs', 'c5393580-f805-4401-95e8-94b7a6ef2fc2'], ['Windows Azure Service Management API', '797f4846-ba00-4fd7-ba43-dac1f8f63013'], ['Microsoft Authentication Broker', '29d9ed98-a469-4536-ade2-f981bc1d605e'], ['Office 365 Management', '00b41c95-dab0-4487-9791-b9d2c32c80f2']] as const)
  addSp(n, id)

function addApp(displayName: string, o: Partial<ApplicationDetail> = {}, spExtra: Partial<ServicePrincipalDetail> = {}) {
  const appId = guid()
  const a: ApplicationDetail = {
    id: guid(),
    displayName,
    appId,
    availableToOtherTenants: false,
    homepage: null,
    publicClient: false,
    oauth2AllowImplicitFlow: false,
    passwordCount: 0,
    keyCount: 0,
    appRoleCount: 0,
    oauth2PermissionCount: 0,
    hasCustomOwner: false,
    servicePrincipal: null,
    replyUrls: [],
    identifierUris: [],
    credentials: [],
    appRoles: [],
    oauth2Permissions: [],
    requiredResourceAccess: [],
    metadata: [],
    counts: { owners: 0, policies: 0 },
    raw: {},
    ...o,
  }
  a.passwordCount = a.credentials.filter((c) => c.kind === 'password').length
  a.keyCount = a.credentials.filter((c) => c.kind === 'certificate').length
  a.appRoleCount = a.appRoles.length
  a.oauth2PermissionCount = a.oauth2Permissions.length
  const s = addSp(displayName, appId, {
    publisherName: 'Halvorsen Maritime',
    microsoftFirstParty: false,
    appOwnerTenantId: TENANT_ID,
    homepage: a.homepage,
    replyUrls: a.replyUrls,
    appRoles: a.appRoles,
    oauth2Permissions: a.oauth2Permissions,
    application: { id: a.id, type: 'application', displayName, sub: appId },
    ...spExtra,
  })
  a.servicePrincipal = { id: s.id, type: 'servicePrincipal', displayName, sub: appId }
  apps.push(a)
  return [a, s] as const
}

const graphRef: ObjectRef = { id: graph.id, type: 'servicePrincipal', displayName: graph.displayName, sub: graph.appId }
const [hrApp, hrSp] = addApp('HR Sync Connector', {
  credentials: [cred('password', 'prod secret', 12), cred('password', 'old', -40)],
  requiredResourceAccess: [{ resource: graphRef, permissions: [{ id: graph.appRoles[0].id, value: 'User.Read.All', type: 'Role' }, { id: graph.appRoles[1].id, value: 'Directory.ReadWrite.All', type: 'Role' }] }],
})
const [, mailSp] = addApp('Fleet Mail Archiver', {
  credentials: [cred('certificate', 'CN=archiver', 200)],
  requiredResourceAccess: [{ resource: graphRef, permissions: [{ id: graph.appRoles[2].id, value: 'Mail.Read', type: 'Role' }] }],
})
const [portalApp, portalSp] = addApp('Crew Portal', {
  homepage: 'https://crew.halvorsen-maritime.com',
  replyUrls: ['https://crew.halvorsen-maritime.com/signin-oidc', 'http://localhost:5000/signin-oidc'],
  identifierUris: ['api://crew-portal'],
  oauth2AllowImplicitFlow: true,
  availableToOtherTenants: true,
  appRoles: [role('Crew.Read', 'Read crew rosters', ['User']), role('Crew.Admin', 'Manage crew rosters', ['User'])],
  oauth2Permissions: [scope('access_as_user', false)],
  requiredResourceAccess: [{ resource: graphRef, permissions: [{ id: graph.oauth2Permissions[0].id, value: 'User.Read', type: 'Scope' }, { id: graph.oauth2Permissions[4].id, value: 'offline_access', type: 'Scope' }] }],
  metadata: [{ key: 'ms.portal.branding', value: { logo: 'crew.png', theme: 'navy' } }],
}, { appRoleAssignmentRequired: true })
const [, deploySp] = addApp('GitHub Actions - infra', {
  credentials: [cred('certificate', 'federated', 90)],
  requiredResourceAccess: [{ resource: graphRef, permissions: [{ id: graph.appRoles[3].id, value: 'RoleManagement.ReadWrite.Directory', type: 'Role' }, { id: graph.appRoles[4].id, value: 'Application.ReadWrite.All', type: 'Role' }] }],
})
const [, cliSp] = addApp('Vessel Telemetry CLI', { publicClient: true })
for (const n of ['Chartering Calendar', 'Expense Reports', 'Port Call Planner', 'Legal Hold Tool', 'Payroll Export', 'Bunker Pricing API', 'Safety Reporting'])
  addApp(n, { credentials: chance(0.5) ? [cred('password', null, Math.floor(rand() * 400) - 60)] : [] })
for (const n of ['Adobe Acrobat', 'Zoom', 'Salesforce', 'DocuSign', 'Slack', 'ServiceNow', 'Miro', 'Atlassian Cloud'])
  addSp(n, guid(), { publisherName: n.split(' ')[0] + ' Inc.', microsoftFirstParty: false, appOwnerTenantId: guid(), oauth2Permissions: [], replyUrls: [`https://${n.split(' ')[0].toLowerCase()}.com/oauth/callback`] })
const mi = addSp('vm-telemetry-prod', guid(), { servicePrincipalType: 'ManagedIdentity', publisherName: null, microsoftFirstParty: false, appOwnerTenantId: null })

owners.set(hrApp.id, [alice.id])
owners.set(hrSp.id, [alice.id, deploySp.id])
owners.set(portalApp.id, [bob.id, carol.id])
owners.set(portalSp.id, [bob.id])
owners.set(tier0.id, [alice.id])
owners.set(finance.id, [carol.id])
for (const d of devices) owners.set(d.id, [deviceOwner.get(d.id)!])
for (const [obj, os] of owners) {
  const sp = sps.find((s) => s.id === obj)
  if (sp) sp.hasCustomOwner = true
  const app = apps.find((a) => a.id === obj)
  if (app) app.hasCustomOwner = true
  void os
}
add(devAdmins, deploySp.id)

// --- Directory roles -------------------------------------------------------

const ROLE_DEFS: [string, string, string][] = [
  ['62e90394-69f5-4237-9190-012177145e10', 'Global Administrator', 'Can manage all aspects of Microsoft Entra ID and Microsoft services that use Microsoft Entra identities.'],
  ['e8611ab8-c189-46e8-94e1-60213ab1f814', 'Privileged Role Administrator', 'Can manage role assignments in Microsoft Entra ID, and all aspects of Privileged Identity Management.'],
  ['9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3', 'Application Administrator', 'Can create and manage all aspects of app registrations and enterprise apps.'],
  ['158c047a-c907-4556-b7ef-446551a6b5f7', 'Cloud Application Administrator', 'Can create and manage all aspects of app registrations and enterprise apps except App Proxy.'],
  ['29232cdf-9323-42fd-ade2-1d097af3e4de', 'Exchange Administrator', 'Can manage all aspects of the Exchange product.'],
  ['fe930be7-5e62-47db-91af-98c3a49a38b1', 'User Administrator', 'Can manage all aspects of users and groups, including resetting passwords for limited admins.'],
  ['729827e3-9c14-49f7-bb1b-9608f156bbb8', 'Helpdesk Administrator', 'Can reset passwords for non-administrators and Helpdesk Administrators.'],
  ['b1be1c3e-b65d-4f19-8427-f6fa0d97feb9', 'Conditional Access Administrator', 'Can manage Conditional Access capabilities.'],
  ['c4e39bd9-1100-46d3-8c65-fb160da0071f', 'Authentication Administrator', 'Can access to view, set and reset authentication method information for any non-admin user.'],
  ['f2ef992c-3afb-46b9-b7cf-a126ee74c451', 'Global Reader', 'Can read everything that a Global Administrator can, but not update anything.'],
  ['5d6b6bb7-de71-4623-b4af-96380a352509', 'Security Reader', 'Can read security information and reports in Microsoft Entra ID and Office 365.'],
  ['3a2c62db-5318-420d-8d74-23affee5d9d5', 'Intune Administrator', 'Can manage all aspects of the Intune product.'],
  ['d29b2b05-8046-44ba-8758-1e26182fcf32', 'Directory Synchronization Accounts', 'Only used by Microsoft Entra Connect service.'],
  ['194ae4cb-b126-40b2-bd5b-6091b380977d', 'Security Administrator', 'Can read security information and reports, and manage configuration in Microsoft Entra ID and Office 365.'],
]
const roles: RoleDetail[] = ROLE_DEFS.map(([templateId, displayName, description]) => ({
  id: templateId,
  templateId,
  displayName,
  description,
  isBuiltIn: true,
  isPrivileged: false,
  activeCount: 0,
  eligibleCount: 0,
  allowedResourceActions: ['microsoft.directory/users/basic/update', 'microsoft.directory/groups/members/update', 'microsoft.directory/applications/credentials/update', 'microsoft.directory/servicePrincipals/appRoleAssignedTo/update'].slice(0, 2 + Math.floor(rand() * 3)),
  raw: {},
}))
const customRole: RoleDetail = { id: guid(), templateId: guid(), displayName: 'Vessel Device Operator', description: 'Custom role: manage BitLocker keys of fleet devices', isBuiltIn: false, isPrivileged: false, activeCount: 0, eligibleCount: 0, allowedResourceActions: ['microsoft.directory/bitlockerKeys/key/read', 'microsoft.directory/devices/basic/update'], raw: {} }
roles.push(customRole)
const roleByName = (n: string) => roles.find((r) => r.displayName === n)!

const ref = (type: ObjectType, o: { id: string; displayName: string; userPrincipalName?: string; appId?: string }): ObjectRef => ({ id: o.id, type, displayName: o.displayName, sub: o.userPrincipalName ?? o.appId ?? null })
const DIRECTORY: ObjectRef = { id: null, type: 'keyword', displayName: 'Directory' }

interface RA {
  id: string
  kind: 'active' | 'eligible'
  role: RoleDetail
  principal: ObjectRef
  scope: ObjectRef
}
const roleAssignments: RA[] = []
const assign = (r: RoleDetail, principal: ObjectRef, kind: RA['kind'] = 'active', sc: ObjectRef = DIRECTORY) => roleAssignments.push({ id: guid(), kind, role: r, principal, scope: sc })
assign(roleByName('Global Administrator'), ref('user', breakGlass1))
assign(roleByName('Global Administrator'), ref('user', breakGlass2))
assign(roleByName('Global Administrator'), ref('group', tier0), 'eligible')
assign(roleByName('Privileged Role Administrator'), ref('user', alice))
assign(roleByName('Privileged Role Administrator'), ref('servicePrincipal', deploySp))
assign(roleByName('Application Administrator'), ref('user', bob), 'eligible')
assign(roleByName('Cloud Application Administrator'), ref('servicePrincipal', hrSp))
assign(roleByName('Helpdesk Administrator'), ref('group', helpdesk))
assign(roleByName('Exchange Administrator'), ref('user', dave))
assign(roleByName('Directory Synchronization Accounts'), ref('user', syncAccount))
assign(roleByName('Conditional Access Administrator'), ref('user', carol), 'eligible')
assign(roleByName('Security Reader'), ref('user', users[20]))
assign(roleByName('Global Reader'), ref('user', users[21]))
assign(roleByName('Intune Administrator'), ref('user', users[22]), 'eligible')
assign(roleByName('Application Administrator'), ref('user', users[23]), 'active', ref('application', portalApp))

// --- Administrative units ---------------------------------------------------

const aus: AdministrativeUnitDetail[] = ['Bergen office', 'Haugesund office', 'Vessels'].map((n, i) => ({
  id: guid(),
  displayName: n,
  description: i === 2 ? 'Shipboard devices and crew' : `Users and devices at the ${n}`,
  membershipRule: i === 2 ? '(device.displayName -startsWith "HM-WS")' : null,
  counts: { memberUsers: 0, memberGroups: 0, memberDevices: 0, scopedRoles: 0 },
  raw: {},
}))
const auMembers = new Map<string, Set<string>>(aus.map((a) => [a.id, new Set<string>()]))
auMembers.get(aus[0].id)!.add(opsA.id)
sample(memberUsers, 40).forEach((u) => auMembers.get(aus[0].id)!.add(u.id))
sample(memberUsers, 25).forEach((u) => auMembers.get(aus[1].id)!.add(u.id))
devices.filter((d) => d.displayName.startsWith('HM-WS')).forEach((d) => auMembers.get(aus[2].id)!.add(d.id))
assign(roleByName('User Administrator'), ref('user', users[24]), 'active', ref('administrativeUnit', aus[0]))
assign(customRole, ref('group', helpdesk), 'active', ref('administrativeUnit', aus[2]))

// --- Grants ----------------------------------------------------------------

const appRoleAssignments: AppRoleAssignmentRow[] = []
const ara = (principal: ObjectRef, resource: ServicePrincipalDetail, r?: AppRoleDefinition) =>
  appRoleAssignments.push({
    id: guid(),
    principal,
    resource: ref('servicePrincipal', resource),
    appRoleId: r?.id ?? '00000000-0000-0000-0000-000000000000',
    value: r?.value ?? 'Default access',
    description: r?.displayName ?? null,
    createdDateTime: daysAgo(Math.floor(rand() * 500)),
  })
ara(ref('servicePrincipal', hrSp), graph, graph.appRoles[0])
ara(ref('servicePrincipal', hrSp), graph, graph.appRoles[1])
ara(ref('servicePrincipal', mailSp), graph, graph.appRoles[2])
ara(ref('servicePrincipal', mailSp), exo, exo.appRoles[0])
ara(ref('servicePrincipal', deploySp), graph, graph.appRoles[3])
ara(ref('servicePrincipal', deploySp), graph, graph.appRoles[4])
ara(ref('servicePrincipal', mi), spo, spo.appRoles[0])
ara(ref('group', m365), portalSp, portalSp.appRoles[0])
ara(ref('user', bob), portalSp, portalSp.appRoles[1])
sample(memberUsers, 12).forEach((u) => ara(ref('user', u), portalSp))

const grants: OAuth2GrantRow[] = []
const grant = (client: ServicePrincipalDetail, resource: ServicePrincipalDetail, scopes: string[], principal?: UserDetail) =>
  grants.push({ id: guid(), consentType: principal ? 'Principal' : 'AllPrincipals', principal: principal ? ref('user', principal) : null, client: ref('servicePrincipal', client), resource: ref('servicePrincipal', resource), scopes, expiryTime: daysAgo(-180) })
grant(portalSp, graph, ['User.Read', 'offline_access', 'openid', 'profile'])
grant(cliSp, graph, ['User.Read', 'Directory.AccessAsUser.All'])
grant(azCli, graph, ['User.Read', 'Directory.AccessAsUser.All'])
grant(teams, exo, ['EWS.AccessAsUser.All'])
const slack = sps.find((s) => s.displayName === 'Slack')!
grant(slack, graph, ['Mail.Read', 'Files.ReadWrite.All', 'offline_access'], carol)
grant(slack, graph, ['User.Read'], users[30])
sample(memberUsers, 8).forEach((u) => grant(sps.find((s) => s.displayName === 'Zoom')!, graph, ['User.Read', 'Calendars.ReadWrite'], u))

// --- Named locations and Conditional Access ---------------------------------

const locations: NamedLocationDetail[] = [
  { id: guid(), displayName: 'Head office Bergen', kind: 'ip', trusted: true, ipRanges: ['193.69.120.0/24', '2a02:fe0:c410::/48'], countries: [], includeUnknownCountries: false, policyCount: 0, policies: [], raw: {} },
  { id: guid(), displayName: 'Vessel satellite uplinks', kind: 'ip', trusted: true, ipRanges: ['85.19.208.0/22', '212.62.231.64/27'], countries: [], includeUnknownCountries: false, policyCount: 0, policies: [], raw: {} },
  { id: guid(), displayName: 'Blocked countries', kind: 'country', trusted: false, ipRanges: [], countries: ['KP', 'IR', 'RU', 'BY'], includeUnknownCountries: true, policyCount: 0, policies: [], raw: {} },
]
const locRef = (l: NamedLocationDetail): ObjectRef => ({ id: l.id, type: 'namedLocation', displayName: l.displayName })
const kw = (displayName: string): ObjectRef => ({ id: null, type: 'keyword', displayName })
const val = (displayName: string): ObjectRef => ({ id: null, type: 'value', displayName })
const roleRef = (n: string) => ref('role', roleByName(n))
const cond = (key: string, label: string, include: ObjectRef[], exclude: ObjectRef[] = []): Condition => ({ key, label, include, exclude })

const policies: PolicyDetail[] = []
function addPolicy(p: Omit<PolicyDetail, 'id' | 'targetsAllUsers' | 'targetsAllApps' | 'grantOperator' | 'sessionControls' | 'modifiedDateTime' | 'parseError' | 'counts' | 'raw'> & Partial<PolicyDetail>) {
  const full: PolicyDetail = {
    id: guid(),
    grantOperator: 'OR',
    sessionControls: p.session.map((s) => s.displayName.split(':')[0]),
    modifiedDateTime: daysAgo(Math.floor(rand() * 200)),
    parseError: null,
    counts: { inScope: 0, excluded: 0 },
    raw: {},
    ...p,
    targetsAllUsers: p.who.some((c) => c.include.some((r) => r.displayName === 'All users')),
    targetsAllApps: p.targets.some((c) => c.include.some((r) => r.displayName === 'All resources')),
  }
  full.raw = { displayName: full.displayName, State: full.state === 'reporting' ? 'Reporting' : full.state === 'enabled' ? 'Enabled' : 'Disabled', Conditions: '…' }
  policies.push(full)
  return full
}
const exceptBg = [ref('group', bgGroup)]
addPolicy({
  displayName: 'CA001 - Require MFA for all users',
  state: 'enabled',
  block: false,
  grant: ['MFA'],
  who: [cond('Users', 'Users', [kw('All users')], [...exceptBg, ref('group', mfaExcl), ref('user', syncAccount)])],
  targets: [cond('Applications', 'Resources', [kw('All resources')])],
  conditions: [],
  grantControls: [val('Multifactor authentication')],
  session: [],
})
addPolicy({
  displayName: 'CA002 - Phishing-resistant MFA for admins',
  state: 'enabled',
  block: false,
  grant: ['Authentication strength'],
  who: [cond('Users', 'Directory roles', [roleRef('Global Administrator'), roleRef('Privileged Role Administrator'), roleRef('Application Administrator'), roleRef('Conditional Access Administrator'), roleRef('Exchange Administrator')], exceptBg)],
  targets: [cond('Applications', 'Resources', [kw('All resources')])],
  conditions: [],
  grantControls: [val('Authentication strength: Phishing-resistant MFA')],
  session: [val('Sign-in frequency: every 4 hours'), val('Persistent browser session: never')],
})
addPolicy({
  displayName: 'CA003 - Block legacy authentication',
  state: 'enabled',
  block: true,
  grant: [],
  who: [cond('Users', 'Users', [kw('All users')], exceptBg)],
  targets: [cond('Applications', 'Resources', [kw('All resources')])],
  conditions: [cond('ClientTypes', 'Client apps', [val('Exchange ActiveSync clients'), val('Other clients')])],
  grantControls: [],
  session: [],
})
addPolicy({
  displayName: 'CA004 - Block access from blocked countries',
  state: 'enabled',
  block: true,
  grant: [],
  who: [cond('Users', 'Users', [kw('All users')], exceptBg)],
  targets: [cond('Applications', 'Resources', [kw('All resources')])],
  conditions: [cond('Locations', 'Locations', [locRef(locations[2])])],
  grantControls: [],
  session: [],
})
addPolicy({
  displayName: 'CA005 - Compliant device for Office 365 outside trusted networks',
  state: 'reporting',
  block: false,
  grant: ['Compliant device', 'Hybrid joined device'],
  who: [cond('Users', 'Users', [ref('group', allStaff)], [ref('group', guestsGroup), ...exceptBg])],
  targets: [cond('Applications', 'Resources', [kw('Office 365')])],
  conditions: [
    cond('Locations', 'Locations', [kw('Any location')], [kw('All trusted locations'), locRef(locations[0])]),
    cond('DevicePlatforms', 'Device platforms', [val('Windows'), val('macOS')]),
  ],
  grantControls: [val('Require device to be marked as compliant'), val('Require Microsoft Entra hybrid joined device')],
  session: [],
})
addPolicy({
  displayName: 'CA006 - Guests: MFA and terms of use',
  state: 'enabled',
  block: false,
  grant: ['MFA', 'Terms of use'],
  grantOperator: 'AND',
  who: [cond('Users', 'Users', [kw('Guests and external users')])],
  targets: [cond('Applications', 'Resources', [kw('All resources')], [ref('servicePrincipal', portalSp)])],
  conditions: [],
  grantControls: [val('Multifactor authentication'), val('Terms of use: Partner access agreement')],
  session: [],
})
addPolicy({
  displayName: 'CA007 - Restrict Azure management to Tier 0',
  state: 'enabled',
  block: true,
  grant: [],
  who: [cond('Users', 'Users', [kw('All users')], [ref('group', tier0), ref('group', devAdmins), ...exceptBg])],
  targets: [cond('Applications', 'Resources', [ref('servicePrincipal', azPortal), ref('servicePrincipal', azCli), ref('servicePrincipal', azPs), ref('servicePrincipal', msAdmin)])],
  conditions: [],
  grantControls: [],
  session: [],
})
addPolicy({
  displayName: 'CA008 - Workload identities from trusted IPs only',
  state: 'reporting',
  block: true,
  grant: [],
  who: [cond('ServicePrincipals', 'Workload identities', [ref('servicePrincipal', hrSp), ref('servicePrincipal', deploySp)])],
  targets: [cond('Applications', 'Resources', [kw('All resources')])],
  conditions: [cond('Locations', 'Locations', [kw('Any location')], [locRef(locations[1]), locRef(locations[0])])],
  grantControls: [],
  session: [],
})
addPolicy({
  displayName: 'CA009 - Risky sign-ins (pilot)',
  state: 'disabled',
  block: false,
  grant: ['MFA'],
  who: [cond('Users', 'Users', [ref('group', finance), ref('user', carol)], [ref('user', dave)])],
  targets: [cond('Applications', 'Resources', [kw('All resources')])],
  conditions: [cond('SignInRisks', 'Sign-in risk', [val('High'), val('Medium')]), cond('Devices', 'Device filter', [val('device.trustType -ne "ServerAD"')])],
  grantControls: [val('Multifactor authentication')],
  session: [val('Sign-in frequency: every time')],
})
addPolicy({
  displayName: 'Legacy - Intune enrollment MFA',
  state: 'enabled',
  block: false,
  grant: ['MFA'],
  who: [cond('Users', 'Users', [kw('All users')]), cond('Users', 'Directory roles', [], [roleRef('Directory Synchronization Accounts')])],
  targets: [cond('Applications', 'Resources', [ref('servicePrincipal', intune)]), cond('UserActions', 'User actions', [val('Register or join devices')])],
  conditions: [],
  grantControls: [val('Multifactor authentication')],
  session: [],
  parseError: 'Unknown condition key "AgentIdRisks" was ignored',
})

// --- Derived relations -----------------------------------------------------

const isGroup = new Set(groups.map((g) => g.id))
const userById = new Map(users.map((u) => [u.id, u]))
const groupById = new Map(groups.map((g) => [g.id, g]))

/** Groups an object is a member of, with the chain from the object. Cycles are cut. */
function ancestors(id: string): Map<string, string[]> {
  const out = new Map<string, string[]>()
  const walk = (child: string, chain: string[]) => {
    for (const [g, ms] of members)
      if (ms.has(child) && !out.has(g) && g !== id) {
        out.set(g, [...chain, g])
        walk(g, [...chain, g])
      }
  }
  walk(id, [])
  return out
}

function transitiveUsers(gid: string, seen = new Set<string>()): Set<string> {
  const out = new Set<string>()
  if (seen.has(gid)) return out
  seen.add(gid)
  for (const m of members.get(gid) ?? []) {
    if (userById.has(m)) out.add(m)
    else if (isGroup.has(m)) transitiveUsers(m, seen).forEach((u) => out.add(u))
  }
  return out
}

/** Role assignments of a principal, directly and through its groups. */
function rolesOf(id: string, transitive: boolean): RoleAssignmentRow[] {
  const anc = transitive ? ancestors(id) : new Map<string, string[]>()
  return roleAssignments
    .filter((ra) => ra.principal.id === id || anc.has(ra.principal.id!))
    .map((ra) => toRow(ra, ra.principal.id === id ? null : ra.principal, id))
}

function toRow(ra: RA, via: ObjectRef | null, principalId?: string): RoleAssignmentRow {
  const p = principalId ? (userById.get(principalId) ? ref('user', userById.get(principalId)!) : ra.principal) : ra.principal
  const u = p.type === 'user' ? userById.get(p.id!) : undefined
  return {
    id: ra.id + (principalId ?? ''),
    kind: ra.kind,
    role: ref('role', ra.role),
    principal: p,
    via,
    scope: ra.scope,
    principalEnabled: u ? u.accountEnabled : p.type === 'group' ? null : true,
    principalDirSync: u?.dirSyncEnabled ?? null,
    principalMfa: u?.mfa ?? null,
  }
}

function policyMatches(type: string, id: string): PolicyMatch[] {
  const anc = type === 'user' || type === 'group' || type === 'servicePrincipal' ? ancestors(id) : new Map<string, string[]>()
  const u = type === 'user' ? userById.get(id) : undefined
  const myRoles = type === 'user' ? rolesOf(id, true) : []
  const appIds = type === 'servicePrincipal' ? [id] : type === 'application' ? [apps.find((a) => a.id === id)?.servicePrincipal?.id] : []
  const out: PolicyMatch[] = []
  for (const p of policies) {
    const sides = { included: [] as MatchReason[], excluded: [] as MatchReason[] }
    for (const c of [...p.who, ...p.targets]) {
      for (const [side, refs] of [['included', c.include], ['excluded', c.exclude]] as const) {
        for (const r of refs) {
          const m = (via: ObjectRef[], extra: Partial<MatchReason> = {}) => sides[side].push({ condition: c.label, via, approximate: false, eligibleOnly: false, ...extra })
          if (r.id === id) m([])
          else if (r.type === 'group' && anc.has(r.id!)) m(anc.get(r.id!)!.map((g) => ref('group', groupById.get(g)!)))
          else if (u && r.displayName === 'All users' && c.key === 'Users') m([r])
          else if (u && r.displayName === 'Guests and external users' && u.userType === 'Guest') m([r], { approximate: true })
          else if (r.type === 'role') {
            const held = myRoles.find((ra) => ra.role.id === r.id)
            if (held) m(held.via ? [held.via, r] : [r], { eligibleOnly: held.kind === 'eligible' })
          } else if (c.key === 'Applications' && appIds.includes(r.id ?? '')) m([])
          else if (c.key === 'Applications' && appIds.length && r.displayName === 'All resources') m([r])
        }
      }
    }
    if (sides.included.length || sides.excluded.length)
      out.push({ policy: toPolicyRow(p), effect: sides.excluded.length ? 'excluded' : 'included', ...sides })
  }
  return out
}

function policyUsers(p: PolicyDetail, effect: 'applies' | 'excluded'): UserDetail[] {
  const side = (refs: ObjectRef[]) => {
    const s = new Set<string>()
    for (const r of refs) {
      if (r.displayName === 'All users') users.forEach((u) => s.add(u.id))
      else if (r.displayName === 'Guests and external users') users.filter((u) => u.userType === 'Guest').forEach((u) => s.add(u.id))
      else if (r.type === 'user') s.add(r.id!)
      else if (r.type === 'group') transitiveUsers(r.id!).forEach((u) => s.add(u))
      else if (r.type === 'role')
        roleAssignments.filter((ra) => ra.role.id === r.id).forEach((ra) => (ra.principal.type === 'user' ? s.add(ra.principal.id!) : ra.principal.type === 'group' && transitiveUsers(ra.principal.id!).forEach((x) => s.add(x))))
    }
    return s
  }
  const users_ = p.who.filter((c) => c.key === 'Users')
  const inc = side(users_.flatMap((c) => c.include))
  const exc = side(users_.flatMap((c) => c.exclude))
  return users.filter((u) => (effect === 'applies' ? inc.has(u.id) && !exc.has(u.id) : inc.has(u.id) && exc.has(u.id)))
}

const toPolicyRow = (p: PolicyDetail): PolicyRow => ({
  id: p.id,
  displayName: p.displayName,
  state: p.state,
  targetsAllUsers: p.targetsAllUsers,
  targetsAllApps: p.targetsAllApps,
  block: p.block,
  grant: p.grant,
  grantOperator: p.grantOperator,
  sessionControls: p.sessionControls,
  modifiedDateTime: p.modifiedDateTime,
  parseError: p.parseError,
})

// Fill counts now that every relation exists.
for (const p of policies) p.counts = { inScope: policyUsers(p, 'applies').length, excluded: policyUsers(p, 'excluded').length }
for (const l of locations) {
  l.policies = policies
    .filter((p) => p.conditions.some((c) => [...c.include, ...c.exclude].some((r) => r.id === l.id)))
    .map((p) => {
      const reason = (side: 'include' | 'exclude'): MatchReason[] =>
        p.conditions.some((c) => c[side].some((r) => r.id === l.id)) ? [{ condition: 'Locations', via: [], approximate: false, eligibleOnly: false }] : []
      const excluded = reason('exclude')
      return { policy: toPolicyRow(p), effect: excluded.length ? 'excluded' : 'included', included: reason('include'), excluded }
    })
  l.policyCount = l.policies.length
}
for (const r of roles) {
  r.activeCount = roleAssignments.filter((a) => a.role.id === r.id && a.kind === 'active').length
  r.eligibleCount = roleAssignments.filter((a) => a.role.id === r.id && a.kind === 'eligible').length
}
const memberOfCount = (id: string) => [...members.values()].filter((m) => m.has(id)).length
const ownedBy = (id: string) => [...owners].filter(([, os]) => os.includes(id)).map(([o]) => o)
for (const u of users) {
  const owned = ownedBy(u.id)
  u.counts = {
    memberOf: memberOfCount(u.id),
    roles: rolesOf(u.id, true).length,
    ownedDevices: owned.filter((o) => devices.some((d) => d.id === o)).length,
    ownedServicePrincipals: owned.filter((o) => sps.some((s) => s.id === o)).length,
    ownedApplications: owned.filter((o) => apps.some((a) => a.id === o)).length,
    ownedGroups: owned.filter((o) => isGroup.has(o)).length,
    administrativeUnits: [...auMembers.values()].filter((m) => m.has(u.id)).length,
    appRoleAssignments: appRoleAssignments.filter((a) => a.principal.id === u.id).length,
    oauth2Grants: grants.filter((g) => g.principal?.id === u.id).length,
    policies: policyMatches('user', u.id).length,
    azureRoles: u === alice || u === dave ? 2 : 0,
    pim: u === alice || u === bob ? 2 : 0,
    accessPackages: u.userType === 'Guest' || u === carol ? 1 : 0,
  }
  u.raw = { objectId: u.id, displayName: u.displayName, userPrincipalName: u.userPrincipalName, accountEnabled: u.accountEnabled, userType: u.userType, strongAuthenticationDetail: { methods: u.mfa.methods.map((m) => ({ methodType: m, isDefault: m === u.mfa.defaultMethod })) } }
}
for (const g of groups) {
  const ms = [...members.get(g.id)!]
  g.counts = {
    memberUsers: ms.filter((m) => userById.has(m)).length,
    transitiveMemberUsers: transitiveUsers(g.id).size,
    memberGroups: ms.filter((m) => isGroup.has(m)).length,
    memberServicePrincipals: ms.filter((m) => sps.some((s) => s.id === m)).length,
    memberDevices: ms.filter((m) => devices.some((d) => d.id === m)).length,
    memberOf: memberOfCount(g.id),
    owners: owners.get(g.id)?.length ?? 0,
    roles: rolesOf(g.id, false).length,
    administrativeUnits: [...auMembers.values()].filter((m) => m.has(g.id)).length,
    appRoleAssignments: appRoleAssignments.filter((a) => a.principal.id === g.id).length,
    policies: policyMatches('group', g.id).length,
    azureRoles: g === devAdmins ? 1 : 0,
  }
  g.raw = { objectId: g.id, displayName: g.displayName, securityEnabled: g.securityEnabled, groupTypes: g.groupTypes, membershipRule: g.membershipRule }
}
const PRIVILEGED = new Set(['62e90394-69f5-4237-9190-012177145e10', 'e8611ab8-c189-46e8-94e1-60213ab1f814', '7be44c8a-adaf-4e2a-84d6-ab2649e08a13', '9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3', '158c047a-c907-4556-b7ef-446551a6b5f7', 'b1be1c3e-b65d-4f19-8427-f6fa0d97feb9', '194ae4cb-b126-40b2-bd5b-6091b380977d', '29232cdf-9323-42fd-ade2-1d097af3e4de', 'fe930be7-5e62-47db-91af-98c3a49a38b1', 'c4e39bd9-1100-46d3-8c65-fb160da0071f', '3a2c62db-5318-420d-8d74-23affee5d9d5', 'd29b2b05-8046-44ba-8758-1e26182fcf32'])
for (const r of roles) r.isPrivileged = PRIVILEGED.has(r.templateId)
for (const g of groups) if (g.dirSyncEnabled) g.onPremisesSecurityIdentifier = `S-1-5-21-3623811015-3361044348-30300820-${3100 + groups.indexOf(g)}`
for (const d of devices) {
  d.owners = [ref('user', userById.get(deviceOwner.get(d.id)!)!)]
  d.counts = { owners: 1, memberOf: memberOfCount(d.id), administrativeUnits: [...auMembers.values()].filter((m) => m.has(d.id)).length }
  d.raw = { objectId: d.id, displayName: d.displayName, deviceId: d.deviceId, deviceOSType: d.deviceOSType }
}
for (const s of sps) {
  s.counts = {
    owners: owners.get(s.id)?.length ?? 0,
    memberOf: memberOfCount(s.id),
    roles: rolesOf(s.id, true).length,
    appRoleAssignments: appRoleAssignments.filter((a) => a.principal.id === s.id).length,
    appRoleAssignedTo: appRoleAssignments.filter((a) => a.resource.id === s.id).length,
    oauth2GrantsAsClient: grants.filter((g) => g.client.id === s.id).length,
    oauth2GrantsAsResource: grants.filter((g) => g.resource.id === s.id).length,
    policies: policyMatches('servicePrincipal', s.id).length,
    azureRoles: s === mi || s === deploySp ? 1 : 0,
  }
  s.raw = { objectId: s.id, displayName: s.displayName, appId: s.appId, servicePrincipalType: s.servicePrincipalType }
}
for (const a of apps) {
  a.counts = { owners: owners.get(a.id)?.length ?? 0, policies: policyMatches('application', a.id).length }
  a.raw = { objectId: a.id, displayName: a.displayName, appId: a.appId }
}
for (const a of aus) {
  const ms = [...auMembers.get(a.id)!]
  a.counts = {
    memberUsers: ms.filter((m) => userById.has(m)).length,
    memberGroups: ms.filter((m) => isGroup.has(m)).length,
    memberDevices: ms.filter((m) => devices.some((d) => d.id === m)).length,
    scopedRoles: roleAssignments.filter((r) => r.scope.id === a.id).length,
  }
}

const tenant: Tenant = {
  displayName: 'Halvorsen Maritime',
  tenantId: TENANT_ID,
  dirSyncEnabled: true,
  domains: [
    { name: DOMAIN, type: 'Managed', capabilities: ['Email', 'OfficeCommunicationsOnline'], isDefault: true, isInitial: false },
    { name: 'halvorsenmaritime.onmicrosoft.com', type: 'Managed', capabilities: ['Email', 'OfficeCommunicationsOnline'], isDefault: false, isInitial: true },
    { name: 'hm-crew.no', type: 'Federated', capabilities: ['Email'], isDefault: false, isInitial: false },
  ],
  authorizationPolicy: {
    selfServicePasswordReset: true,
    blockMsolPowerShell: false,
    usersCanRegisterApps: true,
    usersCanCreateSecurityGroups: false,
    usersCanReadOtherUsers: true,
    userConsent: 'Allow consent for apps from verified publishers, for selected permissions',
    userConsentPolicy: 'verifiedPublishers',
    guestRole: 'limited',
    guestInvitesFrom: 'adminsAndGuestInviters',
    guestAccess: 'Guests have limited access to properties and memberships of directory objects',
    guestInvites: 'Members and guests with the Guest Inviter role',
  },
  directorySettings: [
    {
      name: 'Password protection',
      values: [
        { name: 'Lockout threshold', value: '10' },
        { name: 'Lockout duration', value: '60 seconds' },
        { name: 'Banned password list', value: 'Enabled: halvorsen, maritime, bergen, vessel' },
        { name: 'On-premises protection', value: 'Audit mode' },
      ],
    },
  ],
  raw: { objectId: TENANT_ID, displayName: 'Halvorsen Maritime' },
}

// --- Advanced filtering ------------------------------------------------------

/* eslint-disable @typescript-eslint/no-explicit-any */
interface FieldSpec {
  label: string
  type: FilterType
  get: (row: any) => unknown
  /** Enum labels when they differ from the raw values. */
  labels?: Record<string, string>
}
const text = (label: string, key: string): FieldSpec => ({ label, type: 'text', get: (r) => r[key] })
const bool_ = (label: string, get: (r: any) => unknown): FieldSpec => ({ label, type: 'bool', get })
const enum_ = (label: string, get: (r: any) => unknown, labels?: Record<string, string>): FieldSpec => ({ label, type: 'enum', get, labels })
const num = (label: string, key: string): FieldSpec => ({ label, type: 'number', get: (r) => r[key] })
const date = (label: string, key: string): FieldSpec => ({ label, type: 'date', get: (r) => r[key] })
const mfaKinds = (u: UserRow) => [...u.mfa.methods, ...(u.mfa.fido ? ['Fido'] : []), ...(u.mfa.windowsHello ? ['WindowsHello'] : [])]
const scopeType = (r: RoleAssignmentRow) => (r.scope.type === 'keyword' ? 'Directory' : r.scope.type === 'administrativeUnit' ? 'Administrative unit' : 'Application')

const FIELDS: Record<FilterResource, Record<string, FieldSpec>> = {
  users: {
    displayName: text('Name', 'displayName'),
    userPrincipalName: text('UPN', 'userPrincipalName'),
    mail: text('Mail', 'mail'),
    userType: enum_('Type', (u) => u.userType),
    accountEnabled: bool_('Enabled', (u) => u.accountEnabled),
    dirSyncEnabled: bool_('Synced from AD', (u) => u.dirSyncEnabled),
    department: enum_('Department', (u) => u.department),
    jobTitle: enum_('Job title', (u) => u.jobTitle),
    mobile: text('Mobile', 'mobile'),
    lastPasswordChangeDateTime: date('Password changed', 'lastPasswordChangeDateTime'),
    mfaMethod: enum_('MFA method', mfaKinds, {
      PhoneAppNotification: 'Authenticator notification', PhoneAppOTP: 'Authenticator code', OneWaySms: 'Text message',
      TwoWayVoiceMobile: 'Phone call', Fido: 'FIDO2 key', WindowsHello: 'Windows Hello',
    }),
    hasMfa: bool_('Has MFA', (u) => mfaKinds(u).length > 0),
    perUserMfa: enum_('Per-user MFA', (u) => u.mfa.perUserMfa ?? 'Disabled'),
  },
  groups: {
    displayName: text('Name', 'displayName'),
    description: text('Description', 'description'),
    mail: text('Mail', 'mail'),
    kind: enum_('Type', (g) => (g.groupTypes.includes('Unified') ? 'Microsoft 365' : g.mailEnabled && !g.securityEnabled ? 'Distribution' : 'Security')),
    isAssignableToRole: bool_('Role assignable', (g) => g.isAssignableToRole),
    dynamic: bool_('Dynamic membership', (g) => !!g.membershipRule),
    membershipRule: text('Membership rule', 'membershipRule'),
    isPublic: bool_('Public', (g) => g.isPublic),
    dirSyncEnabled: bool_('Synced from AD', (g) => g.dirSyncEnabled),
    createdDateTime: date('Created', 'createdDateTime'),
  },
  devices: {
    displayName: text('Name', 'displayName'),
    deviceOSType: enum_('OS', (d) => d.deviceOSType),
    deviceOSVersion: text('OS version', 'deviceOSVersion'),
    deviceTrustType: enum_('Trust type', (d) => d.deviceTrustType, { AzureAd: 'Entra joined', ServerAd: 'Hybrid joined', Workplace: 'Registered' }),
    deviceManufacturer: enum_('Manufacturer', (d) => d.deviceManufacturer),
    deviceModel: enum_('Model', (d) => d.deviceModel),
    accountEnabled: bool_('Enabled', (d) => d.accountEnabled),
    isCompliant: bool_('Compliant', (d) => d.isCompliant),
    isManaged: bool_('Managed', (d) => d.isManaged),
    isRooted: bool_('Rooted', (d) => d.isRooted),
  },
  'administrative-units': {
    displayName: text('Name', 'displayName'),
    description: text('Description', 'description'),
    dynamic: bool_('Dynamic membership', (a) => !!a.membershipRule),
  },
  'service-principals': {
    displayName: text('Name', 'displayName'),
    appId: text('App ID', 'appId'),
    servicePrincipalType: enum_('Type', (s) => s.servicePrincipalType),
    publisherName: enum_('Publisher', (s) => s.publisherName),
    microsoftFirstParty: bool_('Microsoft app', (s) => s.microsoftFirstParty),
    accountEnabled: bool_('Enabled', (s) => s.accountEnabled),
    appRoleAssignmentRequired: bool_('Assignment required', (s) => s.appRoleAssignmentRequired),
    passwordCount: num('Secrets', 'passwordCount'),
    keyCount: num('Certificates', 'keyCount'),
    appRoleCount: num('App roles', 'appRoleCount'),
    hasCustomOwner: bool_('Has owner', (s) => s.hasCustomOwner),
  },
  applications: {
    displayName: text('Name', 'displayName'),
    appId: text('App ID', 'appId'),
    availableToOtherTenants: bool_('Multitenant', (a) => a.availableToOtherTenants),
    publicClient: bool_('Public client', (a) => a.publicClient),
    oauth2AllowImplicitFlow: bool_('Implicit flow', (a) => a.oauth2AllowImplicitFlow),
    passwordCount: num('Secrets', 'passwordCount'),
    keyCount: num('Certificates', 'keyCount'),
    appRoleCount: num('App roles', 'appRoleCount'),
    hasCustomOwner: bool_('Has owner', (a) => a.hasCustomOwner),
  },
  roles: {
    displayName: text('Name', 'displayName'),
    isBuiltIn: bool_('Built-in', (r) => r.isBuiltIn),
    activeCount: num('Active assignments', 'activeCount'),
    eligibleCount: num('Eligible assignments', 'eligibleCount'),
  },
  'role-assignments': {
    role: enum_('Role', (r) => r.role.displayName),
    principalType: enum_('Principal type', (r) => r.principal.type, { user: 'User', group: 'Group', servicePrincipal: 'Service principal' }),
    kind: enum_('Assignment', (r) => r.kind, { active: 'Active', eligible: 'Eligible' }),
    scopeType: enum_('Scope', scopeType),
    principalEnabled: bool_('Principal enabled', (r) => r.principalEnabled),
    viaGroup: bool_('Through a group', (r) => !!r.via),
  },
  'app-role-assignments': {
    principalType: enum_('Principal type', (r) => r.principal.type, { user: 'User', group: 'Group', servicePrincipal: 'Service principal' }),
    resource: enum_('Application', (r) => r.resource.displayName),
    value: text('Role', 'value'),
    createdDateTime: date('Assigned', 'createdDateTime'),
  },
  'oauth2-grants': {
    consentType: enum_('Consent', (g) => g.consentType, { AllPrincipals: 'All users', Principal: 'One user' }),
    client: enum_('Granted to', (g) => g.client.displayName),
    resource: enum_('On API', (g) => g.resource.displayName),
    scope: enum_('Scope', (g) => g.scopes),
    expiryTime: date('Expires', 'expiryTime'),
  },
  policies: {
    displayName: text('Name', 'displayName'),
    state: enum_('State', (p) => p.state, { enabled: 'Enabled', reporting: 'Report-only', disabled: 'Disabled' }),
    block: bool_('Blocks access', (p) => p.block),
    targetsAllUsers: bool_('All users', (p) => p.targetsAllUsers),
    targetsAllApps: bool_('All resources', (p) => p.targetsAllApps),
    grant: enum_('Grant control', (p) => p.grant),
    sessionControls: enum_('Session control', (p) => p.sessionControls),
    modifiedDateTime: date('Modified', 'modifiedDateTime'),
  },
  'azure-role-assignments': {
    role: { label: 'Role', type: 'text', get: (r) => r.role.displayName },
    kind: enum_('Assignment', (r) => r.kind, { active: 'Active', eligible: 'Eligible' }),
    scopeType: enum_('Scope level', (r) => (r.scope.includes('/providers/Microsoft.Management/managementGroups') ? 'managementGroup' : r.scope.includes('/providers/') ? 'resource' : r.scope.includes('/resourceGroups/') ? 'resourceGroup' : 'subscription'), { managementGroup: 'Management group', subscription: 'Subscription', resourceGroup: 'Resource group', resource: 'Resource' }),
    viaGroup: bool_('Through a group', (r) => !!r.via),
    conditional: bool_('Conditional', (r) => r.conditional),
  },
  'pim-assignments': {
    role: text('Role', 'role'),
    resourceType: enum_('Resource', (r) => r.resourceType, { directoryRole: 'Directory role', group: 'Group', other: 'Other' }),
    kind: enum_('Assignment', (r) => r.kind, { active: 'Active', eligible: 'Eligible' }),
    approvalRequired: bool_('Approval required', (r) => r.approvalRequired),
    permanent: bool_('Permanent', (r) => !r.endDateTime),
  },
  'access-package-policies': {
    packageName: text('Access package', 'packageName'),
    approvalRequired: bool_('Approval required', (r) => r.approvalRequired),
    renewable: bool_('Renewable', (r) => r.renewable),
  },
  'named-locations': {
    displayName: text('Name', 'displayName'),
    kind: enum_('Kind', (l) => l.kind, { ip: 'IP ranges', country: 'Countries' }),
    trusted: bool_('Trusted', (l) => l.trusted),
    policyCount: num('Used by policies', 'policyCount'),
  },
}

const SOURCES: Record<FilterResource, () => any[]> = {
  users: () => users,
  groups: () => groups,
  devices: () => devices,
  'administrative-units': () => aus,
  'service-principals': () => sps,
  applications: () => apps,
  roles: () => roles,
  'role-assignments': () => roleAssignments.map((ra) => toRow(ra, null)),
  'app-role-assignments': () => appRoleAssignments,
  'oauth2-grants': () => grants,
  policies: () => policies,
  'named-locations': () => locations,
  // Per-principal lists: enum options come from the labels.
  'azure-role-assignments': () => [],
  'pim-assignments': () => [],
  'access-package-policies': () => [],
}

function fieldCatalog(resource: FilterResource): FilterField[] {
  return Object.entries(FIELDS[resource]).map(([key, f]) => {
    if (f.type !== 'enum') return { key, label: f.label, type: f.type }
    const values = new Set<string>()
    for (const r of SOURCES[resource]()) [f.get(r)].flat().forEach((v) => v !== null && v !== undefined && v !== '' && values.add(String(v)))
    if (values.size === 0) Object.keys(f.labels ?? {}).forEach((v) => values.add(v))
    return { key, label: f.label, type: f.type, options: [...values].sort().slice(0, 200).map((v) => ({ value: v, label: f.labels?.[v] ?? v })) }
  })
}

function matches(f: FieldSpec, row: any, op: string, arg: string): boolean {
  const raw = f.get(row)
  const vals = [raw].flat().filter((v) => v !== null && v !== undefined && v !== '')
  const lc = arg.toLowerCase()
  const s = (v: unknown) => String(v).toLowerCase()
  switch (op) {
    case 'empty': return vals.length === 0
    case 'notEmpty': return vals.length > 0
    case 'contains': return vals.some((v) => s(v).includes(lc))
    case 'notContains': return !vals.some((v) => s(v).includes(lc))
    case 'startsWith': return vals.some((v) => s(v).startsWith(lc))
    case 'endsWith': return vals.some((v) => s(v).endsWith(lc))
    case 'eq': return f.type === 'bool' ? String(!!raw) === arg : f.type === 'number' ? Number(raw) === Number(arg) : vals.some((v) => s(v) === lc)
    case 'ne': return f.type === 'number' ? Number(raw) !== Number(arg) : !vals.some((v) => s(v) === lc)
    case 'in': return arg.split(',').map(decodeURIComponent).some((a) => vals.some((v) => String(v) === a))
    case 'notIn': return !arg.split(',').map(decodeURIComponent).some((a) => vals.some((v) => String(v) === a))
    case 'gt': return f.type === 'number' ? Number(raw) > Number(arg) : vals.some((v) => String(v) > arg)
    case 'lt': return f.type === 'number' ? Number(raw) < Number(arg) : vals.some((v) => String(v) < arg)
    default: return true
  }
}

function applyFilters<T>(rows: T[], q: URLSearchParams, resource?: FilterResource): T[] {
  if (!resource) return rows
  const fs = q.getAll('filter').flatMap((raw) => {
    const a = raw.indexOf(':')
    const b = raw.indexOf(':', a + 1)
    const spec = FIELDS[resource][raw.slice(0, a)]
    return spec && b > a ? [{ spec, op: raw.slice(a + 1, b), arg: raw.slice(b + 1) }] : []
  })
  if (fs.length === 0) return rows
  const any = q.get('match') === 'any'
  return rows.filter((r) => (any ? fs.some((f) => matches(f.spec, r, f.op, f.arg)) : fs.every((f) => matches(f.spec, r, f.op, f.arg))))
}
/* eslint-enable @typescript-eslint/no-explicit-any */

// --- Route handlers --------------------------------------------------------

type Q = URLSearchParams
const bool = (q: Q, k: string) => (q.has(k) ? q.get(k) === 'true' : undefined)

function paginate<T>(items: T[], q: Q, text: (t: T) => string, sorters: Record<string, (t: T) => string | number> = {}, resource?: FilterResource): Page<T> {
  let r = applyFilters(items, q, resource)
  const s = q.get('q')?.toLowerCase()
  if (s) r = r.filter((t) => text(t).toLowerCase().includes(s))
  const sort = sorters[q.get('sort') ?? '']
  if (sort) {
    r = [...r].sort((a, b) => {
      const x = sort(a)
      const y = sort(b)
      return typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))
    })
    if (q.get('order') === 'desc') r.reverse()
  }
  const page = Number(q.get('page') ?? 1)
  const size = Number(q.get('page_size') ?? 50)
  return { items: r.slice((page - 1) * size, page * size), total: r.length, page, page_size: size }
}

const strip = <T extends { counts: unknown; raw: unknown }>({ counts: _c, raw: _r, ...row }: T) => row // eslint-disable-line @typescript-eslint/no-unused-vars
const byName = { displayName: (t: { displayName: string }) => t.displayName.toLowerCase() }
const directMembers = (gid: string, transitive: boolean): Set<string> => {
  if (!transitive) return members.get(gid) ?? new Set()
  const out = new Set<string>()
  const walk = (g: string, seen: Set<string>) => {
    if (seen.has(g)) return
    seen.add(g)
    for (const m of members.get(g) ?? []) {
      out.add(m)
      if (isGroup.has(m)) walk(m, seen)
    }
  }
  walk(gid, new Set())
  return out
}

function listUsers(q: Q, base = users): Page<UserRow> {
  let r = base
  const t = q.get('userType')
  if (t) r = r.filter((u) => u.userType === t)
  const en = bool(q, 'accountEnabled')
  if (en !== undefined) r = r.filter((u) => u.accountEnabled === en)
  const ds = bool(q, 'dirSyncEnabled')
  if (ds !== undefined) r = r.filter((u) => !!u.dirSyncEnabled === ds)
  if (q.get('memberOf')) {
    const ms = directMembers(q.get('memberOf')!, bool(q, 'transitive') ?? false)
    r = r.filter((u) => ms.has(u.id))
  }
  if (q.get('ownerOf')) r = r.filter((u) => owners.get(q.get('ownerOf')!)?.includes(u.id))
  if (q.get('memberOfAu')) r = r.filter((u) => auMembers.get(q.get('memberOfAu')!)?.has(u.id))
  const m = q.get('mfa')
  if (m === 'none') r = r.filter((u) => u.mfa.methods.length + u.mfa.fido + u.mfa.windowsHello === 0)
  if (m === 'app') r = r.filter((u) => u.mfa.methods.some((x) => x.startsWith('PhoneApp')))
  if (m === 'phone') r = r.filter((u) => u.mfa.methods.some((x) => x.includes('Voice') || x === 'OneWaySms'))
  if (m === 'fido') r = r.filter((u) => u.mfa.fido > 0)
  if (m === 'windowsHello') r = r.filter((u) => u.mfa.windowsHello > 0)
  const pu = q.get('perUserMfa')
  if (pu) r = r.filter((u) => (u.mfa.perUserMfa ?? 'Disabled') === pu)
  return paginate(r.map(strip), q, (u) => `${u.displayName} ${u.userPrincipalName} ${u.id}`, {
    ...byName,
    userPrincipalName: (u) => u.userPrincipalName.toLowerCase(),
    lastPasswordChangeDateTime: (u) => u.lastPasswordChangeDateTime ?? '',
  }, 'users')
}

const handlers: [string, (p: Record<string, string>, q: Q) => unknown][] = [
  ['/api/filters/{resource}', ({ resource }) => (resource in FIELDS ? fieldCatalog(resource as FilterResource) : undefined)],
  ['/api/stats', (): Stats => ({ users: users.length, guests: users.filter((u) => u.userType === 'Guest').length, groups: groups.length, devices: devices.length, servicePrincipals: sps.length, applications: apps.length, administrativeUnits: aus.length, roles: roles.length, policies: policies.length, namedLocations: locations.length })],
  ['/api/tenant', () => tenant],
  [
    '/api/search',
    (_, q): SearchResult => {
      const s = (q.get('q') ?? '').toLowerCase()
      const lim = Number(q.get('limit') ?? 5)
      const sets: [ObjectType, ObjectRef[]][] = [
        ['user', users.map((u) => ref('user', u))],
        ['group', groups.map((g) => ref('group', g))],
        ['servicePrincipal', sps.map((x) => ref('servicePrincipal', x))],
        ['application', apps.map((a) => ref('application', a))],
        ['device', devices.map((d) => ref('device', d))],
        ['role', roles.map((r) => ref('role', r))],
        ['policy', policies.map((p) => ref('policy', p))],
      ]
      return {
        groups: sets.map(([type, refs]) => {
          const hits = refs.filter((r) => `${r.displayName} ${r.sub ?? ''} ${r.id}`.toLowerCase().includes(s))
          return { type, total: hits.length, items: hits.slice(0, lim) }
        }),
      }
    },
  ],
  ['/api/users', (_, q) => listUsers(q, q.get('excludeMailboxOnly') ? users.filter((u) => u !== syncAccount) : users)],
  ['/api/users/{id}', ({ id }) => userById.get(id)],
  [
    '/api/groups',
    (_, q) => {
      let r = groups
      const mid = q.get('memberId')
      if (mid) {
        const anc = bool(q, 'transitive') ? ancestors(mid) : new Map([...members].filter(([, ms]) => ms.has(mid)).map(([g]) => [g, [g]]))
        r = r.filter((g) => anc.has(g.id))
      }
      if (q.get('memberOf')) {
        const ms = directMembers(q.get('memberOf')!, bool(q, 'transitive') ?? false)
        r = r.filter((g) => ms.has(g.id))
      }
      if (q.get('ownerId')) r = r.filter((g) => owners.get(g.id)?.includes(q.get('ownerId')!))
      if (q.get('memberOfAu')) r = r.filter((g) => auMembers.get(q.get('memberOfAu')!)?.has(g.id))
      const ra = bool(q, 'isAssignableToRole')
      if (ra !== undefined) r = r.filter((g) => !!g.isAssignableToRole === ra)
      const dyn = bool(q, 'dynamic')
      if (dyn !== undefined) r = r.filter((g) => !!g.membershipRule === dyn)
      const kind = q.get('kind')
      if (kind) r = r.filter((g) => g.groupTypes.includes('Unified') === (kind === 'microsoft365'))
      const ds = bool(q, 'dirSyncEnabled')
      if (ds !== undefined) r = r.filter((g) => !!g.dirSyncEnabled === ds)
      return paginate(r.map(strip).map(({ pimEnabled: _p, ...g }) => g), q, (g) => `${g.displayName} ${g.mail ?? ''} ${g.id}`, { ...byName, createdDateTime: (g) => g.createdDateTime ?? '' }, 'groups') // eslint-disable-line @typescript-eslint/no-unused-vars
    },
  ],
  ['/api/groups/{id}', ({ id }) => groupById.get(id)],
  [
    '/api/groups/{id}/pim',
    ({ id }): GroupPim | null =>
      id === tier0.id
        ? {
            onboardedDateTime: daysAgo(320),
            memberApprovalRequired: false,
            ownerApprovalRequired: true,
            members: [
              { subject: ref('user', alice), kind: 'eligible', startDateTime: daysAgo(300), endDateTime: null },
              { subject: ref('user', bob), kind: 'eligible', startDateTime: daysAgo(30), endDateTime: daysAgo(-150) },
              { subject: ref('user', carol), kind: 'active', startDateTime: daysAgo(2), endDateTime: daysAgo(-1) },
            ],
            owners: [{ subject: ref('user', alice), kind: 'active', startDateTime: daysAgo(320), endDateTime: null }],
          }
        : null,
  ],
  [
    '/api/devices',
    (_, q) => {
      let r = devices
      if (q.get('memberOf')) r = r.filter((d) => members.get(q.get('memberOf')!)?.has(d.id))
      if (q.get('ownerId')) r = r.filter((d) => deviceOwner.get(d.id) === q.get('ownerId'))
      if (q.get('memberOfAu')) r = r.filter((d) => auMembers.get(q.get('memberOfAu')!)?.has(d.id))
      for (const k of ['isCompliant', 'isManaged', 'accountEnabled'] as const) {
        const v = bool(q, k)
        if (v !== undefined) r = r.filter((d) => !!d[k] === v)
      }
      for (const k of ['deviceTrustType', 'deviceOSType'] as const) if (q.get(k)) r = r.filter((d) => d[k] === q.get(k))
      return paginate(r.map(strip).map(({ bitLockerKeys: _b, ...d }) => d), q, (d) => `${d.displayName} ${d.deviceId} ${d.id}`, { ...byName, deviceOSType: (d) => d.deviceOSType ?? '' }, 'devices') // eslint-disable-line @typescript-eslint/no-unused-vars
    },
  ],
  ['/api/devices/{id}', ({ id }) => devices.find((d) => d.id === id)],
  [
    '/api/administrative-units',
    (_, q) => {
      const mid = q.get('memberId')
      return paginate(aus.filter((a) => !mid || auMembers.get(a.id)!.has(mid)).map(strip), q, (a) => a.displayName, byName, 'administrative-units')
    },
  ],
  ['/api/administrative-units/{id}', ({ id }) => aus.find((a) => a.id === id)],
  [
    '/api/service-principals',
    (_, q) => {
      let r = sps
      if (q.get('memberOf')) r = r.filter((s) => members.get(q.get('memberOf')!)?.has(s.id))
      if (q.get('ownerId')) r = r.filter((s) => owners.get(s.id)?.includes(q.get('ownerId')!))
      if (q.get('servicePrincipalType')) r = r.filter((s) => s.servicePrincipalType === q.get('servicePrincipalType'))
      const mf = bool(q, 'microsoftFirstParty')
      if (mf !== undefined) r = r.filter((s) => !!s.microsoftFirstParty === mf)
      const hc = bool(q, 'hasCredentials')
      if (hc !== undefined) r = r.filter((s) => s.passwordCount + s.keyCount > 0 === hc)
      return paginate(
        r.map((s) => ({ id: s.id, displayName: s.displayName, appId: s.appId, servicePrincipalType: s.servicePrincipalType, publisherName: s.publisherName, microsoftFirstParty: s.microsoftFirstParty, accountEnabled: s.accountEnabled, appRoleAssignmentRequired: s.appRoleAssignmentRequired, passwordCount: s.passwordCount, keyCount: s.keyCount, appRoleCount: s.appRoleCount, oauth2PermissionCount: s.oauth2PermissionCount, hasCustomOwner: s.hasCustomOwner })),
        q,
        (s) => `${s.displayName} ${s.appId} ${s.id}`,
        { ...byName, publisherName: (s) => s.publisherName ?? '' },
        'service-principals',
      )
    },
  ],
  ['/api/service-principals/{id}', ({ id }) => sps.find((s) => s.id === id)],
  [
    '/api/applications',
    (_, q) => {
      let r = apps
      if (q.get('ownerId')) r = r.filter((a) => owners.get(a.id)?.includes(q.get('ownerId')!))
      for (const k of ['availableToOtherTenants', 'publicClient'] as const) {
        const v = bool(q, k)
        if (v !== undefined) r = r.filter((a) => !!a[k] === v)
      }
      const hc = bool(q, 'hasCredentials')
      if (hc !== undefined) r = r.filter((a) => a.passwordCount + a.keyCount > 0 === hc)
      return paginate(
        r.map((a) => ({ id: a.id, displayName: a.displayName, appId: a.appId, availableToOtherTenants: a.availableToOtherTenants, homepage: a.homepage, publicClient: a.publicClient, oauth2AllowImplicitFlow: a.oauth2AllowImplicitFlow, passwordCount: a.passwordCount, keyCount: a.keyCount, appRoleCount: a.appRoleCount, oauth2PermissionCount: a.oauth2PermissionCount, hasCustomOwner: a.hasCustomOwner })),
        q,
        (a) => `${a.displayName} ${a.appId} ${a.id}`,
        byName,
        'applications',
      )
    },
  ],
  ['/api/applications/{id}', ({ id }) => apps.find((a) => a.id === id)],
  [
    '/api/owners',
    (_, q) => {
      const refs = (owners.get(q.get('ownerOf') ?? '') ?? []).map((o) => (userById.has(o) ? ref('user', userById.get(o)!) : ref('servicePrincipal', sps.find((s) => s.id === o)!)))
      return paginate(refs, q, (r) => r.displayName, byName)
    },
  ],
  [
    '/api/roles',
    (_, q) => {
      let r = roles
      const ha = bool(q, 'hasAssignments')
      if (ha !== undefined) r = r.filter((x) => x.activeCount + x.eligibleCount > 0 === ha)
      const bi = bool(q, 'isBuiltIn')
      if (bi !== undefined) r = r.filter((x) => x.isBuiltIn === bi)
      return paginate(r.map(({ allowedResourceActions: _a, raw: _r, ...x }) => x), q, (x) => x.displayName, { ...byName, activeCount: (x) => x.activeCount, eligibleCount: (x) => x.eligibleCount }, 'roles') // eslint-disable-line @typescript-eslint/no-unused-vars
    },
  ],
  ['/api/roles/{id}', ({ id }) => roles.find((r) => r.id === id)],
  [
    '/api/role-assignments',
    (_, q) => {
      let rows: RoleAssignmentRow[]
      if (q.get('principalId')) rows = rolesOf(q.get('principalId')!, bool(q, 'transitive') ?? false)
      else {
        const ras = roleAssignments.filter((ra) => (!q.get('roleId') || ra.role.id === q.get('roleId')) && (!q.get('scopeId') || ra.scope.id === q.get('scopeId')))
        rows = ras.flatMap((ra) =>
          bool(q, 'expandGroups') && ra.principal.type === 'group' ? [...transitiveUsers(ra.principal.id!)].map((u) => toRow(ra, ra.principal, u)) : [toRow(ra, null)],
        )
      }
      if (q.get('kind')) rows = rows.filter((r) => r.kind === q.get('kind'))
      return paginate(rows, q, (r) => `${r.principal.displayName} ${r.principal.sub ?? ''} ${r.role.displayName}`, { principal: (r) => r.principal.displayName.toLowerCase() }, 'role-assignments')
    },
  ],
  [
    '/api/app-role-assignments',
    (_, q) => {
      let r = appRoleAssignments
      if (q.get('principalId')) r = r.filter((a) => a.principal.id === q.get('principalId'))
      if (q.get('resourceId')) r = r.filter((a) => a.resource.id === q.get('resourceId'))
      const pt = q.get('principalType')
      if (pt) r = r.filter((a) => a.principal.type === ({ User: 'user', Group: 'group', ServicePrincipal: 'servicePrincipal' } as Record<string, string>)[pt])
      return paginate(r, q, (a) => `${a.principal.displayName} ${a.resource.displayName} ${a.value}`, {
        principal: (a) => a.principal.displayName.toLowerCase(),
        resource: (a) => a.resource.displayName.toLowerCase(),
        createdDateTime: (a) => a.createdDateTime ?? '',
      }, 'app-role-assignments')
    },
  ],
  [
    '/api/oauth2-grants',
    (_, q) => {
      let r = grants
      for (const k of ['clientId', 'resourceId', 'principalId'] as const) {
        const v = q.get(k)
        if (v) r = r.filter((g) => ({ clientId: g.client.id, resourceId: g.resource.id, principalId: g.principal?.id })[k] === v)
      }
      if (q.get('consentType')) r = r.filter((g) => g.consentType === q.get('consentType'))
      return paginate(r, q, (g) => `${g.client.displayName} ${g.resource.displayName} ${g.principal?.displayName ?? ''} ${g.scopes.join(' ')}`, {
        client: (g) => g.client.displayName.toLowerCase(),
        resource: (g) => g.resource.displayName.toLowerCase(),
      }, 'oauth2-grants')
    },
  ],
  [
    '/api/azure-role-assignments',
    ({}, q) => {
      const pid = q.get('principalId')!
      const anc = ancestors(pid)
      const rows: AzureRoleAssignmentRow[] = []
      if (pid === alice.id || anc.has(devAdmins.id))
        rows.push({ id: guid(), kind: 'active', role: { displayName: 'Owner', description: 'Grants full access to manage all resources', isBuiltIn: true }, principal: ref('group', devAdmins), via: pid === devAdmins.id ? null : ref('group', devAdmins), scope: '/subscriptions/4f1d2c3b-9a8e-4d7c-b6a5-0e1f2a3b4c5d', conditional: false })
      if (pid === alice.id || pid === dave.id)
        rows.push({ id: guid(), kind: 'eligible', role: { displayName: 'User Access Administrator', description: 'Lets you manage user access to Azure resources', isBuiltIn: true }, principal: ref('user', userById.get(pid)!), via: null, scope: '/providers/Microsoft.Management/managementGroups/hm-root', conditional: true })
      if (pid === mi.id)
        rows.push({ id: guid(), kind: 'active', role: { displayName: 'Storage Blob Data Contributor', description: null, isBuiltIn: true }, principal: ref('servicePrincipal', mi), via: null, scope: '/subscriptions/4f1d2c3b-9a8e-4d7c-b6a5-0e1f2a3b4c5d/resourceGroups/rg-telemetry/providers/Microsoft.Storage/storageAccounts/sttelemetryprod', conditional: false })
      if (pid === deploySp.id)
        rows.push({ id: guid(), kind: 'active', role: { displayName: 'Contributor', description: null, isBuiltIn: true }, principal: ref('servicePrincipal', deploySp), via: null, scope: '/subscriptions/4f1d2c3b-9a8e-4d7c-b6a5-0e1f2a3b4c5d/resourceGroups/rg-infra', conditional: false })
      return paginate(rows, q, (r) => r.role.displayName, {}, 'azure-role-assignments')
    },
  ],
  [
    '/api/pim-assignments',
    (_, q) => {
      const pid = q.get('principalId')!
      const rows: PimAssignmentRow[] = []
      if (pid === alice.id || pid === bob.id) {
        rows.push({ id: guid(), kind: 'eligible', resourceType: 'group', resource: ref('group', tier0), role: 'Member', via: null, approvalRequired: false, startDateTime: daysAgo(300), endDateTime: pid === bob.id ? daysAgo(-150) : null })
        rows.push({ id: guid(), kind: 'eligible', resourceType: 'directoryRole', resource: roleRef('Global Administrator'), role: 'Global Administrator', via: ref('group', tier0), approvalRequired: true, startDateTime: daysAgo(300), endDateTime: null })
      }
      return paginate(rows, q, (r) => r.role, {}, 'pim-assignments')
    },
  ],
  [
    '/api/access-package-policies',
    (_, q) => {
      const u = userById.get(q.get('userId')!)
      const rows: AccessPackagePolicyRow[] = []
      if (u && (u.userType === 'Guest' || u === carol))
        rows.push({
          id: guid(),
          packageName: 'Partner collaboration',
          packageDescription: 'Access for shipyard partners',
          policyName: u.userType === 'Guest' ? 'External users from connected organisations' : 'Internal sponsors',
          resources: [
            { kind: 'Group', resource: ref('group', m365), role: 'Member' },
            { kind: 'Application', resource: ref('servicePrincipal', portalSp), role: 'Crew.Read' },
            { kind: 'SharePoint site', resource: val('https://halvorsenmaritime.sharepoint.com/sites/shipyard'), role: 'Visitors' },
          ],
          approvalRequired: u.userType === 'Guest',
          approvers: u.userType === 'Guest' ? ['Stage 1: Sponsor', 'Fallback: Ingrid Halvorsen'] : [],
          durationDays: 90,
          renewable: true,
          via: u.userType === 'Guest' ? kw('All external users') : ref('group', finance),
        })
      return paginate(rows, q, (r) => r.packageName, {}, 'access-package-policies')
    },
  ],
  [
    '/api/policies',
    (_, q) => {
      let r = policies
      if (q.get('state')) r = r.filter((p) => p.state === q.get('state'))
      const b = bool(q, 'block')
      if (b !== undefined) r = r.filter((p) => p.block === b)
      return paginate(r.map(toPolicyRow), q, (p) => p.displayName, { ...byName, state: (p) => p.state, modifiedDateTime: (p) => p.modifiedDateTime ?? '' }, 'policies')
    },
  ],
  ['/api/policies/{id}', ({ id }) => policies.find((p) => p.id === id)],
  [
    '/api/policies/{id}/users',
    ({ id }, q) => {
      const p = policies.find((x) => x.id === id)
      return p && listUsers(q, policyUsers(p, (q.get('effect') as 'applies' | 'excluded') ?? 'applies'))
    },
  ],
  ['/api/policies/affecting/{type}/{id}', ({ type, id }) => policyMatches(type, id)],
  ['/api/named-locations', (_, q) => paginate(locations.map(({ policies: _p, raw: _r, ...l }) => l), q, (l) => l.displayName, byName, 'named-locations')], // eslint-disable-line @typescript-eslint/no-unused-vars
  ['/api/named-locations/{id}', ({ id }) => locations.find((l) => l.id === id)],
]

const compiled = handlers.map(([tpl, fn]) => {
  const keys: string[] = []
  const re = new RegExp('^' + tpl.replace(/\{(\w+)\}/g, (_, k: string) => (keys.push(k), '([^/]+)')) + '$')
  return { re, keys, fn }
})

export const mockFetch: typeof fetch = async (input) => {
  const url = new URL(String(input), window.location.origin)
  await new Promise((r) => setTimeout(r, 80 + Math.random() * 120))
  for (const { re, keys, fn } of compiled) {
    const m = url.pathname.match(re)
    if (!m) continue
    const params = Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(m[i + 1])]))
    const body = fn(params, url.searchParams)
    if (body === undefined) return new Response('Not found', { status: 404 })
    return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } })
  }
  return new Response('No mock for this route', { status: 404 })
}
