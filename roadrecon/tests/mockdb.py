#!/usr/bin/env python3
"""
Generate a showcase roadrecon.db with believable fake data, for screenshots of the ROADrecon GUI.

Built on gendb.py (same table shapes, same gatherer-accurate JSON), but tuned for looks rather than
test coverage: one coherent fictional company (Contoso, Microsoft's own demo tenant name), real
first-party and SaaS application names, users whose department, title, office and groups agree,
devices owned by their users, dates leading up to the gather date, and no deliberately broken
references (unresolved ids, stale policies) that gendb keeps for the tests.

Intune device compliance is left out: no collector fills it on a real dump, so it should not show
in screenshots either.

Usage:
    python roadrecon/tests/mockdb.py -o roadrecon/.dev/mock.db [--users N] [--seed S]
"""
import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import roadtools.roadlib.metadef.database as database  # noqa: E402
from roadtools.roadlib.metadef import database as db  # noqa: E402
from roadtools.roadrecon.plugins import policyanalysis  # noqa: E402

import gendb  # noqa: E402
from gendb import (AUTHSTRENGTH_CUSTOM, AUTHSTRENGTH_MFA, AUTHSTRENGTH_PHISHRESISTANT,  # noqa: E402
                   GRAPH_APPID, ROLE_TEMPLATES, ZERO_GUID, Gen)

# The day the data was "gathered": every generated date falls before it.
NOW = datetime.datetime(2026, 10, 28, 9, 42)

# Microsoft's fictional demo personas, used for the people who show up most (admins, owners, approvers).
PERSONAS = [
    ('Megan', 'Bowen', 'Marketing', 'Marketing Manager', 'Seattle'),
    ('Adele', 'Vance', 'Retail', 'Retail Manager', 'Seattle'),
    ('Alex', 'Wilber', 'Sales', 'Marketing Assistant', 'Seattle'),
    ('Diego', 'Siciliani', 'HR', 'HR Manager', 'Seattle'),
    ('Isaiah', 'Langer', 'Sales', 'Sales Rep', 'London'),
    ('Lee', 'Gu', 'Engineering', 'Director', 'Seattle'),
    ('Lidia', 'Holloway', 'Engineering', 'Product Manager', 'Amsterdam'),
    ('Lynne', 'Robbins', 'Finance', 'Planner', 'London'),
    ('Miriam', 'Graham', 'Executive Management', 'Director', 'Seattle'),
    ('Nestor', 'Wilke', 'Operations', 'Director', 'Paris'),
    ('Patti', 'Fernandez', 'Executive Management', 'President', 'Seattle'),
    ('Pradeep', 'Gupta', 'Finance', 'Accountant', 'Singapore'),
    ('Johanna', 'Lorenz', 'Engineering', 'Senior Engineer', 'Amsterdam'),
    ('Joni', 'Sherman', 'Legal', 'Paralegal', 'Seattle'),
    ('Grady', 'Archie', 'IT', 'Senior Designer', 'Seattle'),
    ('Henrietta', 'Mueller', 'IT', 'Developer', 'Amsterdam'),
    ('Irvin', 'Sayers', 'IT', 'Director', 'London'),
    ('Christie', 'Cline', 'Sales', 'Buyer', 'Paris'),
    ('Debra', 'Berger', 'Executive Management', 'Administrative Assistant', 'Seattle'),
    ('Enrico', 'Cattaneo', 'Legal', 'Attorney', 'Paris'),
]
FIRST = ['Aaliyah', 'Aarav', 'Abigail', 'Ahmed', 'Aiko', 'Amara', 'Andrei', 'Anika', 'Astrid', 'Ben',
         'Bianca', 'Camille', 'Carlos', 'Chen', 'Chloe', 'Daniel', 'Dmitri', 'Elena', 'Emeka', 'Emma',
         'Fatima', 'Felix', 'Freya', 'Gabriel', 'Hana', 'Hugo', 'Ines', 'Isabel', 'Jakob', 'James',
         'Jin', 'Julia', 'Kai', 'Kenji', 'Lars', 'Laura', 'Leila', 'Liam', 'Lucas', 'Maya',
         'Mateo', 'Mei', 'Mohammed', 'Nadia', 'Noah', 'Nora', 'Olivia', 'Omar', 'Oscar', 'Priya',
         'Rafael', 'Rania', 'Ravi', 'Rosa', 'Ryan', 'Sakura', 'Samuel', 'Sara', 'Sofia', 'Sven',
         'Tariq', 'Thomas', 'Valentina', 'Wei', 'Yara', 'Yusuf', 'Zoe', 'Zainab', 'Elise', 'Marcus']
LAST = ['Andersson', 'Bakker', 'Becker', 'Bernard', 'Brown', 'Castillo', 'Chen', 'Costa', 'Dubois', 'Evans',
        'Fischer', 'Garcia', 'Haddad', 'Hansen', 'Hughes', 'Ibrahim', 'Jansen', 'Johnson', 'Kaur', 'Kim',
        'Kowalski', 'Lambert', 'Larsen', 'Lee', 'Lim', 'Lopez', 'Martin', 'Meyer', 'Moreau', 'Murphy',
        'Nakamura', 'Nguyen', 'Novak', 'Okafor', 'Olsen', 'Patel', 'Peters', 'Petrov', 'Quinn', 'Rahman',
        'Reyes', 'Rossi', 'Santos', 'Schmidt', 'Silva', 'Singh', 'Suzuki', 'Tan', 'Taylor', 'Thompson',
        'Van Dijk', 'Visser', 'Wagner', 'Walker', 'Wang', 'Weber', 'Williams', 'Wong', 'Yilmaz', 'Zhang']
DEPARTMENTS = {
    'Engineering': ['Software Engineer', 'Senior Engineer', 'Engineering Manager', 'QA Engineer', 'Architect'],
    'Sales': ['Account Executive', 'Sales Rep', 'Sales Manager', 'Inside Sales'],
    'Marketing': ['Content Strategist', 'Marketing Specialist', 'Brand Manager'],
    'Finance': ['Accountant', 'Financial Analyst', 'Controller', 'Payroll Specialist'],
    'HR': ['HR Generalist', 'Recruiter', 'HR Business Partner'],
    'IT': ['Systems Administrator', 'Service Desk Analyst', 'Cloud Engineer', 'Security Analyst'],
    'Legal': ['Attorney', 'Paralegal', 'Compliance Officer'],
    'Operations': ['Operations Analyst', 'Logistics Coordinator', 'Facilities Manager'],
    'Retail': ['Store Manager', 'Retail Associate', 'Merchandiser'],
}
DEPT_WEIGHTS = [22, 18, 8, 9, 5, 9, 4, 12, 13]
OFFICES = {  # city -> (country code, usage location, phone prefix, weight)
    'Seattle': ('US', 'US', '+1 206 555', 40),
    'London': ('GB', 'GB', '+44 20 7946', 20),
    'Amsterdam': ('NL', 'NL', '+31 20 555', 15),
    'Paris': ('FR', 'FR', '+33 1 5555', 15),
    'Singapore': ('SG', 'SG', '+65 6555', 10),
}
GUEST_ORGS = ['fabrikam.com', 'northwindtraders.com', 'adatum.com', 'litwareinc.com', 'tailspintoys.com',
              'wingtiptoys.com', 'woodgrovebank.com']

