#!/usr/bin/env python3
"""
Generate a synthetic but realistic roadrecon.db for testing the ROADrecon GUI.

The data is built to match what ``roadrecon gather`` (and pimgather / iggather /
azgather) really store, so the GUI backend can be developed and tested without a
real tenant dump. JSON columns use the exact casing and nesting the gatherers and
the ``policies`` plugin expect.

Usage:
    python roadrecon/tests/gendb.py -o roadrecon.db [--users N] [--seed S] [--minimal]

Also exposes ``generate(path, users=300, seed=1, minimal=False)`` for pytest.

Everything is deterministic for a given seed. Rows are written with Core bulk
inserts (fast: 50k users build in a few seconds). The only object type that
scales with --users is Users (plus their group memberships and MFA); every other
object type is a fixed, hand-built set that covers every table and link the GUI
reads.
"""
import argparse
import base64
import datetime
import json
import os
import random
import sys
import uuid
import zlib

import roadtools.roadlib.metadef.database as database
from roadtools.roadlib.metadef import database as db
from roadtools.roadrecon.plugins import policyanalysis

# Real built-in directory role template IDs (a representative tier-0..tier-2 set).
ROLE_TEMPLATES = {
    'Global Administrator': '62e90394-69f5-4237-9190-012177145e10',
    'Privileged Role Administrator': 'e8611ab8-c189-46e8-94e1-60213ab1f814',
    'User Administrator': 'fe930be7-5e62-47db-91af-98c3a49a38b1',
    'Application Administrator': '9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3',
    'Groups Administrator': 'fdd7a751-b60b-444a-984c-02652fe8fa1c',
    'Helpdesk Administrator': '729827e3-9c14-49f7-bb1b-9608f156bbb8',
    'Global Reader': 'f2ef992c-3afb-46b9-b7cf-a126ee74c451',
}
# Microsoft Graph first-party SP, same appId every tenant.
GRAPH_APPID = '00000003-0000-0000-c000-000000000000'
ZERO_GUID = '00000000-0000-0000-0000-000000000000'
# Built-in Conditional Access authentication strengths (see policies plugin).
AUTHSTRENGTH_MFA = '00000000-0000-0000-0000-000000000002'
AUTHSTRENGTH_PHISHRESISTANT = '00000000-0000-0000-0000-000000000004'
# A custom strength ("Password + Microsoft Authenticator (push)"): resolved from its policyType-44 row.
AUTHSTRENGTH_CUSTOM = '5d3c6a1e-7b2f-4c8e-9a41-2f6b8d0c1e01'
# A second custom strength with no policyType-44 row (old dump): stays unresolved, counted as MFA approximately.
AUTHSTRENGTH_CUSTOM_UNRESOLVED = '7f1a2b3c-4d5e-6f70-8192-a3b4c5d6e7f8'

EPOCH = datetime.datetime(2020, 1, 1)


def _compress_cidr(cidrs):
    """Encode IP ranges the way AAD stores CompressedCidrIpRanges (raw deflate, base64)."""
    co = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    data = co.compress(','.join(cidrs).encode()) + co.flush()
    return base64.b64encode(data).decode()


