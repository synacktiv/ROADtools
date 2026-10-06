import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gendb import generate
from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.app import create_app
from roadtools.roadrecon.api.models import SearchResult, Stats, Tenant
from roadtools.roadrecon.api.routers.meta import AAD_P1, AAD_P2, _auth_policy, _consent, _license


def get(client, url, **params):
    r = client.get(url, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def count(db, model, *where):
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_stats(client, db):
    s = Stats(**get(client, '/api/stats'))
    assert s.users == count(db, d.User) == 300
    assert s.guests == count(db, d.User, d.User.userType == 'Guest') > 0
    assert (s.groups, s.devices, s.servicePrincipals, s.applications, s.administrativeUnits) == (
        count(db, d.Group), count(db, d.Device), count(db, d.ServicePrincipal), count(db, d.Application),
        count(db, d.AdministrativeUnit))
    assert s.roles == count(db, d.RoleDefinition) > 0
    assert s.policies == count(db, d.Policy, d.Policy.policyType == 18) > 0
    assert s.namedLocations == count(db, d.Policy, d.Policy.policyType == 6) > 0


def test_tenant(client, db):
    t = Tenant(**get(client, '/api/tenant'))
    td = db.scalars(select(d.TenantDetail)).one()
    assert (t.displayName, t.tenantId, t.raw['objectId']) == (td.displayName, td.objectId, td.objectId)
    assert {x.name for x in t.domains} == {v['name'] for v in td.verifiedDomains}
    assert t.domains[0].isDefault and not t.domains[0].isInitial and t.domains[1].isInitial
    assert t.domains[0].capabilities == ['Email', 'OfficeCommunicationsOnline']
    assert (t.license, t.securityDefaults, t.seamlessSso, t.seamlessSsoDomains) == ('P1', False, True, ['corp.synthetic.local'])
    ap = t.authorizationPolicy
    assert ap.selfServicePasswordReset is True and ap.blockMsolPowerShell is False and ap.usersCanRegisterApps is True
    assert (ap.usersCanCreateTenants, ap.usersCanReadOwnBitlockerKeys) == (True, False)
    assert (ap.userConsentPolicy, ap.guestRole, ap.guestInvitesFrom) == ('all', 'limited', 'adminsAndGuestInviters')
    assert 'limited access' in ap.guestAccess
    ds = db.scalars(select(d.DirectorySetting)).all()
    assert [s.name for s in t.directorySettings] == [s.displayName for s in ds]
    values = {v.name: v for v in t.directorySettings[0].values}
    assert values['EnableGroupCreation'].value == 'true' and values['EnableGroupCreation'].ref is None
    assert values['GroupCreationAllowedGroupId'].ref.type == 'group'


def test_license_tier():
    plan = lambda pid, status: {'servicePlanId': pid, 'capabilityStatus': status}  # noqa: E731
    assert _license(None) == _license([plan(AAD_P2, 'Suspended'), plan(AAD_P1, 'Deleted')]) == 'Free'
    assert _license([plan(AAD_P1, 'Warning')]) == 'P1'
    assert _license([plan(AAD_P1, 'Enabled'), plan(AAD_P2, 'Enabled')]) == 'P2'


def test_invites_case_insensitive():
    """AAD Graph returns 'Everyone', MS Graph 'everyone'."""
    ap = _auth_policy(d.AuthorizationPolicy(allowInvitesFrom='AdminsGuestInvitersAndAllMembers'))
    assert ap.guestInvitesFrom == 'members' and not ap.guestInvites.startswith('Unknown')
    assert _auth_policy(d.AuthorizationPolicy(allowInvitesFrom='Everyone')).guestInvitesFrom == 'everyone'


def test_consent_decoding():
    assert _consent([]) == ('none', 'Do not allow user consent')
    assert _consent(['ManagePermissionGrantsForOwnedResource.microsoft-dynamically-managed-permissions-for-team'])[0] == 'none'
    assert _consent(['ManagePermissionGrantsForSelf.microsoft-user-default-low'])[0] == 'verifiedPublishers'
    assert _consent(['ManagePermissionGrantsForSelf.microsoft-user-default-legacy'])[0] == 'all'
    assert _consent(['ManagePermissionGrantsForSelf.my-policy'])[1].endswith('my-policy')


def test_search(client, db):
    user = db.scalars(select(d.User).order_by(d.User.objectId)).first()
    r = SearchResult(**get(client, '/api/search', q=user.objectId))
    assert [(g.type, g.total) for g in r.groups] == [('user', 1)]
    assert r.groups[0].items[0].id == user.objectId and r.groups[0].items[0].sub == user.userPrincipalName

    # UPN domain matches (nearly) every user: total is the real count, items capped at limit.
    domain = user.userPrincipalName.split('@')[1]
    r = SearchResult(**get(client, '/api/search', q=domain.upper(), limit=3))
    users = r.groups[0]
    expected = count(db, d.User, d.User.userPrincipalName.ilike(f'%{domain}%') | d.User.displayName.ilike(f'%{domain}%'))
    assert users.type == 'user' and users.total == expected and len(users.items) == 3

    sp = db.scalars(select(d.ServicePrincipal).where(d.ServicePrincipal.appId.isnot(None))).first()
    r = SearchResult(**get(client, '/api/search', q=sp.appId))
    g = next(g for g in r.groups if g.type == 'servicePrincipal')
    assert g.items[0].id == sp.objectId and g.items[0].sub == sp.appId

    loc = db.scalars(select(d.Policy).where(d.Policy.policyType == 6)).first()
    r = SearchResult(**get(client, '/api/search', q=loc.displayName))
    assert ('namedLocation', loc.objectId) in {(g.type, i.id) for g in r.groups for i in g.items}
    assert 'policy' not in {g.type for g in r.groups if any(i.id == loc.objectId for i in g.items)}

    role = db.scalars(select(d.RoleDefinition).where(d.RoleDefinition.displayName == 'Global Administrator')).one()
    r = SearchResult(**get(client, '/api/search', q='global admin'))
    assert next(g for g in r.groups if g.type == 'role').items[0].id == role.templateId

    # Fixed type order, only non-empty groups, LIKE wildcards escaped.
    r = SearchResult(**get(client, '/api/search', q='a'))
    order = ['user', 'group', 'device', 'servicePrincipal', 'application', 'administrativeUnit', 'role', 'policy', 'namedLocation']
    types = [g.type for g in r.groups]
    assert types == sorted(types, key=order.index) and all(g.total > 0 for g in r.groups)
    assert get(client, '/api/search', q='%_%') == {'groups': []}
    assert client.get('/api/search', params={'q': ''}).status_code == 422


def test_minimal(minimal_client):
    assert Stats(**get(minimal_client, '/api/stats')).users == 300
    assert Tenant(**get(minimal_client, '/api/tenant')).authorizationPolicy is not None
    assert SearchResult(**get(minimal_client, '/api/search', q='admin')).groups


def test_empty_tenant_tables(tmp_path):
    """Old dump: no TenantDetails row, no AuthorizationPolicys / DirectorySettings tables, no RoleDefinitions."""
    path = tmp_path / 'old.db'
    generate(str(path))
    with sqlite3.connect(path) as conn:
        conn.executescript('DELETE FROM TenantDetails; DELETE FROM RoleDefinitions; DELETE FROM Policys WHERE policyType IN (8, 10);'
                           'DROP TABLE AuthorizationPolicys; DROP TABLE DirectorySettings;')
        roles = conn.execute('SELECT count(*) FROM DirectoryRoles').fetchone()[0]
        role_name = conn.execute('SELECT displayName, roleTemplateId FROM DirectoryRoles').fetchone()
    with TestClient(create_app(str(path))) as c:
        t = Tenant(**get(c, '/api/tenant'))
        assert (t.domains, t.authorizationPolicy, t.directorySettings, t.raw) == ([], None, [], {})
        assert (t.license, t.securityDefaults, t.seamlessSso, t.seamlessSsoDomains) == (None, None, None, [])
        assert Stats(**get(c, '/api/stats')).roles == roles > 0
        g = next(g for g in SearchResult(**get(c, '/api/search', q=role_name[0])).groups if g.type == 'role')
        assert g.items[0].id == role_name[1]