# Extra built-in directory roles on top of gendb's set (real template ids).
EXTRA_ROLES = {
    'Security Administrator': '194ae4cb-b126-40b2-bd5b-6091b380977d',
    'Exchange Administrator': '29232cdf-9323-42fd-ade2-1d097af3e4de',
    'Conditional Access Administrator': 'b1be1c3e-b65d-4f19-8427-f6fa0d97feb9',
    'Intune Administrator': '3a2c62db-5318-420d-8d74-23affee5d9d5',
    'Cloud Application Administrator': '158c047a-c907-4556-b7ef-446551a6b5f7',
    'Security Reader': '5d6b6bb7-de71-4623-b4af-96380a352509',
    'Billing Administrator': 'b0f54661-2d74-4c50-afa3-1ec803f12efe',
    'Directory Synchronization Accounts': 'd29b2b05-8046-44ba-8758-1e26182fcf32',
}
# Real first-party apps (appId is the same in every tenant).
MS_APPS = [
    ('Office 365 Exchange Online', '00000002-0000-0ff1-ce00-000000000000',
     [('full_access_as_app', 'Use Exchange Web Services with full access to all mailboxes'),
      ('Mail.ReadWrite', 'Read and write mail in all mailboxes')]),
    ('Office 365 SharePoint Online', '00000003-0000-0ff1-ce00-000000000000',
     [('Sites.FullControl.All', 'Have full control of all site collections')]),
    ('Windows Azure Active Directory', '00000002-0000-0000-c000-000000000000',
     [('Directory.Read.All', 'Read directory data')]),
    ('Microsoft Intune', '0000000a-0000-0000-c000-000000000000', []),
    ('Microsoft Teams', '1fec8e78-bce4-4aaf-ab1b-5451cc387264', []),
    ('Azure Portal', 'c44b4083-3bb0-49c1-b47d-974e53cbdf3c', []),
    ('Microsoft Azure CLI', '04b07795-8ddb-461a-bbee-02f9e1bf7b46', []),
    ('Microsoft Azure PowerShell', '1950a258-227b-4e31-a9cf-717495945fc2', []),
    ('Office 365 Management APIs', 'c5393580-f805-4401-95e8-94b7a6ef2fc2',
     [('ActivityFeed.Read', 'Read activity data for your organization')]),
    ('Windows Azure Service Management API', '797f4846-ba00-4fd7-ba43-dac1f8f63013', []),
]
SAAS_APPS = [  # name, publisher, app role
    ('Salesforce', 'Salesforce.com, inc.', 'User'),
    ('ServiceNow', 'ServiceNow, Inc.', 'itil'),
    ('Slack', 'Slack Technologies', 'User'),
    ('Zoom', 'Zoom Video Communications', 'User'),
    ('Atlassian Cloud', 'Atlassian', 'User'),
    ('Workday', 'Workday, Inc.', 'Employee'),
    ('DocuSign', 'DocuSign Inc.', 'DocuSign Sender'),
    ('GitHub Enterprise Cloud', 'GitHub, Inc.', 'User'),
    ('Datadog', 'Datadog, Inc.', 'Datadog Standard'),
    ('Miro', 'RealtimeBoard Inc.', 'User'),
]
LOB_APPS = [  # name, host, Graph app permissions (by value), delegated scopes, multi-tenant
    ('Contoso Customer Portal', 'portal.contoso.com', [], ['User.Read'], True),
    ('Contoso HR Sync', None, ['User.Read.All', 'Directory.Read.All'], [], False),
    ('Contoso Expense API', 'expenses.contoso.com', [], ['User.Read'], False),
    ('Contoso Mail Archiver', None, ['Mail.Read'], [], False),
    ('Azure DevOps Deploy (prod)', None, ['Application.ReadWrite.All'], [], False),
    ('Identity Automation', None, ['RoleManagement.ReadWrite.Directory', 'User.Read.All'], [], False),
    ('Store Inventory Mobile', 'inventory.contoso.com', [], ['User.Read', 'Mail.Read'], False),
    ('Contoso Intranet', 'intranet.contoso.com', [], ['User.Read'], False),
]