class Gen:
    def __init__(self, nusers, seed, minimal):
        self.rng = random.Random(seed)
        self.nusers = nusers
        self.minimal = minimal
        # table (model class or Table) -> list[dict]
        self.rows = {}
        self.tenant_id = self.guid()
        self.domain = 'synthetic.onmicrosoft.com'
        self.vanity = 'synthetic.example.com'

    # -- helpers -----------------------------------------------------------
    def guid(self):
        return str(uuid.UUID(int=self.rng.getrandbits(128)))

    def dt(self, days_ago_max=1500):
        return EPOCH + datetime.timedelta(
            seconds=self.rng.randint(0, days_ago_max * 86400))

    def add(self, table, row):
        self.rows.setdefault(table, []).append(row)
        return row

    def link(self, table, **cols):
        self.rows.setdefault(table, []).append(cols)

    def pick(self, seq):
        return self.rng.choice(seq)

    def _sid(self, onprem=True):
        if onprem:
            return 'S-1-5-21-%d-%d-%d-%d' % (self.rng.randint(100000000, 999999999),
                                             self.rng.randint(100000000, 999999999),
                                             self.rng.randint(100000000, 999999999),
                                             self.rng.randint(1000, 99999))
        return 'S-1-12-1-%d-%d-%d-%d' % tuple(self.rng.randint(1, 4294967295) for _ in range(4))

    def chance(self, p):
        return self.rng.random() < p

    # -- directory objects -------------------------------------------------
    def gen_users(self):
        self.users = []        # (objectId, userType, enabled)
        self.enabled_users = []
        first = ['Alice', 'Bob', 'Carol', 'Dave', 'Eve', 'Frank', 'Grace', 'Heidi',
                 'Ivan', 'Judy', 'Mallory', 'Niaj', 'Olivia', 'Peggy', 'Rupert', 'Sybil',
                 'Trent', 'Victor', 'Walter', 'Yolanda']
        last = ['Smith', 'Jones', 'Nguyen', 'Khan', 'Garcia', 'Muller', 'Rossi', 'Kowalski',
                'Andersen', 'Dubois', 'Costa', 'Ivanov', 'Tanaka', 'Haddad', 'Novak']
        depts = ['IT', 'Finance', 'HR', 'Sales', 'Engineering', 'Legal', 'Marketing', None]
        titles = ['Analyst', 'Manager', 'Engineer', 'Director', 'Consultant', 'Intern', None]
        rows = []
        for i in range(self.nusers):
            oid = self.guid()
            # Mix: ~8% guests, ~10% synced, ~12% disabled, a few shared mailboxes.
            is_guest = self.chance(0.08)
            synced = self.chance(0.10)
            enabled = not self.chance(0.12)
            fn, ln = self.pick(first), self.pick(last)
            if is_guest:
                upn = (f'{fn.lower()}.{ln.lower()}_contoso.com#EXT#@{self.domain}')
                mail = f'{fn.lower()}.{ln.lower()}@contoso.com'
            else:
                upn = f'{fn.lower()}.{ln.lower()}{i}@{self.domain}'
                mail = upn
            # Shared / resource mailboxes via msExchRecipientTypeDetails.
            # cloudMSExchRecipientDisplayType: 0/7/18 are the mailbox-only types
            # the MFA view filters out (see server.get_mfa).
            shared = self.chance(0.03)
            row = {
                'objectType': 'User',
                'objectId': oid,
                'accountEnabled': enabled,
                'displayName': f'{fn} {ln}',
                'givenName': fn,
                'surname': ln,
                'userPrincipalName': upn,
                'mail': mail if self.chance(0.9) else None,
                'mailNickname': f'{fn.lower()}.{ln.lower()}{i}',
                'userType': 'Guest' if is_guest else 'Member',
                'dirSyncEnabled': True if synced else None,
                'department': self.pick(depts),
                'jobTitle': self.pick(titles),
                'mobile': f'+1555{self.rng.randint(1000000, 9999999)}' if self.chance(0.4) else None,
                'city': self.pick(['Amsterdam', 'Seattle', 'Paris', 'Tokyo', None]),
                'country': self.pick(['NL', 'US', 'FR', 'JP', None]),
                'usageLocation': self.pick(['NL', 'US', 'FR', 'JP']),
                'createdDateTime': self.dt(),
                'lastPasswordChangeDateTime': self.dt(),
                'onPremisesSecurityIdentifier': self._sid(True) if synced else None,
                'cloudSecurityIdentifier': self._sid(False),
                'strongAuthenticationDetail': self._mfa_detail(),
                'searchableDeviceKey': self._device_keys(),
            }
            if shared:
                # 0 = UserMailbox-ish shared, 7 = room/equipment. Use shared mailbox code 0.
                row['cloudMSExchRecipientDisplayType'] = 0
                row['msExchRecipientTypeDetails'] = 34359738368  # SharedMailbox
            self.add(db.User, row)
            self.users.append((oid, row['userType'], enabled))
            if enabled:
                self.enabled_users.append(oid)
            rows.append(oid)
        self.user_ids = rows
        # A couple of well-known accounts always present for assertions.
        self.ga_user = self.user_ids[0]

    def _mfa_detail(self):
        """strongAuthenticationDetail as stored by `gather --mfa` (AAD Graph shape)."""
        methods = []
        catalog = ['PhoneAppNotification', 'PhoneAppOTP', 'OneWaySms', 'TwoWayVoiceMobile']
        if self.chance(0.55):
            chosen = self.rng.sample(catalog, self.rng.randint(1, 3))
            default = self.pick(chosen)
            for m in chosen:
                # Real AAD Graph uses both `methodType` and the `default` flag; the
                # legacy GUI also reads `isDefault`, so we store both for compatibility.
                methods.append({'methodType': m, 'default': m == default, 'isDefault': m == default})
        requirements = []
        if self.chance(0.18):
            requirements.append({
                'relyingParty': '*',
                'state': self.pick(['enabled', 'enforced']),
                'rememberDevicesState': False,
            })
        return {'methods': methods, 'requirements': requirements, 'verificationDetail': None}

    def _device_keys(self):
        """searchableDeviceKey: FIDO2 keys and Windows Hello (NGC) registrations."""
        keys = []
        if self.chance(0.12):
            keys.append({
                'usage': 'FIDO',
                'keyType': 'FIDO',
                'keyIdentifier': base64.b64encode(os_urandom(self.rng, 32)).decode(),
                'keyMaterial': base64.b64encode(os_urandom(self.rng, 128)).decode(),
                'deviceId': self.guid(),
                'customKeyInformation': None,
                'fidoAaGuid': self.guid(),
            })
        if self.chance(0.20):
            keys.append({
                'usage': 'NGC',
                'keyType': 'NGC',
                'keyIdentifier': base64.b64encode(os_urandom(self.rng, 32)).decode(),
                'keyMaterial': base64.b64encode(os_urandom(self.rng, 270)).decode(),
                'deviceId': self.guid(),
            })
        return keys

    def gen_contacts(self):
        for i in range(5):
            self.add(db.Contact, {
                'objectType': 'Contact',
                'objectId': self.guid(),
                'displayName': f'External Contact {i}',
                'mail': f'contact{i}@partner.example',
                'dirSyncEnabled': True,
                'proxyAddresses': [f'SMTP:contact{i}@partner.example'],
            })

    def gen_groups(self):
        self.groups = []     # objectId
        self.role_assignable_group = None
        self.m365_group = None
        names = ['All Staff', 'IT Admins', 'Finance', 'Sales EMEA', 'Engineering',
                 'Project Falcon', 'Security Team', 'Contractors', 'Guests Welcome',
                 'VPN Users', 'Licensed E5', 'Help Desk', 'Dynamic Devices', 'Managers']
        for n in names:
            oid = self.guid()
            unified = self.chance(0.4)
            dynamic = self.chance(0.2)
            assignable = n == 'IT Admins'  # role-assignable group, members get the role
            row = {
                'objectType': 'Group',
                'objectId': oid,
                'displayName': n,
                'description': f'{n} group',
                'securityEnabled': True,
                'mailEnabled': unified,
                'mail': f'{n.lower().replace(" ", "")}@{self.domain}' if unified else None,
                'mailNickname': n.lower().replace(' ', ''),
                'groupTypes': (['Unified'] if unified else []) + (['DynamicMembership'] if dynamic else []),
                'isAssignableToRole': True if assignable else None,
                'isPublic': unified and self.chance(0.5),
                'visibility': 'Public' if unified and self.chance(0.5) else ('Private' if unified else None),
                'dirSyncEnabled': True if self.chance(0.2) else None,
                'createdDateTime': self.dt(),
                'onPremisesSecurityIdentifier': self._sid(True) if self.chance(0.2) else None,
                'cloudSecurityIdentifier': self._sid(False),
                'membershipRule': '(user.department -eq "IT")' if dynamic else None,
                'membershipRuleProcessingState': 'On' if dynamic else None,
            }
            self.add(db.Group, row)
            self.groups.append(oid)
            if assignable:
                self.role_assignable_group = oid
            if unified and self.m365_group is None:
                self.m365_group = oid

    def gen_group_memberships(self):
        # Scale user memberships with --users; keep the group set fixed.
        for oid, utype, enabled in self.users:
            for g in self.rng.sample(self.groups, self.rng.randint(0, 3)):
                self.link(db.lnk_group_member_user, Group=g, User=oid)
        # Nested groups: a cycle-free chain 4+ deep, plus a couple extra nests.
        chain = self.groups[:5]
        for parent, child in zip(chain, chain[1:]):
            self.link(db.lnk_group_member_group, Group=parent, childGroup=child)
        self.link(db.lnk_group_member_group, Group=self.groups[6], childGroup=self.groups[7])
        self.nested_chain_head = chain[0]

    def gen_devices(self):
        self.devices = []
        oss = [('Windows', '10.0.19045.3693'), ('Windows', '11.0.22631.2715'),
               ('iOS', '17.1'), ('Android', '14'), ('MacMDM', '14.1'), ('Linux', '')]
        trusts = ['AzureAd', 'ServerAd', 'Workplace']
        for i in range(20):
            oid = self.guid()
            ostype, osver = self.pick(oss)
            compliant = self.chance(0.6)
            row = {
                'objectType': 'Device',
                'objectId': oid,
                'accountEnabled': not self.chance(0.1),
                'displayName': f'DESKTOP-{self.rng.randint(1000, 9999)}' if ostype == 'Windows'
                               else f'{ostype}-{i}',
                'deviceId': self.guid(),
                'deviceManufacturer': self.pick(['Microsoft', 'Dell', 'Lenovo', 'Apple', 'HP']),
                'deviceModel': self.pick(['Surface', 'Latitude', 'ThinkPad', 'MacBook Pro', 'EliteBook']),
                'deviceOSType': ostype,
                'deviceOSVersion': osver,
                'deviceTrustType': self.pick(trusts),
                'deviceOwnership': self.pick(['Company', 'Personal']),
                'isCompliant': compliant,
                'isManaged': self.chance(0.7),
                'isRooted': self.chance(0.05),
                'approximateLastLogonTimestamp': self.dt(),
                'bitLockerKey': self._bitlocker() if ostype == 'Windows' and self.chance(0.6) else [],
            }
            self.add(db.Device, row)
            self.devices.append(oid)
            # Device owners (registered owners) -> users.
            if self.enabled_users and self.chance(0.8):
                self.link(db.lnk_device_owner, Device=oid, User=self.pick(self.enabled_users))

    def _bitlocker(self):
        out = []
        for _ in range(self.rng.randint(1, 2)):
            out.append({
                'keyIdentifier': self.guid().upper(),
                'keyMaterial': base64.b64encode(os_urandom(self.rng, 48)).decode(),
                'volumeType': self.pick([1, 2]),
                'deviceId': self.guid(),
                'creationTime': self.dt().isoformat() + 'Z',
            })
        return out

    def gen_sps_and_apps(self):
        self.sps = []           # objectId
        self.sp_by_appid = {}
        self.apps = []
        # Microsoft Graph first-party SP with real-looking app roles and scopes.
        graph_roles = [
            self._approle('User.Read.All', 'Read all users\' full profiles'),
            self._approle('Directory.Read.All', 'Read directory data'),
            self._approle('Mail.Read', 'Read mail in all mailboxes'),
            self._approle('RoleManagement.ReadWrite.Directory', 'Read and write all directory RBAC settings'),
            self._approle('Application.ReadWrite.All', 'Read and write all applications'),
        ]
        graph_scopes = [
            self._scope('User.Read', 'Sign in and read user profile', 'User'),
            self._scope('Mail.Read', 'Read user mail', 'User'),
            self._scope('Directory.AccessAsUser.All', 'Access directory as the signed in user', 'Admin'),
        ]
        self.graph_sp = self._add_sp('Microsoft Graph', GRAPH_APPID, microsoft=True,
                                     approles=graph_roles, scopes=graph_scopes,
                                     sptype='Application', publisher='Microsoft Services')
        self._add_sp('Office 365 Exchange Online', '00000002-0000-0ff1-ce00-000000000000',
                     microsoft=True, approles=[self._approle('full_access_as_app', 'Full mailbox access')],
                     publisher='Microsoft Services')
        # Managed identity.
        self._add_sp('vm-backup-identity', self.guid(), sptype='ManagedIdentity',
                     mi_resource='/subscriptions/%s/resourcegroups/rg-prod/providers/Microsoft.ManagedIdentity/userAssignedIdentities/vm-backup' % self.guid())
        # Third-party multi-tenant SPs.
        self.thirdparty_sps = []
        for n in ['Salesforce', 'Datadog', 'GitHub Enterprise', 'Zoom']:
            sp = self._add_sp(n, self.guid(), publisher=f'{n} Inc.',
                              approles=[self._approle(f'{n.split()[0]}.Access', f'{n} access')],
                              scopes=[self._scope('access_as_user', 'Access as user', 'User')],
                              owner_tenant=self.guid())
            self.thirdparty_sps.append(sp)
        # Applications (with their SP, the way gather links app<->SP via appId).
        for n in ['Fleet Portal', 'HR Sync Job', 'Deployment Runner', 'Crew Scheduler']:
            appid = self.guid()
            host = f'https://{n.lower().replace(" ", "")}.example'
            sp = self._add_sp(n, appid, publisher='Synthetic Corp',
                              urls={'homepage': host, 'logoutUrl': f'{host}/logout',
                                    'replyUrls': [f'{host}/auth', 'http://localhost:5000/auth']},
                              approles=[self._approle('Crew.Read', 'Read crew rosters', 'User'),
                                        self._approle('Crew.Admin', 'Manage crew rosters', 'User')],
                              scopes=[self._scope('access_as_user', 'Access as user', 'User')])
            app_oid = self.guid()
            self.add(db.Application, {
                'objectType': 'Application',
                'objectId': app_oid,
                'displayName': n,
                'appId': appid,
                'availableToOtherTenants': self.chance(0.3),
                'publicClient': self.chance(0.3),
                'oauth2AllowImplicitFlow': self.chance(0.2),
                'oauth2AllowIdTokenImplicitFlow': self.chance(0.2),
                'homepage': f'https://{n.lower().replace(" ", "")}.example',
                'replyUrls': [f'https://{n.lower().replace(" ", "")}.example/auth'],
                'identifierUris': [f'api://{appid}'],
                'appRoles': [self._approle('Crew.Read', 'Read crew rosters', 'User')],
                'oauth2Permissions': [self._scope('access_as_user', 'Access as user', 'User')],
                'keyCredentials': self._key_creds(),
                'passwordCredentials': self._pw_creds(),
                'requiredResourceAccess': [{
                    'resourceAppId': GRAPH_APPID,
                    'resourceAccess': [
                        {'id': graph_scopes[0]['id'], 'type': 'Scope'},
                        {'id': graph_roles[0]['id'], 'type': 'Role'},
                    ],
                }],
                'publisherDomain': self.domain,
                'appMetadata': {'version': 1, 'data': []},
            })
            self.apps.append(app_oid)
            # App owners: a user and (for one app) a service principal.
            if self.enabled_users:
                self.link(db.lnk_application_owner_user, Application=app_oid, User=self.pick(self.enabled_users))
            self.link(db.lnk_application_owner_serviceprincipal, Application=app_oid,
                      ServicePrincipal=self.pick(self.thirdparty_sps))
            # SP owners too.
            if self.enabled_users:
                self.link(db.lnk_serviceprincipal_owner_user, ServicePrincipal=sp,
                          User=self.pick(self.enabled_users))
        self.link(db.lnk_serviceprincipal_owner_serviceprincipal,
                  ServicePrincipal=self.thirdparty_sps[0],
                  childServicePrincipal=self.thirdparty_sps[1])

    def _approle(self, value, name, member='Application'):
        return {
            'id': self.guid(),
            'value': value,
            'displayName': name,
            'description': name,
            'allowedMemberTypes': [member],
            'isEnabled': True,
            'origin': 'Application',
        }

    def _scope(self, value, name, consent):
        return {
            'id': self.guid(),
            'value': value,
            'adminConsentDisplayName': name,
            'adminConsentDescription': name,
            'userConsentDisplayName': name,
            'userConsentDescription': name,
            'type': consent,  # 'User' or 'Admin'
            'isEnabled': True,
        }

    def _key_creds(self):
        if not self.chance(0.4):
            return []
        return [{
            'keyId': self.guid(),
            'usage': 'Verify',
            'type': 'AsymmetricX509Cert',
            'startDate': self.dt().isoformat() + 'Z',
            'endDate': (self.dt() + datetime.timedelta(days=365)).isoformat() + 'Z',
            'customKeyIdentifier': base64.b64encode(os_urandom(self.rng, 20)).decode(),
            'value': None,
        }]

    def _pw_creds(self):
        if not self.chance(0.5):
            return []
        return [{
            'keyId': self.guid(),
            'startDate': self.dt().isoformat() + 'Z',
            'endDate': (self.dt() + datetime.timedelta(days=180)).isoformat() + 'Z',
            'customKeyIdentifier': None,
            'value': None,
        }]

    def _add_sp(self, name, appid, microsoft=False, approles=None, scopes=None,
                sptype='Application', publisher=None, owner_tenant=None, mi_resource=None, urls=None):
        oid = self.guid()
        self.add(db.ServicePrincipal, {
            'objectType': 'ServicePrincipal',
            'objectId': oid,
            'accountEnabled': True,
            'displayName': name,
            'appDisplayName': name,
            'appId': appid,
            'servicePrincipalType': sptype,
            'microsoftFirstParty': microsoft,
            'publisherName': publisher,
            'appOwnerTenantId': owner_tenant or (self.tenant_id if not microsoft else 'f8cdef31-a31e-4b4a-93e4-5f571e91255a'),
            'appRoleAssignmentRequired': self.chance(0.3),
            'appRoles': approles or [],
            'oauth2Permissions': scopes or [],
            'keyCredentials': self._key_creds(),
            'passwordCredentials': self._pw_creds() if not microsoft else [],
            'servicePrincipalNames': [appid, f'https://{name.lower().replace(" ", "")}/{appid}'],
            'replyUrls': [],
            'tags': ['WindowsAzureActiveDirectoryIntegratedApp'] if sptype == 'Application' else [],
            'managedIdentityResourceId': mi_resource,
            'appMetadata': {'version': 1, 'data': []} if not microsoft else {},
            **(urls or {}),
        })
        self.sps.append(oid)
        self.sp_by_appid[appid] = oid
        return oid

    def gen_group_sp_owners(self):
        # Group owners: a user and a service principal.
        for g in self.groups[:6]:
            if self.enabled_users:
                self.link(db.lnk_group_owner_user, Group=g, User=self.pick(self.enabled_users))
        self.link(db.lnk_group_owner_serviceprincipal, Group=self.groups[0],
                  ServicePrincipal=self.pick(self.thirdparty_sps))
        # Group memberships for SPs and devices (coverage of those link tables).
        self.link(db.lnk_group_member_serviceprincipal, Group=self.groups[1],
                  ServicePrincipal=self.pick(self.thirdparty_sps))
        self.link(db.lnk_group_member_device, Group=self.groups[12], Device=self.pick(self.devices))
        # Contacts in a group.
        for c in self.rows.get(db.Contact, [])[:2]:
            self.link(db.lnk_group_member_contact, Group=self.groups[0], Contact=c['objectId'])

    def gen_approle_assignments(self):
        """AppRoleAssignments incl. the zero-GUID default access assignment."""
        # SP -> Graph app role (app permission granted).
        for sp in self.thirdparty_sps[:3]:
            role = self.pick(self.rows[db.ServicePrincipal][0]['appRoles'])  # graph roles
            self.add(db.AppRoleAssignment, {
                'objectType': 'AppRoleAssignment',
                'objectId': self.guid(),
                'id': role['id'],
                'principalId': sp,
                'principalType': 'ServicePrincipal',
                'principalDisplayName': 'third-party app',
                'resourceId': self.graph_sp,
                'resourceDisplayName': 'Microsoft Graph',
                'creationTimestamp': self.dt(),
            })
        # User assigned to an app role on a line-of-business SP.
        if self.enabled_users:
            target = self.pick(self.thirdparty_sps)
            roles = [r for r in self.rows[db.ServicePrincipal]
                     if r['objectId'] == target][0]['appRoles']
            self.add(db.AppRoleAssignment, {
                'objectType': 'AppRoleAssignment',
                'objectId': self.guid(),
                'id': roles[0]['id'] if roles else ZERO_GUID,
                'principalId': self.pick(self.enabled_users),
                'principalType': 'User',
                'principalDisplayName': 'a user',
                'resourceId': target,
                'resourceDisplayName': 'third-party app',
                'creationTimestamp': self.dt(),
            })
            # Default access (zero GUID) assignment for a group.
            self.add(db.AppRoleAssignment, {
                'objectType': 'AppRoleAssignment',
                'objectId': self.guid(),
                'id': ZERO_GUID,
                'principalId': self.m365_group or self.groups[0],
                'principalType': 'Group',
                'principalDisplayName': 'a group',
                'resourceId': self.pick(self.thirdparty_sps),
                'resourceDisplayName': 'third-party app',
                'creationTimestamp': self.dt(),
            })

    def gen_oauth2_grants(self):
        expiry = (EPOCH + datetime.timedelta(days=3650))
        # AllPrincipals (admin consent, tenant-wide).
        self.add(db.OAuth2PermissionGrant, {
            'objectId': self.guid(),
            'clientId': self.pick(self.thirdparty_sps),
            'consentType': 'AllPrincipals',
            'principalId': None,
            'resourceId': self.graph_sp,
            'scope': 'User.Read Mail.Read offline_access',
            'startTime': EPOCH,
            'expiryTime': expiry,
        })
        # Principal (per-user consent).
        if self.enabled_users:
            self.add(db.OAuth2PermissionGrant, {
                'objectId': self.guid(),
                'clientId': self.pick(self.thirdparty_sps),
                'consentType': 'Principal',
                'principalId': self.pick(self.enabled_users),
                'resourceId': self.graph_sp,
                'scope': 'User.Read openid profile',
                'startTime': EPOCH,
                'expiryTime': expiry,
            })

    def gen_roles(self):
        """DirectoryRoles (activated) + unified RoleDefinitions + Role(Eligible)Assignments."""
        self.dir_roles = {}
        for name, template in ROLE_TEMPLATES.items():
            oid = self.guid()
            self.add(db.DirectoryRole, {
                'objectType': 'DirectoryRole',
                'objectId': oid,
                'displayName': name,
                'description': f'{name} built-in role',
                'roleTemplateId': template,
                'isSystem': True,
                'roleDisabled': False,
                'cloudSecurityIdentifier': self._sid(False),
            })
            self.dir_roles[name] = oid
            # Unified role definition (id == templateId for built-ins).
            self.add(db.RoleDefinition, {
                'objectType': 'RoleDefinition',
                'objectId': template,
                'displayName': name,
                'description': f'{name} built-in role',
                'isBuiltIn': True,
                'isEnabled': True,
                'templateId': template,
                'version': '1',
                'resourceScopes': ['/'],
                'rolePermissions': [{
                    'allowedResourceActions': ['microsoft.directory/users/basic/read'],
                    'condition': None,
                }],
            })
        # Members of Global Administrator: a user and a service principal.
        ga = self.dir_roles['Global Administrator']
        self.link(db.lnk_role_member_user, DirectoryRole=ga, User=self.ga_user)
        self.link(db.lnk_role_member_serviceprincipal, DirectoryRole=ga,
                  ServicePrincipal=self.pick(self.thirdparty_sps))
        # A role-assignable group as a role member.
        self.link(db.lnk_role_member_group,
                  DirectoryRole=self.dir_roles['User Administrator'],
                  Group=self.role_assignable_group)
        # A couple more direct user role members.
        for name in ['Helpdesk Administrator', 'Global Reader']:
            if self.enabled_users:
                self.link(db.lnk_role_member_user, DirectoryRole=self.dir_roles[name],
                          User=self.pick(self.enabled_users))

        # RoleAssignments (active) and EligibleRoleAssignments with directory / AU / app scopes.
        au_scope = '/administrativeUnits/%s'
        app_scope = '/%s'
        self.pending_au_scope = au_scope  # filled after AUs exist
        # directory scope, user
        self.add(db.RoleAssignment, {
            'id': self.guid(),
            'principalId': self.ga_user,
            'roleDefinitionId': ROLE_TEMPLATES['Global Administrator'],
            'resourceScopes': ['/'],
        })
        # app-scoped (Application Administrator over one application object)
        self.add(db.RoleAssignment, {
            'id': self.guid(),
            'principalId': self.pick(self.enabled_users) if self.enabled_users else self.ga_user,
            'roleDefinitionId': ROLE_TEMPLATES['Application Administrator'],
            'resourceScopes': [app_scope % self.apps[0]],
        })
        # role-assignable group with a directory-scoped active assignment
        self.add(db.RoleAssignment, {
            'id': self.guid(),
            'principalId': self.role_assignable_group,
            'roleDefinitionId': ROLE_TEMPLATES['Groups Administrator'],
            'resourceScopes': ['/'],
        })
        # eligible assignments (one directory, one AU — AU id set in gen_aus)
        self.add(db.EligibleRoleAssignment, {
            'id': self.guid(),
            'principalId': self.pick(self.enabled_users) if self.enabled_users else self.ga_user,
            'roleDefinitionId': ROLE_TEMPLATES['Privileged Role Administrator'],
            'resourceScopes': ['/'],
        })

    def gen_aus(self):
        self.aus = []
        for n in ['EMEA Region', 'Executives', 'Lab Devices']:
            oid = self.guid()
            dynamic = n == 'Lab Devices'
            self.add(db.AdministrativeUnit, {
                'objectType': 'AdministrativeUnit',
                'objectId': oid,
                'displayName': n,
                'description': f'{n} administrative unit',
                'membershipType': 'Dynamic' if dynamic else 'Assigned',
                'membershipRule': '(device.displayName -startsWith "LAB")' if dynamic else None,
                'membershipRuleProcessingState': 'On' if dynamic else None,
                'isMemberManagementRestricted': n == 'Executives',
                'visibility': 'HiddenMembership' if n == 'Executives' else None,
            })
            self.aus.append(oid)
            # Members: users, a group, a device.
            for u in self.rng.sample(self.enabled_users, min(3, len(self.enabled_users))):
                self.link(db.lnk_au_member_user, AdministrativeUnit=oid, User=u)
            self.link(db.lnk_au_member_group, AdministrativeUnit=oid, Group=self.pick(self.groups))
            self.link(db.lnk_au_member_device, AdministrativeUnit=oid, Device=self.pick(self.devices))
        # AU-scoped eligible role assignment (User Administrator over EMEA Region AU).
        self.add(db.EligibleRoleAssignment, {
            'id': self.guid(),
            'principalId': self.pick(self.enabled_users) if self.enabled_users else self.ga_user,
            'roleDefinitionId': ROLE_TEMPLATES['User Administrator'],
            'resourceScopes': ['/administrativeUnits/%s' % self.aus[0]],
        })

    def gen_tenant_and_settings(self):
        self.add(db.TenantDetail, {
            'objectType': 'Company',
            'objectId': self.tenant_id,
            'displayName': 'Synthetic Corporation',
            'city': 'Amsterdam',
            'country': 'Netherlands',
            'countryLetterCode': 'NL',
            'preferredLanguage': 'en',
            'tenantType': 'AAD',
            'createdDateTime': EPOCH,
            'verifiedDomains': [
                {'name': self.domain, 'capabilities': 'Email, OfficeCommunicationsOnline',
                 'default': False, 'initial': True, 'type': 'Managed', 'id': 'onmicrosoft'},
                {'name': self.vanity, 'capabilities': 'Email, OfficeCommunicationsOnline',
                 'default': True, 'initial': False, 'type': 'Managed', 'id': 'vanity'},
            ],
            'assignedPlans': [],
            'provisionedPlans': [],
        })
        self.add(db.AuthorizationPolicy, {
            'id': 'authorizationPolicy',
            'displayName': 'Authorization Policy',
            'description': 'Used to manage authorization related settings across the company.',
            'allowInvitesFrom': 'adminsAndGuestInviters',
            'allowedToSignUpEmailBasedSubscriptions': True,
            'allowedToUseSSPR': True,
            'allowEmailVerifiedUsersToJoinOrganization': False,
            'blockMsolPowerShell': False,
            'guestUserRoleId': '10dae51f-b6af-4016-8d66-8c2a99b929b3',  # Restricted guest
            'defaultUserRolePermissions': {
                'allowedToCreateApps': True,
                'allowedToCreateSecurityGroups': True,
                'allowedToReadOtherUsers': True,
                'allowedToCreateTenants': True,
                'allowedToReadBitlockerKeysForOwnedDevice': False,
                'permissionGrantPoliciesAssigned': ['ManagePermissionGrantsForSelf.microsoft-user-default-legacy'],
            },
            'permissionGrantPolicyIdsAssignedToDefaultUserRole':
                ['microsoft-user-default-legacy'],
            'enabledPreviewFeatures': [],
        })
        self.add(db.DirectorySetting, {
            'id': self.guid(),
            'displayName': 'Group.Unified',
            'templateId': '62375ab9-6b52-47ed-826b-58e47e0e304b',
            'values': [
                {'name': 'EnableGroupCreation', 'value': 'true'},
                {'name': 'AllowGuestsToAccessGroups', 'value': 'true'},
                {'name': 'AllowToAddGuests', 'value': 'true'},
                {'name': 'GroupCreationAllowedGroupId', 'value': self.groups[0]},
            ],
        })

    # -- Conditional Access -----------------------------------------------
    def gen_named_locations(self):
        self.named_locations = []  # (policyIdentifier, displayName)
        # Trusted corporate IP location.
        lid = self.guid()
        self.add(db.Policy, {
            'objectType': 'Policy',
            'objectId': self.guid(),
            'displayName': 'Corporate network',
            'policyType': 6,
            'policyIdentifier': lid,
            'tenantDefaultPolicy': 0,
            'policyDetail': [json.dumps({
                'Categories': ['trusted'],
                'CidrIpRanges': ['203.0.113.0/24', '198.51.100.0/24'],
                'CompressedCidrIpRanges': _compress_cidr(['203.0.113.0/24', '198.51.100.0/24']),
                'ApplyToUnknownCountry': None,
            })],
        })
        self.named_locations.append((lid, 'Corporate network'))
        self.trusted_location = lid
        # Country-based location.
        lid2 = self.guid()
        self.add(db.Policy, {
            'objectType': 'Policy',
            'objectId': self.guid(),
            'displayName': 'Blocked countries',
            'policyType': 6,
            'policyIdentifier': lid2,
            'tenantDefaultPolicy': 0,
            'policyDetail': [json.dumps({
                'Categories': [],
                'CountryIsoCodes': ['KP', 'IR', 'RU'],
                'ApplyToUnknownCountry': True,
            })],
        })
        self.named_locations.append((lid2, 'Blocked countries'))
        # Trusted country location (legacy portal; Graph's countryNamedLocation has no isTrusted).
        lid3 = self.guid()
        self.add(db.Policy, {
            'objectType': 'Policy',
            'objectId': self.guid(),
            'displayName': 'Nordic countries',
            'policyType': 6,
            'policyIdentifier': lid3,
            'tenantDefaultPolicy': 0,
            'policyDetail': [json.dumps({
                'Categories': ['trusted'],
                'CountryIsoCodes': ['NO', 'SE', 'DK', 'FI', 'IS'],
                'ApplyToUnknownCountry': False,
            })],
        })
        self.named_locations.append((lid3, 'Nordic countries'))

    def gen_auth_strengths(self):
        """Custom Conditional Access authentication strengths, as AAD Graph stores them: policyType-44 Policy rows.

        The tenant default "container" (tenantDefaultPolicy set, no allowedCombinations) is ignored by the backend;
        a custom strength has tenantDefaultPolicy null and its objectId is what CA policies put in AuthStrengthIds.
        Omitted from --minimal dumps to exercise the unresolved fallback.
        """
        self.add(db.Policy, {
            'objectType': 'Policy',
            'objectId': self.guid(),
            'displayName': 'Default Policy',
            'policyType': 44,
            'policyIdentifier': None,
            'tenantDefaultPolicy': 44,
            'policyDetail': [json.dumps({'LastUpdatedTimestamp': self.dt().isoformat() + 'Z'})],
        })
        self.add(db.Policy, {
            'objectType': 'Policy',
            'objectId': AUTHSTRENGTH_CUSTOM,
            'displayName': 'Password + Microsoft Authenticator (push)',
            'policyType': 44,
            'policyIdentifier': None,
            'tenantDefaultPolicy': None,
            'policyDetail': [json.dumps({
                'created': self.dt().isoformat() + 'Z',
                'modified': self.dt().isoformat() + 'Z',
                'description': '',
                'allowedCombinations': ['Password, MicrosoftAuthenticatorPush'],
                'requirementsSatisfied': 'Mfa',
                'metadata': {'version': '1.0'},
                'combinationConfigurations': [],
            })],
        })

    def gen_ca_policies(self):
        g = self.groups
        roles = list(ROLE_TEMPLATES.values())
        deleted_id = self.guid()  # references nothing -> unresolved reference

        def policy(name, state, conditions, controls=None, session=None, extra=None):
            detail = {'State': state, 'Conditions': conditions}
            if controls is not None:
                detail['Controls'] = controls
            if session:
                detail['SessionControls'] = session
            if extra:
                detail.update(extra)
            self.add(db.Policy, {
                'objectType': 'Policy',
                'objectId': self.guid(),
                'displayName': name,
                'policyType': 18,
                'policyIdentifier': None,
                'tenantDefaultPolicy': None,
                'policyDetail': [json.dumps(detail)],
            })

        # 1. Enabled: require MFA for all users, all apps, exclude break-glass user + a group.
        policy('Require MFA for all users', 'Enabled', {
            'Users': {
                'Include': [{'All': ['All']}],
                'Exclude': [{'Users': [self.ga_user]}, {'Groups': [g[1]]}],
            },
            'Applications': {'Include': [{'Applications': ['All']}]},
        }, controls=[{'Control': ['Mfa']}])

        # 2. Report-only: block legacy auth for Office365, specific clients + platforms.
        policy('Block legacy authentication (report only)', 'Reporting', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': [{'Roles': [roles[0]]}]},
            'Applications': {'Include': [{'Applications': ['Office365']}]},
            'ClientTypes': {'Include': [{'ClientTypes': ['Native', 'OtherLegacy', 'LegacyExchange']}]},
            'DevicePlatforms': {'Include': [{'DevicePlatforms': ['All']}],
                                'Exclude': [{'DevicePlatforms': ['iOS', 'Android']}]},
        }, controls=[{'Control': ['Block']}])

        # 3. Disabled: phishing-resistant MFA for admins (roles) at untrusted locations.
        policy('Admins need phishing-resistant MFA', 'Disabled', {
            'Users': {'Include': [{'Roles': roles[:3]}]},
            'Applications': {'Include': [{'Applications': ['All']}]},
            'Locations': {'Include': [{'Locations': ['All']}],
                          'Exclude': [{'Locations': [self.trusted_location]}]},
        }, controls=[{'AuthStrengthIds': [AUTHSTRENGTH_PHISHRESISTANT]}])

        # 4. Enabled: guests/external users, sign-in risk, grant with MFA + compliant device,
        #    session controls. Includes a specific group and a specific named location.
        policy('Risky guest sign-ins', 'Enabled', {
            'Users': {
                'Include': [
                    {'Groups': [self.m365_group or g[0]]},
                    {'GuestsOrExternalUsers': {
                        'GuestOrExternalUserTypes': 'internalGuest,b2bCollaborationGuest',
                        'ExternalTenants': {'MembershipKind': 'all'}}},
                ],
                'Exclude': [{'Users': [deleted_id]}],  # unresolved reference
            },
            'Applications': {'Include': [{'Applications': ['All']}],
                             'Exclude': [{'Applications': [GRAPH_APPID]}]},
            'SignInRisks': {'Include': [{'SignInRisks': ['high', 'medium']}]},
            'UserRisks': {'Include': [{'UserRisks': ['high']}]},
            'Locations': {'Include': [{'Locations': [self.named_locations[1][0]]}]},
        }, controls=[{'Control': ['Mfa', 'CompliantDevice']}],
            session=['SignInFrequency', 'PersistentBrowserSessionMode'],
            extra={'SignInFrequencyType': 10, 'SignInFrequencyTimeSpan': '4:00:00',
                   'PersistentBrowserSessionMode': 'Never'})

        # 5. Enabled: user-action (register security info) with a (resolved) custom auth strength + auth context.
        policy('Protect security info registration', 'Enabled', {
            'Users': {'Include': [{'Users': self.enabled_users[:2] or [self.ga_user]}]},
            'Applications': {'Include': [{'Acrs': ['c1']}]},
            'AuthFlows': {'Include': [{'AuthFlowType': ['deviceCodeFlow', 'authenticationTransfer']}]},
        }, controls=[{'AuthStrengthIds': [AUTHSTRENGTH_CUSTOM]}])

        # 5b. Enabled: a custom strength with no type-44 row (old dump) -> unresolved, MFA approximate.
        #     Scoped to specific users/app so it does not disturb the targetsAll* / grant filter assertions.
        policy('Legacy custom-strength MFA', 'Enabled', {
            'Users': {'Include': [{'Users': self.enabled_users[:2] or [self.ga_user]}]},
            'Applications': {'Include': [{'Applications': [GRAPH_APPID]}]},
        }, controls=[{'AuthStrengthIds': [AUTHSTRENGTH_CUSTOM_UNRESOLVED]}])

        # 6. Enabled: device-filter rule, service-principal policy (workload identities).
        policy('Workload identity sign-in restriction', 'Enabled', {
            'Users': {'Include': [{'None': ['None']}]},
            'ServicePrincipals': {'Include': [{'ServicePrincipals': self.thirdparty_sps[:2]}],
                                  'Exclude': [{'ServicePrincipals': [self.thirdparty_sps[2]]}]},
            'Applications': {'Include': [{'Applications': ['All']}]},
            'Devices': {'Include': [{'DeviceRule': 'device.trustType -eq "AzureAD" -and device.isCompliant -eq True'}]},
        }, controls=[{'Control': ['Block']}])

        # 7. Enabled: policy referencing only the deleted object id (resolves to nothing).
        policy('Stale policy (deleted principals)', 'Enabled', {
            'Users': {'Include': [{'Users': [deleted_id]}, {'Groups': [deleted_id]}]},
            'Applications': {'Include': [{'Applications': ['All']}]},
        }, controls=[{'Control': ['Mfa']}])

    # -- PIM / IG / AZ -----------------------------------------------------
    def gen_pim(self):
        self.add(db.PIMprivilegedAccess, {'id': 'aadroles', 'displayName': 'aadroles'})
        self.add(db.PIMprivilegedAccess, {'id': 'aadgroups', 'displayName': 'aadgroups'})
        self.add(db.PIMprivilegedAccess, {'id': 'azureResources', 'displayName': 'azureResources'})

        # aadroles: the directory resource.
        dir_res = self.guid()
        self.add(db.PIMgovernanceResource, {
            'id': dir_res, 'externalId': self.tenant_id, 'type': 'Directory',
            'displayName': 'Synthetic Corporation', 'status': 'Active',
            'onboardDateTime': self.dt(), 'registeredDateTime': self.dt(),
            'managedAt': None, 'registeredRoot': None, 'originTenantId': self.tenant_id,
        })
        self.link(db.lnk_pim_resource, PIMprivilegedAccess='aadroles', PIMgovernanceResource=dir_res)

        # aadgroups: onboarded groups (role-assignable + M365).
        for grp in [self.role_assignable_group, self.m365_group or self.groups[0]]:
            res = self.guid()
            self.add(db.PIMgovernanceResource, {
                'id': res, 'externalId': grp, 'type': 'Security',
                'displayName': 'PIM group', 'status': 'Active',
                'onboardDateTime': self.dt(), 'registeredDateTime': self.dt(),
                'originTenantId': self.tenant_id,
            })
            self.link(db.lnk_pim_resource, PIMprivilegedAccess='aadgroups', PIMgovernanceResource=res)
            self.link(db.lnk_pim_resource_aadgroup, PIMgovernanceResource=res, Group=grp)

        # Role definitions + settings (with approval) + assignments on the directory resource.
        for name, template in list(ROLE_TEMPLATES.items())[:4]:
            rdef = self.guid()
            self.add(db.PIMgovernanceRoleDefinition, {
                'id': rdef, 'resourceId': dir_res, 'externalId': template,
                'templateId': template, 'displayName': name, 'type': 'BuiltInRole',
            })
            approval = name in ('Global Administrator', 'Privileged Role Administrator')
            self.add(db.PIMgovernanceRoleSettingV2, {
                'id': self.guid(), 'resourceId': dir_res, 'roleDefinitionId': rdef,
                'isDefault': True, 'lastUpdatedDateTime': self.dt(), 'lastUpdatedBy': None,
                'lifeCycleManagement': [{
                    'caller': 'EndUser', 'level': 'Member', 'operation': 'All',
                    'value': [{
                        'ruleIdentifier': 'ApprovalRule',
                        'setting': json.dumps({
                            'enabled': approval,
                            'approvalMode': 'SingleStage',
                            'approvalStages': [{
                                'approvalStageTimeOutInDays': 1,
                                'isApproverJustificationRequired': True,
                                'escalationTimeInMinutes': 0,
                                'primaryApprovers': [{
                                    '@odata.type': '#microsoft.activeDirectory.singleUser',
                                    'id': self.ga_user, 'isBackup': False}],
                            }],
                        }),
                    }, {
                        'ruleIdentifier': 'ExpirationRule',
                        'setting': json.dumps({'maximumGrantPeriodInMinutes': 480}),
                    }],
                }],
            })
            # Eligible assignment for a user; active assignment for a group.
            self.add(db.PIMgovernanceRoleAssignment, {
                'id': self.guid(), 'resourceId': dir_res, 'roleDefinitionId': rdef,
                'subjectId': self.pick(self.enabled_users) if self.enabled_users else self.ga_user,
                'assignmentState': 'Eligible', 'memberType': 'Direct', 'status': 'Provisioned',
                'isPermanent': False, 'startDateTime': self.dt(),
                'endDateTime': self.dt() + datetime.timedelta(days=180),
            })
            agid = self.guid()
            self.add(db.PIMgovernanceRoleAssignment, {
                'id': agid, 'resourceId': dir_res, 'roleDefinitionId': rdef,
                'subjectId': self.role_assignable_group,
                'assignmentState': 'Active', 'memberType': 'Direct', 'status': 'Provisioned',
                'isPermanent': True, 'startDateTime': self.dt(),
            })
            # Subject links (what the GUI reads for principal resolution).
            last = self.rows[db.PIMgovernanceRoleAssignment][-2]
            self.link(db.lnk_pim_roleassignment_subjectuser,
                      PIMgovernanceRoleAssignment=last['id'], User=last['subjectId'])
            self.link(db.lnk_pim_roleassignment_subjectgroup,
                      PIMgovernanceRoleAssignment=agid, Group=self.role_assignable_group)

    def gen_ig(self):
        cat = self.guid()
        self.add(db.IGaccessPackageCatalog, {
            'id': cat, 'displayName': 'IT Resources', 'uniqueName': 'it-resources',
            'description': 'Self-service IT access', 'catalogType': 'UserManaged',
            'catalogStatus': 'Published', 'state': 'published', 'isExternallyVisible': False,
            'createdDateTime': self.dt(),
        })
        # A resource + role + scope, joined into a resource-role-scope.
        res = self.guid()
        self.add(db.IGaccessPackageResource, {
            'id': res, 'displayName': self.m365_group and 'Fleet Management' or 'Group',
            'description': 'An onboarded group', 'resourceType': 'Security Group',
            'originId': self.m365_group or self.groups[0], 'originSystem': 'AadGroup',
            'addedOn': self.dt(),
        })
        self.link(db.lnk_ig_cg_resource, IGaccessPackageCatalog=cat, IGaccessPackageResource=res)
        role = self.guid()
        self.add(db.IGaccessPackageResourceRole, {
            'id': role, 'displayName': 'Member', 'roleType': None,
            'originId': 'Member_%s' % (self.m365_group or self.groups[0]), 'originSystem': 'AadGroup',
        })
        self.link(db.lnk_ig_ap_rr, IGaccessPackageResource=res, IGaccessPackageResourceRole=role)
        scope = self.guid()
        self.add(db.IGaccessPackageResourceScope, {
            'id': scope, 'displayName': 'Root', 'originId': self.m365_group or self.groups[0],
            'originSystem': 'AadGroup', 'isRootScope': True,
        })
        pkg = self.guid()
        self.add(db.IGaccessPackage, {
            'id': pkg, 'catalogId': cat, 'displayName': 'Fleet access package',
            'uniqueName': 'fleet-access', 'description': 'Access to fleet resources',
            'isHidden': False, 'createdDateTime': self.dt(),
        })
        self.link(db.lnk_ig_ap, IGaccessPackageCatalog=cat, IGaccessPackage=pkg)
        rrs = self.guid()
        self.add(db.IGaccessPackageResourceRoleScope, {
            'id': rrs, 'createdDateTime': self.dt(),
        })
        self.link(db.lnk_ig_ap_rrs_role, IGaccessPackageResourceRoleScope=rrs, IGaccessPackageResourceRole=role)
        self.link(db.lnk_ig_ap_rrs_scope, IGaccessPackageResourceRoleScope=rrs, IGaccessPackageResourceScope=scope)
        self.link(db.lnk_ig_ap_rr_scope, IGaccessPackage=pkg, IGaccessPackageResourceRoleScope=rrs)
        # Assignment policy with scope users/groups and approval settings.
        pol = self.guid()
        self.add(db.IGaccessPackageAssignmentPolicy, {
            'id': pol, 'displayName': 'Standard requests', 'description': 'Anyone in the directory',
            'allowedTargetScope': 'specificDirectoryUsers',
            'specificAllowedTargets': [
                {'@odata.type': '#microsoft.graph.singleUser', 'objectId': u}
                for u in (self.enabled_users[:2] or [self.ga_user])
            ] + [{'@odata.type': '#microsoft.graph.groupMembers', 'objectId': self.groups[0]}],
            'accessPackageId': pkg, 'durationInDays': 180, 'canExtend': True,
            'createdDateTime': self.dt(),
            'requestApprovalSettings': {
                'isApprovalRequiredForAdd': True,
                'isApprovalRequiredForUpdate': False,
                'isRequestorJustificationRequired': True,
                'approvalMode': 'SingleStage',
                'approvalStages': [{
                    'approvalStageTimeOutInDays': 14,
                    'isApproverJustificationRequired': True,
                    'isEscalationEnabled': False,
                    'primaryApprovers': [{
                        '@odata.type': '#Microsoft.IGAELM.EC.FrontEnd.ExternalModel.singleUser',
                        'displayName': 'Approver', 'isBackup': False, 'id': self.ga_user}],
                    'fallbackPrimaryApprovers': [],
                    'escalationApprovers': [],
                    'fallbackEscalationApprovers': [],
                }],
            },
            'expiration': {'type': 'afterDuration', 'duration': 'P180D', 'endDateTime': None},
        })
        # Scope links (iggather phase 2).
        for u in (self.enabled_users[:2] or [self.ga_user]):
            self.link(db.lnk_ig_ap_assignment_policy_inscope_user,
                      IGaccessPackageAssignmentPolicy=pol, User=u)
        self.link(db.lnk_ig_ap_assignment_policy_inscope_group,
                  IGaccessPackageAssignmentPolicy=pol, Group=self.groups[0])
        # Subjects + an assignment.
        subj = self.guid()
        tgt_user = self.enabled_users[0] if self.enabled_users else self.ga_user
        self.add(db.IGaccessPackageSubject, {
            'id': subj, 'objectId': tgt_user, 'displayName': 'Assigned user',
            'principalName': 'user@%s' % self.domain, 'type': 'user',
            'subjectType': 'User', 'createdDateTime': self.dt(),
        })
        asg = self.guid()
        self.add(db.IGaccessPackageAssignment, {
            'id': asg, 'catalogId': cat, 'accessPackageId': pkg, 'assignmentPolicyId': pol,
            'targetId': subj, 'assignmentState': 'Delivered', 'state': 'Delivered',
            'status': 'Delivered', 'createdDateTime': self.dt(),
        })
        self.link(db.lnk_ig_ap_assignment_target, IGaccessPackageAssignment=asg, IGaccessPackageSubject=subj)

    def gen_az(self):
        sub_id = self.guid()
        sub = '/subscriptions/%s' % sub_id
        mg = '/providers/Microsoft.Management/managementGroups/%s' % 'mg-root'
        rg = '%s/resourceGroups/rg-prod' % sub
        resource = '%s/providers/Microsoft.Storage/storageAccounts/prodstorage' % rg

        self.add(db.AZmanagementGroup, {
            'id': mg, 'name': 'mg-root', 'type': 'Microsoft.Management/managementGroups',
            'display_name': 'Root Management Group', 'tenant_id': self.tenant_id,
            'details': {'parent': None},
        })
        self.add(db.AZsubscription, {
            'id': sub, 'subscription_id': sub_id, 'display_name': 'Production',
            'state': 'Enabled', 'authorization_source': 'RoleBased',
            'subscription_policies': {'quotaId': 'PayAsYouGo_2014-09-01'},
        })
        self.add(db.AZresource, {
            'id': resource, 'name': 'prodstorage', 'type': 'microsoft.storage/storageaccounts',
            'type_display_name': 'Storage account', 'resource_group': 'rg-prod',
            'location': 'westeurope', 'subscription_id': sub, 'tags': {'env': 'prod'},
        })
        # Role definitions (Owner/Contributor/Reader + custom).
        defs = {}
        for name, actions in [
            ('Owner', ['*']), ('Contributor', ['*']), ('Reader', ['*/read']),
            ('Custom Storage Operator', ['Microsoft.Storage/storageAccounts/*'])]:
            rid = '/providers/Microsoft.Authorization/roleDefinitions/%s' % self.guid()
            self.add(db.AZroleDefinition, {
                'id': rid, 'name': rid.split('/')[-1],
                'type': 'Microsoft.Authorization/roleDefinitions',
                'role_name': name, 'description': f'{name} role',
                'role_type': 'BuiltInRole' if name != 'Custom Storage Operator' else 'CustomRole',
                'created_on': self.dt(),
                'permissions': [{'actions': actions, 'notActions': [], 'dataActions': [], 'notDataActions': []}],
            })
            defs[name] = rid

        # Active assignments at every scope, for user / group / SP (one with a condition).
        plan = [
            ('Owner', mg, self.pick(self.enabled_users) if self.enabled_users else self.ga_user, 'User'),
            ('Contributor', sub, self.pick(self.groups), 'Group'),
            ('Reader', rg, self.pick(self.sps), 'ServicePrincipal'),
            ('Custom Storage Operator', resource,
             self.pick(self.enabled_users) if self.enabled_users else self.ga_user, 'User'),
        ]
        for i, (rname, scope, pid, ptype) in enumerate(plan):
            aid = '%s/providers/Microsoft.Authorization/roleAssignments/%s' % (scope, self.guid())
            cond = ("((!(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'})) "
                    "OR (@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringEquals 'public'))"
                    if i == 3 else None)
            self.add(db.AZroleAssignment, {
                'id': aid, 'name': aid.split('/')[-1],
                'type': 'Microsoft.Authorization/roleAssignments', 'scope': scope,
                'role_definition_id': defs[rname], 'principal_id': pid, 'principal_type': ptype,
                'condition': cond, 'condition_version': '2.0' if cond else None,
                'created_on': self.dt(),
            })
            tbl = {'User': db.lnk_az_roleassignment_user, 'Group': db.lnk_az_roleassignment_group,
                   'ServicePrincipal': db.lnk_az_roleassignment_serviceprincipal}[ptype]
            self.link(tbl, AZroleAssignment=aid, **{ptype: pid})

        # One eligible (PIM for Azure) assignment at subscription scope for a group.
        eid = '%s/providers/Microsoft.Authorization/roleEligibilityScheduleInstances/%s' % (sub, self.guid())
        self.add(db.AZroleEligibilityScheduleInstance, {
            'id': eid, 'name': eid.split('/')[-1],
            'type': 'Microsoft.Authorization/roleEligibilityScheduleInstances',
            'role_definition_id': defs['Owner'], 'principal_id': self.pick(self.groups),
            'principal_type': 'Group', 'scope': sub, 'status': 'Provisioned',
            'member_type': 'Direct', 'start_date_time': self.dt(),
            'end_date_time': self.dt() + datetime.timedelta(days=365),
            'created_on': self.dt(),
            'expanded_properties': {'scope': {'id': sub, 'displayName': 'Production', 'type': 'subscription'}},
        })
        self.link(db.lnk_az_roleassignment_eligible_group,
                  AZroleEligibilityScheduleInstance=eid, Group=self.rows[db.AZroleEligibilityScheduleInstance][-1]['principal_id'])

    # -- Intune device compliance -----------------------
    def gen_compliance(self):
        # secureByDefault False: devices without a compliance policy count as compliant (the risky case).
        settings = {'deviceComplianceCheckinThresholdDays': 30, 'isScheduledActionEnabled': True,
                    'secureByDefault': False, 'enhancedJailBreak': False, 'deviceInactivityBeforeRetirementInDay': 0,
                    'derivedCredentialProvider': 'notConfigured', 'derivedCredentialUrl': None}
        self.add(db.DeviceManagementSetting, {
            'id': self.tenant_id, 'secureByDefault': False, 'deviceComplianceCheckinThresholdDays': 30,
            'enhancedJailBreak': False, 'isScheduledActionEnabled': True, 'settings': settings})

        g = self.groups
        deleted_group = self.guid()  # unresolved reference
        policies = [
            # (name, platform, settings, [(targetType, groupId)], [(actionType, gracePeriodHours)])
            ('Windows 10/11 baseline', 'windows10', {
                'passwordRequired': True, 'passwordMinimumLength': 12, 'osMinimumVersion': '10.0.19045',
                'osMaximumVersion': None, 'bitLockerEnabled': True, 'secureBootEnabled': True,
                'codeIntegrityEnabled': True, 'storageRequireEncryption': True, 'defenderEnabled': True,
                'deviceThreatProtectionEnabled': False, 'deviceThreatProtectionRequiredSecurityLevel': 'unavailable',
            }, [('group', g[0]), ('exclusionGroup', g[7])], [('block', 72), ('notification', 0)]),
            ('iOS corporate devices', 'ios', {
                'passcodeRequired': True, 'passcodeMinimumLength': 6, 'securityBlockJailbrokenDevices': True,
                'osMinimumVersion': '17.0', 'managedEmailProfileRequired': False,
            }, [('allLicensedUsers', None)], [('block', 0)]),
            ('Android work profile', 'androidWorkProfile', {
                'passwordRequired': True, 'passwordMinimumLength': 6, 'securityBlockJailbrokenDevices': True,
                'securityRequireSafetyNetAttestationBasicIntegrity': True, 'storageRequireEncryption': True,
                'osMinimumVersion': '12.0',
            }, [('group', g[3]), ('group', g[4])], [('block', 24), ('notification', 0), ('retire', 720)]),
            ('macOS FileVault', 'macOS', {
                'passwordRequired': False, 'storageRequireEncryption': True, 'firewallEnabled': True,
                'systemIntegrityProtectionEnabled': True, 'gatekeeperAllowedAppSource': 'macAppStoreAndIdentifiedDevelopers',
            }, [('allDevices', None), ('exclusionGroup', deleted_group)], [('block', 0)]),
            ('Windows 10/11 legacy (unassigned)', 'windows10', {
                'passwordRequired': False, 'bitLockerEnabled': False,
            }, [], [('notification', 0)]),
        ]
        targets = {'group': 'groupAssignmentTarget', 'exclusionGroup': 'exclusionGroupAssignmentTarget',
                   'allLicensedUsers': 'allLicensedUsersAssignmentTarget', 'allDevices': 'allDevicesAssignmentTarget'}
        for name, platform, settings, assignments, actions in policies:
            pid = self.guid()
            created = self.dt()
            odata = '#microsoft.graph.%sCompliancePolicy' % platform
            self.add(db.DeviceCompliancePolicy, {
                'id': pid, 'odataType': odata, 'platform': platform, 'displayName': name,
                'description': f'{name} compliance policy', 'createdDateTime': created,
                'lastModifiedDateTime': created + datetime.timedelta(days=self.rng.randint(0, 300)), 'version': 2,
                'settings': {'@odata.type': odata, 'id': pid, 'displayName': name, 'roleScopeTagIds': ['0'],
                             'version': 2, **settings},
                'scheduledActionsForRule': [{'ruleName': 'PasswordRequired', 'scheduledActionConfigurations': [
                    {'actionType': a, 'gracePeriodHours': h,
                     'notificationTemplateId': self.guid() if a == 'notification' else ZERO_GUID,
                     'notificationMessageCCList': []} for a, h in actions]}],
            })
            for ttype, gid in assignments:
                target = {'@odata.type': '#microsoft.graph.' + targets[ttype],
                          'deviceAndAppManagementAssignmentFilterId': None,
                          'deviceAndAppManagementAssignmentFilterType': 'none'}
                if gid:
                    target['groupId'] = gid
                self.add(db.DeviceCompliancePolicyAssignment, {
                    'id': self.guid(), 'policyId': pid, 'targetType': ttype, 'groupId': gid,
                    'filterId': None, 'filterType': 'none', 'target': target})

        # Device page: one device in targeted groups (Engineering, nested under All Staff; Contractors excludes it
        # from the Windows baseline), and one reached through an owner in Engineering.
        in_group = {r['Device'] for r in self.rows[db.lnk_group_member_device]}
        dev, owned = [x for x in self.devices if x not in in_group][:2]
        self.link(db.lnk_group_member_device, Group=g[4], Device=dev)
        self.link(db.lnk_group_member_device, Group=g[7], Device=dev)
        user = next(r['User'] for r in self.rows[db.lnk_group_member_user] if r['Group'] == g[4])
        self.link(db.lnk_device_owner, Device=owned, User=user)

    # -- build / write -----------------------------------------------------
    def build(self):
        self.gen_users()
        self.gen_contacts()
        self.gen_groups()
        self.gen_group_memberships()
        self.gen_devices()
        self.gen_sps_and_apps()
        self.gen_group_sp_owners()
        self.gen_approle_assignments()
        self.gen_oauth2_grants()
        self.gen_roles()
        self.gen_aus()
        self.gen_tenant_and_settings()
        self.gen_named_locations()
        self.gen_ca_policies()
        if not self.minimal:
            self.gen_auth_strengths()  # type-44 rows: omitted from minimal (old dump) to test the fallback
            self.gen_pim()
            self.gen_ig()
            self.gen_az()
            self.gen_compliance()