class MockGen(Gen):
    def __init__(self, nusers, seed):
        super().__init__(nusers, seed, minimal=False)
        self.domain = 'contoso.onmicrosoft.com'
        self.vanity = 'contoso.com'

    def dt(self, days_ago_max=1500):
        return NOW - datetime.timedelta(seconds=self.rng.randint(3600, days_ago_max * 86400))

    def recent(self, days=30):
        return self.dt(days)

    # -- users ---------------------------------------------------------------
    def _user(self, fn, ln, upn, dept=None, title=None, city=None, enabled=True, guest=False,
              synced=False, mfa=None, extra=None):
        oid = self.guid()
        country, usage, phone, _ = OFFICES.get(city, (None, 'US', None, 0))
        detail = self._mfa_detail()
        if mfa is True and not detail['methods']:
            detail['methods'] = [{'methodType': 'PhoneAppNotification', 'default': True, 'isDefault': True},
                                 {'methodType': 'PhoneAppOTP', 'default': False, 'isDefault': False}]
        elif mfa is False:
            detail = {'methods': [], 'requirements': [], 'verificationDetail': None}
        created = self.dt(2200)
        row = {
            'objectType': 'User',
            'objectId': oid,
            'accountEnabled': enabled,
            'displayName': f'{fn} {ln}'.strip(),
            'givenName': fn if ln else None,
            'surname': ln or None,
            'userPrincipalName': upn,
            'mail': None if guest else upn,
            'mailNickname': upn.split('@')[0].split('#')[0],
            'userType': 'Guest' if guest else 'Member',
            'dirSyncEnabled': True if synced else None,
            'department': dept,
            'jobTitle': title,
            'mobile': f'{phone} {self.rng.randint(1000, 9999)}' if phone and self.chance(0.6) else None,
            'telephoneNumber': f'{phone} {self.rng.randint(1000, 9999)}' if phone and self.chance(0.3) else None,
            'city': city,
            'country': country,
            'usageLocation': usage,
            'physicalDeliveryOfficeName': f'{city} HQ' if city == 'Seattle' else city,
            'createdDateTime': created,
            'lastPasswordChangeDateTime': created + (NOW - created) * self.rng.uniform(0.4, 1.0),
            'onPremisesSecurityIdentifier': self._sid(True) if synced else None,
            'onPremisesDistinguishedName': (f'CN={fn} {ln},OU=Users,OU={city},DC=corp,DC=contoso,DC=com'
                                            if synced else None),
            'lastDirSyncTime': self.recent(1) if synced else None,
            'cloudSecurityIdentifier': self._sid(False),
            'strongAuthenticationDetail': detail,
            'searchableDeviceKey': self._device_keys() if not guest else [],
            **(extra or {}),
        }
        if guest:
            row['mail'] = upn.split('#EXT#')[0][::-1].replace('_', '@', 1)[::-1]
            row['userState'] = 'Accepted' if self.chance(0.85) else 'PendingAcceptance'
            row['creationType'] = 'Invitation'
        self.add(db.User, row)
        self.users.append((oid, row['userType'], enabled))
        if enabled:
            self.enabled_users.append(oid)
        self.user_info[oid] = row
        return oid

    def gen_users(self):
        self.users, self.enabled_users, self.user_info = [], [], {}
        self.admins = []        # (oid, displayName) of the adm- accounts
        self.staff = []         # enabled member employees
        taken = set()

        def upn_for(fn, ln):
            base = f'{fn}.{ln}'.lower().replace(' ', '')
            upn, n = base, 2
            while upn in taken:
                upn, n = f'{base}{n}', n + 1
            taken.add(upn)
            return f'{upn}@{self.vanity}'

        # Break-glass accounts: cloud-only, excluded from every CA policy.
        self.ga_user = self._user('Break Glass', 'Account 01', f'breakglass01@{self.domain}', mfa=False)
        self.breakglass = [self.ga_user,
                           self._user('Break Glass', 'Account 02', f'breakglass02@{self.domain}', mfa=False)]
        # The directory sync account Entra Connect creates.
        self.sync_account = self._user('On-Premises Directory Synchronization Service Account', '',
                                       f'Sync_CTS-ADC01_8f3e2a1b9c4d@{self.domain}', mfa=False)

        for fn, ln, dept, title, city in PERSONAS:
            self.staff.append(self._user(fn, ln, upn_for(fn, ln), dept, title, city, synced=True))
        for fn, ln in [('Grady', 'Archie'), ('Irvin', 'Sayers'), ('Henrietta', 'Mueller'), ('Lee', 'Gu')]:
            self.admins.append(self._user(f'ADM {fn}', ln, f'adm-{fn}.{ln}@{self.domain}'.lower(),
                                          'IT', 'Administrative account', mfa=True))

        rest = self.nusers - len(self.user_info) - 7  # shared mailboxes and service accounts below
        cities = list(OFFICES)
        city_w = [OFFICES[c][3] for c in cities]
        for _ in range(max(rest, 0)):
            fn, ln = self.pick(FIRST), self.pick(LAST)
            if self.chance(0.07):
                org = self.pick(GUEST_ORGS)
                local = f'{fn}.{ln}'.lower().replace(' ', '')
                self._user(fn, ln, f'{local}_{org}#EXT#@{self.domain}', guest=True,
                           enabled=not self.chance(0.05), extra={'companyName': org.split('.')[0].title()})
                continue
            dept = self.rng.choices(list(DEPARTMENTS), DEPT_WEIGHTS)[0]
            city = self.rng.choices(cities, city_w)[0]
            enabled = not self.chance(0.06)
            oid = self._user(fn, ln, upn_for(fn, ln), dept, self.pick(DEPARTMENTS[dept]), city,
                             enabled=enabled, synced=self.chance(0.85))
            if enabled:
                self.staff.append(oid)

        for name, local in [('Reception Seattle', 'reception.seattle'), ('Finance Invoices', 'invoices'),
                            ('IT Service Desk', 'servicedesk'), ('Board Room 4.01', 'boardroom401')]:
            oid = self._user(name, '', f'{local}@{self.vanity}', enabled=False, mfa=False)
            self.user_info[oid].update({'givenName': None, 'surname': None, 'cloudMSExchRecipientDisplayType': 0,
                                        'msExchRecipientTypeDetails': 34359738368})
        for name, local, dept in [('svc-backup', 'svc-backup', 'IT'), ('svc-scanner', 'svc-scanner', 'Operations'),
                                  ('svc-powerbi-gateway', 'svc-pbigw', 'IT')]:
            self._user(name, '', f'{local}@{self.vanity}', dept, 'Service account', synced=True, mfa=False)
        self.user_ids = [u[0] for u in self.users]
        # gendb takes enabled_users[:2] for scopes and assignees: put real employees first.
        self.enabled_users = self.staff + [u for u in self.enabled_users if u not in set(self.staff)]

    def person(self, oid):
        return self.user_info[oid]['displayName']

    def staff_in(self, dept=None, city=None):
        return [u for u in self.staff
                if (dept is None or self.user_info[u]['department'] == dept)
                and (city is None or self.user_info[u]['city'] == city)]

    def gen_contacts(self):
        for name, mail in [('Northwind Traders Support', 'support@northwindtraders.com'),
                           ('Fabrikam Accounts Payable', 'ap@fabrikam.com'),
                           ('Woodgrove Bank Relationship Manager', 'rm.contoso@woodgrovebank.com'),
                           ('Litware Legal Counsel', 'counsel@litwareinc.com'),
                           ('Adatum Facilities', 'facilities@adatum.com')]:
            self.add(db.Contact, {
                'objectType': 'Contact', 'objectId': self.guid(), 'displayName': name, 'mail': mail,
                'dirSyncEnabled': True, 'proxyAddresses': [f'SMTP:{mail}'],
            })

    # -- groups --------------------------------------------------------------
    def _group(self, name, desc, unified=False, rule=None, assignable=False, synced=False, visibility=None):
        oid = self.guid()
        nick = name.lower().replace(' - ', '-').replace(' ', '-')
        self.add(db.Group, {
            'objectType': 'Group',
            'objectId': oid,
            'displayName': name,
            'description': desc,
            'securityEnabled': True,
            'mailEnabled': unified,
            'mail': f'{nick}@{self.vanity}' if unified else None,
            'mailNickname': nick,
            'groupTypes': (['Unified'] if unified else []) + (['DynamicMembership'] if rule else []),
            'isAssignableToRole': True if assignable else None,
            'isPublic': visibility == 'Public' if unified else None,
            'visibility': visibility if unified else None,
            'dirSyncEnabled': True if synced else None,
            'lastDirSyncTime': self.recent(1) if synced else None,
            'onPremisesSecurityIdentifier': self._sid(True) if synced else None,
            'createdDateTime': self.dt(2000),
            'cloudSecurityIdentifier': self._sid(False),
            'membershipRule': rule,
            'membershipRuleProcessingState': 'On' if rule else None,
        })
        self.groups.append(oid)
        self.group_by_name[name] = oid
        return oid

    def gen_groups(self):
        self.groups, self.group_by_name = [], {}
        G = self._group
        # The first 14 keep gendb's positions (gen_compliance, gen_group_sp_owners and gen_aus index into them).
        G('All Staff', 'Every employee, through the office groups', synced=True)
        self.role_assignable_group = G('Tier 0 - Identity Admins', 'Role-assignable: holds the identity admin roles',
                                       assignable=True)
        G('Finance', 'Finance department', rule='(user.department -eq "Finance")')
        G('Sales EMEA', 'Sales team in London, Amsterdam and Paris', synced=True)
        G('Engineering', 'Engineering department', rule='(user.department -eq "Engineering")')
        self.m365_group = G('Project Falcon', 'Next-generation retail platform', unified=True, visibility='Private')
        G('Security Operations', 'SOC analysts and incident responders', synced=True)
        G('Contractors', 'External contractors with a Contoso account', synced=True)
        G('All Guests', 'Every B2B guest', rule='(user.userType -eq "Guest")')
        G('VPN Users', 'Allowed on the Always On VPN profile', synced=True)
        G('License - Microsoft 365 E5', 'Group-based licensing: Microsoft 365 E5', synced=True)
        G('IT Service Desk', 'First-line support', synced=True)
        G('Devices - Corporate Windows', 'Every corporate Windows device',
          rule='(device.deviceOSType -eq "Windows") -and (device.deviceOwnership -eq "Company")')
        G('People Managers', 'Everyone with direct reports', synced=True)
        for dept in ('HR', 'IT', 'Legal', 'Marketing', 'Sales', 'Operations', 'Retail'):
            G(dept if dept != 'IT' else 'IT Department', f'{dept} department',
              rule=f'(user.department -eq "{dept}")')
        for city in OFFICES:
            G(f'Office - {city}', f'Everyone based in {city}', synced=True)
        G('CA - Exclude Break Glass', 'Emergency access accounts excluded from Conditional Access')
        G('CA - Pilot Passwordless', 'Pilot ring for phishing-resistant sign-in')
        G('App - Salesforce Users', 'Assigned to the Salesforce enterprise app')
        G('App - ServiceNow Agents', 'ServiceNow ITIL licence holders')
        G('Azure - Production Contributors', 'Contributor on the production subscription')
        G('Azure - Subscription Owners', 'Eligible Owner on every subscription (PIM)')
        G('Contoso Leadership', 'Executive leadership team', unified=True, visibility='Private')
        G('Marketing Campaigns 2026', 'Campaign planning and assets', unified=True, visibility='Public')
        G('Seattle Social Club', 'After-work events in Seattle', unified=True, visibility='Public')
        G('Store Managers', 'Retail store managers', unified=True, visibility='Private')

    def gen_group_memberships(self):
        g = self.group_by_name
        L = lambda grp, user: self.link(db.lnk_group_member_user, Group=g[grp], User=user)  # noqa: E731
        dept_group = {'Finance': 'Finance', 'Engineering': 'Engineering', 'HR': 'HR', 'IT': 'IT Department',
                      'Legal': 'Legal', 'Marketing': 'Marketing', 'Sales': 'Sales', 'Operations': 'Operations',
                      'Retail': 'Retail'}
        for oid, utype, enabled in self.users:
            u = self.user_info[oid]
            if utype == 'Guest':
                L('All Guests', oid)
                if self.chance(0.4):
                    L('Project Falcon', oid)
                continue
            if u['city']:
                L(f'Office - {u["city"]}', oid)
            if u['department'] in dept_group and u['jobTitle'] not in ('Administrative account', 'Service account'):
                L(dept_group[u['department']], oid)
                if self.chance(0.8):
                    L('License - Microsoft 365 E5', oid)
            if u['department'] == 'Sales' and u['city'] in ('London', 'Amsterdam', 'Paris'):
                L('Sales EMEA', oid)
                L('App - Salesforce Users', oid)
            elif u['department'] == 'Sales':
                L('App - Salesforce Users', oid)
            if u['department'] == 'IT' and 'Desk' in (u['jobTitle'] or ''):
                L('IT Service Desk', oid)
            if u['department'] == 'IT' and 'Security' in (u['jobTitle'] or ''):
                L('Security Operations', oid)
            if u['department'] == 'IT' and u['jobTitle'] != 'Administrative account' and self.chance(0.5):
                L('App - ServiceNow Agents', oid)
            if u['department'] == 'Retail' and u['jobTitle'] == 'Store Manager':
                L('Store Managers', oid)
            if any(w in (u['jobTitle'] or '') for w in ('Manager', 'Director', 'President', 'Controller')):
                L('People Managers', oid)
            if u['department'] == 'Executive Management':
                L('Contoso Leadership', oid)
            if u['department'] == 'Engineering' and self.chance(0.3):
                L('Project Falcon', oid)
            if u['department'] == 'Engineering' and self.chance(0.25):
                L('Azure - Production Contributors', oid)
            if u['department'] == 'Marketing' or (u['department'] and self.chance(0.03)):
                L('Marketing Campaigns 2026', oid)
            if u['city'] == 'Seattle' and self.chance(0.15):
                L('Seattle Social Club', oid)
            if u['department'] in ('Engineering', 'Sales', 'IT') and self.chance(0.6):
                L('VPN Users', oid)
            if u['department'] == 'Operations' and self.chance(0.2):
                L('Contractors', oid)
        for oid in self.breakglass:
            L('CA - Exclude Break Glass', oid)
        for oid in self.admins:
            L('Tier 0 - Identity Admins', oid)
        L('Azure - Subscription Owners', self.admins[0])
        L('Azure - Subscription Owners', self.admins[1])
        for oid in self.staff_in('IT')[:6]:
            L('CA - Pilot Passwordless', oid)
        # Nesting: All Staff holds the office groups, the IT department holds the desk and the SOC.
        for city in OFFICES:
            self.link(db.lnk_group_member_group, Group=g['All Staff'], childGroup=g[f'Office - {city}'])
        self.link(db.lnk_group_member_group, Group=g['IT Department'], childGroup=g['IT Service Desk'])
        self.link(db.lnk_group_member_group, Group=g['IT Department'], childGroup=g['Security Operations'])
        self.link(db.lnk_group_member_group, Group=g['Sales'], childGroup=g['Sales EMEA'])
        self.link(db.lnk_group_member_group, Group=g['Azure - Subscription Owners'],
                  childGroup=g['Tier 0 - Identity Admins'])
        self.nested_chain_head = g['All Staff']

    # -- devices -------------------------------------------------------------
    def gen_devices(self):
        self.devices = []
        win = [('Dell', 'Latitude 7440'), ('Dell', 'Latitude 5540'), ('Lenovo', 'ThinkPad T14 Gen 4'),
               ('Lenovo', 'ThinkPad X1 Carbon Gen 11'), ('HP', 'EliteBook 840 G10'),
               ('Microsoft Corporation', 'Surface Laptop 5')]
        win_ver = ['10.0.22631.4317', '10.0.22631.4460', '10.0.26100.2033', '10.0.19045.5011']
        n = {'LT': 0, 'DT': 0, 'MAC': 0}

        def add(name, ostype, osver, maker, model, trust, ownership, owner=None, managed=True, compliant=None,
                enabled=True, days=21):
            oid = self.guid()
            self.add(db.Device, {
                'objectType': 'Device',
                'objectId': oid,
                'accountEnabled': enabled,
                'displayName': name,
                'deviceId': self.guid(),
                'deviceManufacturer': maker,
                'deviceModel': model,
                'deviceOSType': ostype,
                'deviceOSVersion': osver,
                'deviceTrustType': trust,
                'deviceOwnership': ownership,
                'isCompliant': compliant if compliant is not None else (managed and not self.chance(0.12)),
                'isManaged': managed,
                'isRooted': False,
                'profileType': 'RegisteredDevice',
                'approximateLastLogonTimestamp': self.recent(days),
                'dirSyncEnabled': True if trust == 'ServerAd' else None,
                'bitLockerKey': self._bitlocker() if ostype == 'Windows' and ownership == 'Company' else [],
            })
            self.devices.append(oid)
            if owner:
                self.link(db.lnk_device_owner, Device=oid, User=owner)
            return oid

        cap = max(20, min(len(self.staff), 400))
        for u in self.staff[:cap]:
            info = self.user_info[u]
            if info['department'] in ('Marketing',) or (info['department'] == 'Engineering' and self.chance(0.35)):
                n['MAC'] += 1
                add(f'CTS-MAC-{n["MAC"]:04d}', 'MacMDM', self.pick(['14.7', '15.0.1', '15.1']), 'Apple',
                    self.pick(['MacBook Pro (14-inch, M3)', 'MacBook Air (15-inch, M2)']), 'AzureAd', 'Company', u)
            elif info['department'] == 'Retail' and self.chance(0.5):
                pass  # store staff use shared kiosks
            else:
                kind = 'DT' if info['department'] in ('Finance', 'Operations') and self.chance(0.4) else 'LT'
                n[kind] += 1
                maker, model = self.pick(win) if kind == 'LT' else ('Dell', 'OptiPlex 7010')
                add(f'CTS-{kind}-{n[kind]:04d}', 'Windows', self.pick(win_ver), maker, model,
                    self.pick(['AzureAd', 'AzureAd', 'ServerAd']), 'Company', u)
            if self.chance(0.45):
                if self.chance(0.55):
                    add(f'{info["givenName"]}\'s iPhone', 'iOS', self.pick(['17.6.1', '18.0.1', '18.1']), 'Apple',
                        self.pick(['iPhone 14', 'iPhone 15', 'iPhone 15 Pro', 'iPhone 16']), 'Workplace',
                        self.pick(['Personal', 'Company']), u)
                else:
                    add(f'{info["givenName"]}\'s Galaxy', 'Android', self.pick(['14', '15']), 'samsung',
                        self.pick(['SM-S921B', 'SM-A546B', 'SM-S928B']), 'Workplace', 'Personal', u)
        for i in range(1, 9):
            add(f'CTS-SRV-{["DC", "DC", "ADC", "FS", "APP", "APP", "SQL", "PRN"][i - 1]}{i:02d}', 'Windows',
                '10.0.20348.2762', 'Microsoft Corporation', 'Virtual Machine', 'ServerAd', 'Company',
                managed=False, compliant=False, days=2)
        for i in range(1, 7):
            add(f'CTS-KIOSK-{i:03d}', 'Windows', '10.0.22631.4317', 'HP', 'Engage One', 'AzureAd', 'Company',
                days=3)
        # A few stale ones, for the inactive-device views.
        for i in range(1, 5):
            add(f'DESKTOP-{self.rng.randint(1000000, 9999999):X}'[:15], 'Windows', '10.0.19044.1288',
                self.pick(['Dell', 'HP']), self.pick(['Latitude 7400', 'EliteBook 830 G6']), 'Workplace',
                'Personal', self.pick(self.staff), managed=False, compliant=False, enabled=i > 2, days=900)
        for i in range(1, 3):
            add(f'ubuntu-dev-{i:02d}', 'Linux', '22.04', 'Lenovo', 'ThinkPad P16s', 'AzureAd', 'Company',
                self.pick(self.staff_in('Engineering') or self.staff), managed=False, compliant=False)

    # -- applications and service principals ----------------------------------
    def gen_sps_and_apps(self):
        self.sps, self.sp_by_appid, self.apps = [], {}, []
        graph_roles = {v: self._approle(v, d) for v, d in [
            ('User.Read.All', "Read all users' full profiles"),
            ('Directory.Read.All', 'Read directory data'),
            ('Mail.Read', 'Read mail in all mailboxes'),
            ('RoleManagement.ReadWrite.Directory', 'Read and write all directory RBAC settings'),
            ('Application.ReadWrite.All', 'Read and write all applications'),
            ('Group.ReadWrite.All', 'Read and write all groups'),
            ('Sites.Read.All', 'Read items in all site collections'),
            ('AuditLog.Read.All', 'Read all audit log data'),
        ]}
        graph_scopes = {v: self._scope(v, d, c) for v, d, c in [
            ('User.Read', 'Sign in and read user profile', 'User'),
            ('Mail.Read', 'Read user mail', 'User'),
            ('Files.ReadWrite.All', 'Have full access to all files user can access', 'User'),
            ('Directory.AccessAsUser.All', 'Access directory as the signed in user', 'Admin'),
            ('offline_access', 'Maintain access to data you have given it access to', 'User'),
        ]}
        self.graph_roles, self.graph_scopes = graph_roles, graph_scopes
        self.graph_sp = self._add_sp('Microsoft Graph', GRAPH_APPID, microsoft=True,
                                     approles=list(graph_roles.values()), scopes=list(graph_scopes.values()),
                                     publisher='Microsoft Services')
        for name, appid, roles in MS_APPS:
            self._add_sp(name, appid, microsoft=True, publisher='Microsoft Services',
                         approles=[self._approle(v, d) for v, d in roles])
        for name, res in [('id-backup-prod', 'Microsoft.ManagedIdentity/userAssignedIdentities/id-backup-prod'),
                          ('func-invoice-processor', 'Microsoft.Web/sites/func-invoice-processor'),
                          ('logic-hr-onboarding', 'Microsoft.Logic/workflows/logic-hr-onboarding')]:
            self._add_sp(name, self.guid(), sptype='ManagedIdentity',
                         mi_resource=f'/subscriptions/{self.guid()}/resourcegroups/rg-prod-weu/providers/{res}')

        self.thirdparty_sps, self.saas = [], {}
        for name, publisher, role in SAAS_APPS:
            sp = self._add_sp(name, self.guid(), publisher=publisher, owner_tenant=self.guid(),
                              approles=[self._approle(role, role, 'User'), self._approle('msiam_access', 'msiam_access', 'User')],
                              scopes=[self._scope('user_impersonation', f'Access {name}', 'User')])
            self.thirdparty_sps.append(sp)
            self.saas[name] = sp

        owners = self.staff_in('IT') + self.staff_in('Engineering') or self.staff
        for name, host, perms, scopes, multi in LOB_APPS:
            appid = self.guid()
            urls = {}
            if host:
                urls = {'homepage': f'https://{host}', 'logoutUrl': f'https://{host}/signout',
                        'replyUrls': [f'https://{host}/signin-oidc']}
            sp = self._add_sp(name, appid, publisher='Contoso Ltd', urls=urls,
                              approles=[self._approle('Reader', 'Read access', 'User'),
                                        self._approle('Admin', 'Administrator', 'User')] if host else [],
                              scopes=[self._scope('access_as_user', f'Access {name}', 'User')] if host else [])
            app_oid = self.guid()
            secret = not host or self.chance(0.4)
            self.add(db.Application, {
                'objectType': 'Application',
                'objectId': app_oid,
                'displayName': name,
                'appId': appid,
                'availableToOtherTenants': multi,
                'publicClient': name == 'Store Inventory Mobile',
                'oauth2AllowImplicitFlow': name == 'Contoso Intranet',
                'oauth2AllowIdTokenImplicitFlow': name == 'Contoso Intranet',
                'homepage': urls.get('homepage'),
                'replyUrls': urls.get('replyUrls', []) + (['http://localhost:5000/signin-oidc']
                                                          if name == 'Contoso Expense API' else []),
                'identifierUris': [f'api://{appid}'],
                'appRoles': [],
                'oauth2Permissions': [],
                'keyCredentials': self._key_creds() if not secret else [],
                'passwordCredentials': self._recent_secret() if secret else [],
                'requiredResourceAccess': [{
                    'resourceAppId': GRAPH_APPID,
                    'resourceAccess': [{'id': graph_scopes[s]['id'], 'type': 'Scope'} for s in scopes]
                    + [{'id': graph_roles[r]['id'], 'type': 'Role'} for r in perms],
                }],
                'publisherDomain': self.vanity,
                'appMetadata': {'version': 1, 'data': []},
            })
            self.apps.append(app_oid)
            self.lob = getattr(self, 'lob', {})
            self.lob[name] = (app_oid, sp, perms, scopes)
            owner = self.pick(owners)
            self.link(db.lnk_application_owner_user, Application=app_oid, User=owner)
            self.link(db.lnk_serviceprincipal_owner_user, ServicePrincipal=sp, User=owner)
        # An automation SP that owns the deployment app: an ownership path worth showing.
        self.link(db.lnk_application_owner_serviceprincipal, Application=self.lob['Contoso HR Sync'][0],
                  ServicePrincipal=self.lob['Azure DevOps Deploy (prod)'][1])

    def _recent_secret(self):
        start = self.dt(500)
        return [{'keyId': self.guid(), 'startDate': start.isoformat() + 'Z',
                 'endDate': (start + datetime.timedelta(days=self.pick([180, 365, 730]))).isoformat() + 'Z',
                 'customKeyIdentifier': None, 'value': None}]

    def gen_group_sp_owners(self):
        g = self.group_by_name
        it = self.staff_in('IT') or self.staff
        for name, gid in g.items():
            if name.startswith(('Devices', 'All Guests')) or self.groups.index(gid) % 4 == 3:
                continue
            self.link(db.lnk_group_owner_user, Group=gid, User=self.pick(it))
        self.link(db.lnk_group_owner_serviceprincipal, Group=g['App - Salesforce Users'],
                  ServicePrincipal=self.lob['Identity Automation'][1])
        self.link(db.lnk_group_member_serviceprincipal, Group=g['Tier 0 - Identity Admins'],
                  ServicePrincipal=self.lob['Identity Automation'][1])
        for dev in self.rows[db.Device]:
            if dev['deviceOSType'] == 'Windows' and dev['deviceOwnership'] == 'Company':
                self.link(db.lnk_group_member_device, Group=g['Devices - Corporate Windows'], Device=dev['objectId'])
        for c in self.rows.get(db.Contact, [])[:2]:
            self.link(db.lnk_group_member_contact, Group=g['Finance'], Contact=c['objectId'])

    def _ara(self, role_id, principal, ptype, resource):
        self.add(db.AppRoleAssignment, {
            'objectType': 'AppRoleAssignment', 'objectId': self.guid(), 'id': role_id,
            'principalId': principal, 'principalType': ptype, 'principalDisplayName': '',
            'resourceId': resource, 'resourceDisplayName': '', 'creationTimestamp': self.dt(1200),
        })

    def gen_approle_assignments(self):
        # Application permissions granted on Microsoft Graph to the line-of-business apps.
        for name, (app, sp, perms, scopes) in self.lob.items():
            for p in perms:
                self._ara(self.graph_roles[p]['id'], sp, 'ServicePrincipal', self.graph_sp)
        # A SaaS vendor with Graph application access, and the HR sync on Exchange.
        self._ara(self.graph_roles['Directory.Read.All']['id'], self.saas['Workday'], 'ServicePrincipal', self.graph_sp)
        self._ara(self.graph_roles['Sites.Read.All']['id'], self.saas['Miro'], 'ServicePrincipal', self.graph_sp)
        # Users and groups assigned to the SaaS apps.
        sp_rows = {r['objectId']: r for r in self.rows[db.ServicePrincipal]}
        g = self.group_by_name
        for app, grp in [('Salesforce', 'App - Salesforce Users'), ('ServiceNow', 'App - ServiceNow Agents'),
                         ('Workday', 'All Staff'), ('Zoom', 'All Staff'), ('Slack', 'Engineering'),
                         ('Atlassian Cloud', 'Engineering'), ('GitHub Enterprise Cloud', 'Engineering'),
                         ('DocuSign', 'Legal'), ('Miro', 'Marketing')]:
            sp = self.saas[app]
            self._ara(sp_rows[sp]['appRoles'][0]['id'], g[grp], 'Group', sp)
            sp_rows[sp]['appRoleAssignmentRequired'] = True
        for u in self.rng.sample(self.staff, min(12, len(self.staff))):
            sp = self.pick([self.saas['Datadog'], self.saas['Miro'], self.saas['DocuSign']])
            self._ara(sp_rows[sp]['appRoles'][0]['id'], u, 'User', sp)
        self._ara(ZERO_GUID, g['Project Falcon'], 'Group', self.lob['Contoso Intranet'][1])

    def gen_oauth2_grants(self):
        expiry = NOW + datetime.timedelta(days=3650)
        # Admin consent (tenant-wide) for the LOB apps' delegated scopes and a couple of SaaS apps.
        for name, (app, sp, perms, scopes) in self.lob.items():
            if scopes:
                self.add(db.OAuth2PermissionGrant, {
                    'objectId': self.guid(), 'clientId': sp, 'consentType': 'AllPrincipals', 'principalId': None,
                    'resourceId': self.graph_sp, 'scope': ' '.join(scopes + ['openid', 'profile']),
                    'startTime': self.dt(900), 'expiryTime': expiry,
                })
        for app, scope in [('Slack', 'User.Read openid profile email offline_access'),
                           ('Zoom', 'User.Read Calendars.ReadWrite openid offline_access')]:
            self.add(db.OAuth2PermissionGrant, {
                'objectId': self.guid(), 'clientId': self.saas[app], 'consentType': 'AllPrincipals',
                'principalId': None, 'resourceId': self.graph_sp, 'scope': scope,
                'startTime': self.dt(900), 'expiryTime': expiry,
            })
        # User consents, one of them broad.
        for u in self.rng.sample(self.staff, min(6, len(self.staff))):
            self.add(db.OAuth2PermissionGrant, {
                'objectId': self.guid(), 'clientId': self.saas['Miro'], 'consentType': 'Principal',
                'principalId': u, 'resourceId': self.graph_sp, 'scope': 'User.Read openid profile offline_access',
                'startTime': self.dt(400), 'expiryTime': expiry,
            })
        self.add(db.OAuth2PermissionGrant, {
            'objectId': self.guid(), 'clientId': self.saas['Datadog'], 'consentType': 'Principal',
            'principalId': self.staff[0], 'resourceId': self.graph_sp,
            'scope': 'User.Read Mail.Read Files.ReadWrite.All offline_access',
            'startTime': self.dt(200), 'expiryTime': expiry,
        })

    # -- roles -----------------------------------------------------------------
    def _role(self, name, template):
        oid = self.guid()
        desc = f'Can manage {name.replace(" Administrator", "").lower()} settings.' if 'Admin' in name \
            else f'{name} built-in role.'
        self.add(db.DirectoryRole, {
            'objectType': 'DirectoryRole', 'objectId': oid, 'displayName': name, 'description': desc,
            'roleTemplateId': template, 'isSystem': True, 'roleDisabled': False,
            'cloudSecurityIdentifier': self._sid(False),
        })
        self.add(db.RoleDefinition, {
            'objectType': 'RoleDefinition', 'objectId': template, 'displayName': name, 'description': desc,
            'isBuiltIn': True, 'isEnabled': True, 'templateId': template, 'version': '1',
            'resourceScopes': ['/'],
            'rolePermissions': [{'allowedResourceActions': ['microsoft.directory/users/basic/read'],
                                 'condition': None}],
        })
        self.dir_roles[name] = oid

    def _assign(self, role, principal, ptype='User', eligible=False, scope='/'):
        template = ROLE_TEMPLATES.get(role) or EXTRA_ROLES[role]
        self.add(db.EligibleRoleAssignment if eligible else db.RoleAssignment, {
            'id': self.guid(), 'principalId': principal, 'roleDefinitionId': template, 'resourceScopes': [scope],
        })
        if not eligible and scope == '/':
            tbl = {'User': db.lnk_role_member_user, 'Group': db.lnk_role_member_group,
                   'ServicePrincipal': db.lnk_role_member_serviceprincipal}[ptype]
            self.link(tbl, DirectoryRole=self.dir_roles[role], **{ptype: principal})

    def gen_roles(self):
        self.dir_roles = {}
        for name, template in {**ROLE_TEMPLATES, **EXTRA_ROLES}.items():
            self._role(name, template)
        grady, irvin, henrietta, lee = self.admins
        A = self._assign
        for bg in self.breakglass:
            A('Global Administrator', bg)
        A('Global Administrator', irvin, eligible=True)
        A('Privileged Role Administrator', irvin, eligible=True)
        A('User Administrator', self.role_assignable_group, 'Group')
        A('Groups Administrator', self.role_assignable_group, 'Group')
        A('Security Administrator', grady)
        A('Conditional Access Administrator', grady, eligible=True)
        A('Intune Administrator', henrietta)
        A('Exchange Administrator', henrietta, eligible=True)
        A('Application Administrator', lee, scope='/%s' % self.lob['Contoso Customer Portal'][0])
        A('Cloud Application Administrator', lee, eligible=True)
        A('Global Reader', lee)
        A('Billing Administrator', self.staff_in('Finance')[0] if self.staff_in('Finance') else lee)
        A('Directory Synchronization Accounts', self.sync_account)
        A('Application Administrator', self.lob['Azure DevOps Deploy (prod)'][1], 'ServicePrincipal')
        for u in self.staff_in('IT', 'Seattle')[:3] + self.staff_in('IT', 'London')[:2]:
            A('Helpdesk Administrator', u)
        for u in [x for x in self.staff_in('IT') if 'Security' in (self.user_info[x]['jobTitle'] or '')][:4]:
            A('Security Reader', u)
        self.pending_au_scope = '/administrativeUnits/%s'

    def gen_aus(self):
        self.aus = []
        for name, desc, city, dynamic in [
            ('Region - Americas', 'Users and devices in the Seattle office', 'Seattle', False),
            ('Region - EMEA', 'London, Amsterdam and Paris', None, False),
            ('Region - APAC', 'Singapore office', 'Singapore', False),
            ('Executives', 'Restricted management: leadership accounts', None, False),
            ('Kiosk Devices', 'Shared retail kiosks', None, True),
        ]:
            oid = self.guid()
            self.add(db.AdministrativeUnit, {
                'objectType': 'AdministrativeUnit', 'objectId': oid, 'displayName': name, 'description': desc,
                'membershipType': 'Dynamic' if dynamic else 'Assigned',
                'membershipRule': '(device.displayName -startsWith "CTS-KIOSK")' if dynamic else None,
                'membershipRuleProcessingState': 'On' if dynamic else None,
                'isMemberManagementRestricted': name == 'Executives',
                'visibility': 'HiddenMembership' if name == 'Executives' else None,
            })
            self.aus.append(oid)
            if name == 'Region - EMEA':
                users = [u for c in ('London', 'Amsterdam', 'Paris') for u in self.staff_in(city=c)]
            elif name == 'Executives':
                users = self.staff_in('Executive Management')
            elif city:
                users = self.staff_in(city=city)
            else:
                users = []
            for u in users:
                self.link(db.lnk_au_member_user, AdministrativeUnit=oid, User=u)
            if city:
                self.link(db.lnk_au_member_group, AdministrativeUnit=oid, Group=self.group_by_name[f'Office - {city}'])
            if dynamic:
                for d in self.rows[db.Device]:
                    if d['displayName'].startswith('CTS-KIOSK'):
                        self.link(db.lnk_au_member_device, AdministrativeUnit=oid, Device=d['objectId'])
        emea_desk = self.staff_in('IT', 'London')[2:3] or self.staff_in('IT')[:1]
        for u in emea_desk:
            self._assign('User Administrator', u, eligible=True, scope='/administrativeUnits/%s' % self.aus[1])
        self._assign('Helpdesk Administrator', self.admins[0], eligible=True,
                     scope='/administrativeUnits/%s' % self.aus[3])

    # -- Conditional Access ------------------------------------------------------
    def gen_named_locations(self):
        self.named_locations = []

        def loc(name, detail):
            lid = self.guid()
            self.add(db.Policy, {
                'objectType': 'Policy', 'objectId': self.guid(), 'displayName': name, 'policyType': 6,
                'policyIdentifier': lid, 'tenantDefaultPolicy': 0, 'policyDetail': [json.dumps(detail)],
            })
            self.named_locations.append((lid, name))
            return lid

        def ips(name, cidrs, trusted=True):
            return loc(name, {'Categories': ['trusted'] if trusted else [], 'CidrIpRanges': cidrs,
                              'CompressedCidrIpRanges': gendb._compress_cidr(cidrs), 'ApplyToUnknownCountry': None})

        self.trusted_location = ips('Seattle HQ', ['203.0.113.0/26', '203.0.113.64/27'])
        ips('London office', ['198.51.100.32/28'])
        ips('Amsterdam office', ['198.51.100.96/28'])
        ips('Azure egress (prod)', ['192.0.2.0/27'])
        self.blocked_location = loc('Blocked countries', {'Categories': [],
                                                          'CountryIsoCodes': ['KP', 'IR', 'RU', 'BY', 'SY', 'CU'],
                                                          'ApplyToUnknownCountry': True})
        self.office_countries = loc('Office countries', {'Categories': ['trusted'],
                                                         'CountryIsoCodes': ['US', 'GB', 'NL', 'FR', 'SG'],
                                                         'ApplyToUnknownCountry': False})

    def gen_auth_strengths(self):
        self.add(db.Policy, {
            'objectType': 'Policy', 'objectId': self.guid(), 'displayName': 'Default Policy', 'policyType': 44,
            'policyIdentifier': None, 'tenantDefaultPolicy': 44,
            'policyDetail': [json.dumps({'LastUpdatedTimestamp': self.dt(300).isoformat() + 'Z'})],
        })
        self.add(db.Policy, {
            'objectType': 'Policy', 'objectId': AUTHSTRENGTH_CUSTOM, 'displayName': 'Contoso passwordless',
            'policyType': 44, 'policyIdentifier': None, 'tenantDefaultPolicy': None,
            'policyDetail': [json.dumps({
                'created': self.dt(300).isoformat() + 'Z', 'modified': self.dt(100).isoformat() + 'Z',
                'description': 'Windows Hello, FIDO2 or Authenticator passwordless',
                'allowedCombinations': ['WindowsHelloForBusiness', 'Fido2', 'MicrosoftAuthenticatorPSI'],
                'requirementsSatisfied': 'Mfa', 'metadata': {'version': '1.0'}, 'combinationConfigurations': [],
            })],
        })

    def gen_ca_policies(self):
        g = self.group_by_name
        bg = [{'Groups': [g['CA - Exclude Break Glass']]}]
        admin_roles = [ROLE_TEMPLATES[r] for r in ('Global Administrator', 'Privileged Role Administrator',
                                                   'User Administrator', 'Application Administrator',
                                                   'Groups Administrator', 'Helpdesk Administrator')] + \
            [EXTRA_ROLES[r] for r in ('Security Administrator', 'Exchange Administrator',
                                      'Conditional Access Administrator', 'Intune Administrator',
                                      'Cloud Application Administrator')]
        all_apps = {'Include': [{'Applications': ['All']}]}

        def policy(name, state, conditions, controls=None, session=None, extra=None):
            detail = {'State': state, 'Conditions': conditions}
            if controls is not None:
                detail['Controls'] = controls
            if session:
                detail['SessionControls'] = session
            detail.update(extra or {})
            self.add(db.Policy, {
                'objectType': 'Policy', 'objectId': self.guid(), 'displayName': name, 'policyType': 18,
                'policyIdentifier': None, 'tenantDefaultPolicy': None, 'policyDetail': [json.dumps(detail)],
            })

        policy('CA001 - All users - All apps - Require MFA', 'Enabled', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': bg + [{'Users': [self.sync_account]}]},
            'Applications': all_apps,
        }, [{'AuthStrengthIds': [AUTHSTRENGTH_MFA]}])
        policy('CA002 - All users - Block legacy authentication', 'Enabled', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': bg},
            'Applications': all_apps,
            'ClientTypes': {'Include': [{'ClientTypes': ['OtherLegacy', 'LegacyExchange']}]},
        }, [{'Control': ['Block']}])
        policy('CA003 - Admins - Require phishing-resistant MFA', 'Enabled', {
            'Users': {'Include': [{'Roles': admin_roles}], 'Exclude': bg},
            'Applications': all_apps,
        }, [{'AuthStrengthIds': [AUTHSTRENGTH_PHISHRESISTANT]}],
            session=['SignInFrequency'], extra={'SignInFrequencyType': 10, 'SignInFrequencyTimeSpan': '4:00:00'})
        policy('CA004 - All users - Block blocked countries', 'Enabled', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': bg},
            'Applications': all_apps,
            'Locations': {'Include': [{'Locations': [self.blocked_location]}]},
        }, [{'Control': ['Block']}])
        policy('CA005 - Members - Office 365 - Require compliant or hybrid joined device', 'Reporting', {
            'Users': {'Include': [{'All': ['All']}],
                      'Exclude': bg + [{'Groups': [g['All Guests'], g['Contractors']]}]},
            'Applications': {'Include': [{'Applications': ['Office365']}]},
            'DevicePlatforms': {'Include': [{'DevicePlatforms': ['Windows', 'macOS']}]},
        }, [{'Control': ['CompliantDevice', 'DomainJoinedDevice']}])
        policy('CA006 - Guests - All apps - MFA and 8h sign-in frequency', 'Enabled', {
            'Users': {'Include': [{'GuestsOrExternalUsers': {
                'GuestOrExternalUserTypes': 'internalGuest,b2bCollaborationGuest,b2bCollaborationMember',
                'ExternalTenants': {'MembershipKind': 'all'}}}]},
            'Applications': all_apps,
        }, [{'Control': ['Mfa']}], session=['SignInFrequency', 'PersistentBrowserSessionMode'],
            extra={'SignInFrequencyType': 10, 'SignInFrequencyTimeSpan': '8:00:00',
                   'PersistentBrowserSessionMode': 'Never'})
        policy('CA007 - All users - Medium or high sign-in risk - Require MFA', 'Enabled', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': bg},
            'Applications': all_apps,
            'SignInRisks': {'Include': [{'SignInRisks': ['high', 'medium']}]},
        }, [{'Control': ['Mfa']}], session=['SignInFrequency'], extra={'SignInFrequencyType': 30})
        policy('CA008 - All users - High user risk - Require password change', 'Enabled', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': bg},
            'Applications': all_apps,
            'UserRisks': {'Include': [{'UserRisks': ['high']}]},
        }, [{'Control': ['Mfa']}, {'Control': ['PasswordChange']}])
        policy('CA009 - All users - Register security info from trusted locations', 'Enabled', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': bg + [{'Groups': [g['All Guests']]}]},
            'Applications': {'Include': [{'Acrs': ['urn:user:registersecurityinfo']}]},
            'Locations': {'Include': [{'Locations': ['All']}],
                          'Exclude': [{'Locations': [self.trusted_location, self.office_countries]}]},
        }, [{'Control': ['Mfa']}])
        policy('CA010 - All users - Block device code flow', 'Enabled', {
            'Users': {'Include': [{'All': ['All']}], 'Exclude': bg},
            'Applications': all_apps,
            'AuthFlows': {'Include': [{'AuthFlowType': ['deviceCodeFlow', 'authenticationTransfer']}]},
        }, [{'Control': ['Block']}])
        policy('CA011 - Mobile - Office 365 - Require approved client app', 'Reporting', {
            'Users': {'Include': [{'Groups': [g['All Staff']]}], 'Exclude': bg},
            'Applications': {'Include': [{'Applications': ['Office365']}]},
            'DevicePlatforms': {'Include': [{'DevicePlatforms': ['iOS', 'Android']}]},
        }, [{'Control': ['ApprovedApp', 'CompliantApp']}])
        policy('CA012 - Workload identities - Block outside Azure egress', 'Enabled', {
            'Users': {'Include': [{'None': ['None']}]},
            'ServicePrincipals': {'Include': [{'ServicePrincipals': [self.lob['Contoso HR Sync'][1],
                                                                     self.lob['Identity Automation'][1]]}]},
            'Applications': all_apps,
            'Locations': {'Include': [{'Locations': ['All']}],
                          'Exclude': [{'Locations': [self.named_locations[3][0]]}]},
        }, [{'Control': ['Block']}])
        policy('CA013 - Pilot - Passwordless sign-in for IT', 'Disabled', {
            'Users': {'Include': [{'Groups': [g['CA - Pilot Passwordless']]}]},
            'Applications': all_apps,
        }, [{'AuthStrengthIds': [AUTHSTRENGTH_CUSTOM]}])
        policy('CA014 - Kiosks - Block access outside stores', 'Disabled', {
            'Users': {'Include': [{'Groups': [g['Store Managers'], g['Retail']]}]},
            'Applications': all_apps,
            'Devices': {'Include': [{'DeviceRule': 'device.displayName -startsWith "CTS-KIOSK"'}]},
            'Locations': {'Include': [{'Locations': ['All']}], 'Exclude': [{'Locations': [self.office_countries]}]},
        }, [{'Control': ['Block']}])

    # -- PIM / IG / AZ -----------------------------------------------------------
    def gen_pim(self):
        super().gen_pim()
        names = {r['objectId']: r['displayName'] for r in self.rows[db.Group]}
        for r in self.rows[db.PIMgovernanceResource]:
            if r['type'] == 'Security':
                r['displayName'] = names[r['externalId']]
        # gendb picks random eligible users: give the roles to the admin accounts instead.
        admins = iter(self.admins * 2)
        subjects = {r['PIMgovernanceRoleAssignment']: r for r in self.rows[db.lnk_pim_roleassignment_subjectuser]}
        for r in self.rows[db.PIMgovernanceRoleAssignment]:
            if r['id'] in subjects:
                r['subjectId'] = subjects[r['id']]['User'] = next(admins)

    def gen_ig(self):
        super().gen_ig()
        names = {r['objectId']: r['displayName'] for r in self.rows[db.Group]}
        self.rows[db.IGaccessPackageCatalog][0].update(displayName='Project Falcon', uniqueName='project-falcon',
                                                       description='Resources for the Falcon programme')
        self.rows[db.IGaccessPackageResource][0].update(displayName=names[self.m365_group],
                                                        description='Microsoft 365 group', resourceType='O365 Group')
        self.rows[db.IGaccessPackage][0].update(displayName='Falcon contributor', uniqueName='falcon-contributor',
                                                description='Membership of the Project Falcon team for 180 days')
        self.rows[db.IGaccessPackageAssignmentPolicy][0].update(displayName='Engineering self-service',
                                                                description='Engineers request, Lee Gu approves')
        subj = self.rows[db.IGaccessPackageSubject][0]
        info = self.user_info[subj['objectId']]
        subj.update(displayName=info['displayName'], principalName=info['userPrincipalName'])
        approver = self.staff[5]  # Lee Gu
        stage = self.rows[db.IGaccessPackageAssignmentPolicy][0]['requestApprovalSettings']['approvalStages'][0]
        stage['primaryApprovers'][0].update(displayName=self.person(approver), id=approver)

    def gen_az(self):
        super().gen_az()
        for r in self.rows[db.AZmanagementGroup]:
            r['display_name'] = 'Tenant Root Group'
        for r in self.rows[db.AZsubscription]:
            r['display_name'] = 'Contoso Production'
            r['subscription_policies'] = {'quotaId': 'EnterpriseAgreement_2014-09-01'}
        for r in self.rows[db.AZroleEligibilityScheduleInstance]:
            r['expanded_properties']['scope']['displayName'] = 'Contoso Production'
        # Put readable principals on the assignments gendb picked at random.
        g = self.group_by_name
        targets = [('User', self.admins[2]), ('Group', g['Azure - Production Contributors']),
                   ('ServicePrincipal', self.lob['Azure DevOps Deploy (prod)'][1]), ('User', self.staff_in('IT')[0])]
        links = {db.lnk_az_roleassignment_user: 'User', db.lnk_az_roleassignment_group: 'Group',
                 db.lnk_az_roleassignment_serviceprincipal: 'ServicePrincipal'}
        for r, (ptype, pid) in zip(self.rows[db.AZroleAssignment], targets):
            for tbl, col in links.items():
                for link in self.rows.get(tbl, []):
                    if link['AZroleAssignment'] == r['id']:
                        link[col] = pid
            r['principal_id'] = pid
        for r in self.rows[db.AZroleEligibilityScheduleInstance]:
            r['principal_id'] = g['Azure - Subscription Owners']
        for link in self.rows[db.lnk_az_roleassignment_eligible_group]:
            link['Group'] = g['Azure - Subscription Owners']
        for r in self.rows[db.AZresource]:
            r.update(name='stcontosoprodweu', resource_group='rg-prod-weu', tags={'env': 'prod', 'owner': 'platform'})

    def gen_compliance(self):
        pass  # no collector fills these tables on a real dump

    # -- final pass -----------------------------------------------------------------
    def build(self):
        super().build()
        # gendb's tenant row and policies use its own names; rename them.
        replace = {'Synthetic Corporation': 'Contoso Ltd', 'synthetic.example.com': self.vanity,
                   'corp.synthetic.local': 'corp.contoso.com', 'Synthetic Corp': 'Contoso Ltd'}

        def fix(v):
            if isinstance(v, str):
                for a, b in replace.items():
                    v = v.replace(a, b)
                return v
            if isinstance(v, list):
                return [fix(x) for x in v]
            if isinstance(v, dict):
                return {k: fix(x) for k, x in v.items()}
            return v

        for rows in self.rows.values():
            for r in rows:
                for k, v in r.items():
                    r[k] = fix(v)
        tenant = self.rows[db.TenantDetail][0]
        tenant.update(city='Seattle', country='United States', countryLetterCode='US', state='WA',
                      street='1 Microsoft Way', postalCode='98052', telephoneNumber='+1 206 555 0100',
                      technicalNotificationMails=[f'it-alerts@{self.vanity}'],
                      dirSyncEnabled=True, companyLastDirSyncTime=NOW - datetime.timedelta(minutes=23),
                      createdDateTime=datetime.datetime(2017, 3, 14, 10, 5))
        for d in tenant['verifiedDomains']:
            d['id'] = d['name']
        tenant['verifiedDomains'].append({'name': 'contoso-retail.com', 'capabilities': 'Email', 'default': False,
                                          'initial': False, 'type': 'Federated', 'id': 'contoso-retail.com'})
        # Denormalised display names on app role assignments.
        names = {r['objectId']: r['displayName'] for t in (db.User, db.Group, db.ServicePrincipal)
                 for r in self.rows[t]}
        for r in self.rows[db.AppRoleAssignment]:
            r['principalDisplayName'] = names.get(r['principalId'], '')
            r['resourceDisplayName'] = names.get(r['resourceId'], '')


def generate(path, users=250, seed=7):
    """Build the showcase roadrecon.db at *path*. Returns the SQLAlchemy dburl."""
    if os.path.exists(path):
        os.remove(path)
    dburl = database.parse_db_argument(path)
    engine = database.init(create=True, dburl=dburl)
    gen = MockGen(users, seed)
    gen.build()
    with engine.begin() as conn:
        for table, rows in gen.rows.items():
            if not rows:
                continue
            tbl = table.__table__ if hasattr(table, '__table__') else table
            keys = set().union(*(r.keys() for r in rows))
            conn.execute(tbl.insert(), [{k: r.get(k) for k in keys} for r in rows])
    session = database.get_session(engine)
    policyanalysis.dburl = dburl
    policyanalysis.PoliciesPlugin(session).main()
    session.close()
    return dburl


def main():
    parser = argparse.ArgumentParser(description='Generate a showcase roadrecon.db with fake data for screenshots.')
    parser.add_argument('-o', '--output', required=True, help='Output SQLite database path')
    parser.add_argument('--users', type=int, default=250, help='Number of users (default 250)')
    parser.add_argument('--seed', type=int, default=7, help='Random seed (default 7)')
    args = parser.parse_args()
    t0 = time.perf_counter()
    generate(args.output, users=args.users, seed=args.seed)
    print('Generated %s (%d users, seed %d) in %.2fs' % (args.output, args.users, args.seed,
                                                         time.perf_counter() - t0))


if __name__ == '__main__':
    main()