MINIMAL_PREFIXES = ('PIM', 'IG', 'AZ', 'DeviceManagement', 'DeviceCompliance')


def _drop_minimal_tables(engine):
    """Remove PIM*/IG*/AZ* and Intune compliance tables, plus their link tables, to emulate old dumps."""
    from sqlalchemy import text
    names = [t for t in database.Base.metadata.tables
             if t.startswith(MINIMAL_PREFIXES)
             or t.startswith('lnk_pim') or t.startswith('lnk_ig') or t.startswith('lnk_az')]
    with engine.begin() as conn:
        for name in names:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % name))


def generate(path, users=300, seed=1, minimal=False):
    """Build a synthetic roadrecon.db at *path*. Returns the SQLAlchemy dburl."""
    if os.path.exists(path):
        os.remove(path)
    dburl = database.parse_db_argument(path)
    engine = database.init(create=True, dburl=dburl)
    if minimal:
        _drop_minimal_tables(engine)

    gen = Gen(users, seed, minimal)
    gen.build()

    # Bulk insert every table via Core executemany (fast and order-independent in SQLite).
    with engine.begin() as conn:
        for table, rows in gen.rows.items():
            if not rows:
                continue
            tbl = table.__table__ if hasattr(table, '__table__') else table
            # Core executemany needs identical keys in every dict of the batch;
            # pad each row to the union of keys used across the batch.
            keys = set().union(*(r.keys() for r in rows))
            rows = [{k: r.get(k) for k in keys} for r in rows]
            conn.execute(tbl.insert(), rows)

    # Fill lnk_policy_user_* the way policyanalysis would after a gather.
    session = database.get_session(engine)
    policyanalysis.dburl = dburl
    policyanalysis.PoliciesPlugin(session).main()
    session.close()
    return dburl


def os_urandom(rng, n):
    """Deterministic pseudo-random bytes (not os.urandom) so output is seed-stable."""
    return bytes(rng.getrandbits(8) for _ in range(n))


def main():
    parser = argparse.ArgumentParser(description='Generate a synthetic roadrecon.db for tests.')
    parser.add_argument('-o', '--output', required=True, help='Output SQLite database path')
    parser.add_argument('--users', type=int, default=300, help='Number of users (default 300)')
    parser.add_argument('--seed', type=int, default=1, help='Random seed (default 1)')
    parser.add_argument('--minimal', action='store_true',
                        help='Leave out PIM*/IG*/AZ* and compliance tables (emulate old dumps)')
    args = parser.parse_args()
    import time
    t0 = time.perf_counter()
    generate(args.output, users=args.users, seed=args.seed, minimal=args.minimal)
    size = os.path.getsize(args.output)
    print('Generated %s (%d users, seed %d%s) in %.2fs, %.1f MiB' % (
        args.output, args.users, args.seed, ', minimal' if args.minimal else '',
        time.perf_counter() - t0, size / 1048576))


if __name__ == '__main__':
    main()
