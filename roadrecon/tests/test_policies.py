"""S5 Conditional Access routes, checked against a plain-Python reading of the same gendb database."""
import base64
import json
import shutil
import sqlite3
import zlib
from collections import defaultdict

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.app import create_app
from roadtools.roadrecon.api.models import NamedLocationDetail, NamedLocationRow, Page, PolicyDetail, PolicyMatch, PolicyRow
from roadtools.roadrecon.api.routers import policies as pol

GA, PRA, USER_ADMIN = ('62e90394-69f5-4237-9190-012177145e10', 'e8611ab8-c189-46e8-94e1-60213ab1f814',
                       'fe930be7-5e62-47db-91af-98c3a49a38b1')
GRAPH_APPID = '00000003-0000-0000-c000-000000000000'


# --- Reference: who is in scope, computed in Python without the router's SQL -----------------

@pytest.fixture(scope='module')
def ref(app):
    with app.state.sessionmaker() as db:
        users = {u.objectId: u for u in db.scalars(select(d.User))}
        group_users, group_groups = defaultdict(set), defaultdict(set)
        for g, u in db.execute(select(d.lnk_group_member_user.c.Group, d.lnk_group_member_user.c.User)):
            group_users[g].add(u)
        for g, c in db.execute(select(d.lnk_group_member_group.c.Group, d.lnk_group_member_group.c.childGroup)):
            group_groups[g].add(c)

        def tusers(g, seen=None):
            seen = seen if seen is not None else set()
            if g in seen:
                return set()
            seen.add(g)
            return group_users[g].union(*(tusers(c, seen) for c in group_groups[g]))

        template = {r.objectId: r.roleTemplateId for r in db.scalars(select(d.DirectoryRole))}
        holders = defaultdict(set)
        for t, col in ((d.lnk_role_member_user, 'User'), (d.lnk_role_member_group, 'Group'),
                       (d.lnk_role_member_serviceprincipal, 'ServicePrincipal')):
            for row in db.execute(select(t)).mappings():
                holders[template[row['DirectoryRole']]].add(row[col])
        for model in (d.RoleAssignment, d.EligibleRoleAssignment):
            for ra in db.scalars(select(model)):
                if '/' in (ra.resourceScopes or []):  # AU / object scoped assignments are ignored by CA
                    holders[ra.roleDefinitionId].add(ra.principalId)

        def side(crits):
            s = set()
            for crit in crits:
                for k, v in crit.items():
                    if k == 'All':
                        s |= set(users)
                    elif k == 'Users':
                        s |= set(v)
                    elif k == 'Groups':
                        s = s.union(*(tusers(g) for g in v))
                    elif k == 'Roles':
                        for r in v:
                            for p in holders[r]:
                                s |= {p} | tusers(p)
                    elif k == 'GuestsOrExternalUsers':
                        s |= {u for u, o in users.items() if o.userType == 'Guest'}
            return s & set(users)

        out = {}
        for p in db.scalars(select(d.Policy).where(d.Policy.policyType == 18)):
            det = json.loads(p.policyDetail[0])
            u = det['Conditions'].get('Users', {})
            inc, exc = side(u.get('Include', [])), side(u.get('Exclude', []))
            out[p.displayName] = {'id': p.objectId, 'det': det, 'applies': inc - exc, 'excluded': inc & exc,
                                  'inc': inc, 'exc': exc}
        out['_users'] = users
        out['_holders'] = holders
        return out


def by_name(client, name):
    return next(p for p in client.get('/api/policies', params={'page_size': 500}).json()['items'] if p['displayName'] == name)


def matches(client, type, id):
    return {m.policy.displayName: m for m in (PolicyMatch(**x) for x in client.get(f'/api/policies/affecting/{type}/{id}').json())}


# --- /api/policies ---------------------------------------------------------------

def test_list_shape_paging_sort(client, db, ref):
    names = sorted(k for k in ref if not k.startswith('_'))
    page = Page[PolicyRow](**client.get('/api/policies').json())
    assert page.total == len(names) == db.query(d.Policy).filter(d.Policy.policyType == 18).count()
    assert [p.displayName for p in page.items] == sorted(names, key=str.lower)
    desc = client.get('/api/policies', params={'order': 'desc'}).json()['items']
    assert [p['displayName'] for p in desc] == sorted(names, key=str.lower, reverse=True)
    p3 = client.get('/api/policies', params={'page_size': 3, 'page': 3}).json()
    assert len(p3['items']) == len(names) - 6 and p3['total'] == len(names)
    states = [p['state'] for p in client.get('/api/policies', params={'sort': 'state'}).json()['items']]
    assert states == sorted(states)
    assert client.get('/api/policies', params={'sort': 'nope'}).status_code == 422


def test_list_row_values(client):
    mfa = by_name(client, 'Require MFA for all users')
    assert (mfa['state'], mfa['targetsAllUsers'], mfa['targetsAllApps'], mfa['block'], mfa['grant']) == \
        ('enabled', True, True, False, ['MFA'])
    legacy = by_name(client, 'Block legacy authentication (report only)')
    assert (legacy['state'], legacy['block'], legacy['targetsAllApps'], legacy['grant']) == ('reporting', True, False, [])
    risky = by_name(client, 'Risky guest sign-ins')
    assert risky['grant'] == ['MFA', 'Compliant device'] and risky['grantOperator'] == 'OR'
    assert risky['sessionControls'] == ['Sign-in frequency', 'Persistent browser session']
    assert by_name(client, 'Admins need phishing-resistant MFA')['grant'] == ['Phishing-resistant MFA']


@pytest.mark.parametrize('params, expected', [
    ({'state': 'reporting'}, {'Block legacy authentication (report only)'}),
    ({'block': 'true'}, {'Block legacy authentication (report only)', 'Workload identity sign-in restriction'}),
    ({'filter': 'state:eq:disabled'}, {'Admins need phishing-resistant MFA'}),
    ({'filter': 'targetsAllUsers:eq:true'}, {'Require MFA for all users', 'Block legacy authentication (report only)'}),
    ({'filter': 'sessionControls:in:Sign-in%20frequency'}, {'Risky guest sign-ins'}),
    ({'filter': ['grant:in:MFA', 'targetsAllApps:eq:false'], 'match': 'all'}, set()),
    ({'filter': ['grant:in:Compliant%20device', 'state:eq:reporting'], 'match': 'any'},
     {'Risky guest sign-ins', 'Block legacy authentication (report only)'}),
    ({'q': 'GUEST'}, {'Risky guest sign-ins'}),
])
def test_list_filters(client, params, expected):
    items = client.get('/api/policies', params=params).json()['items']
    assert {p['displayName'] for p in items} == expected


def test_policy_filter_catalogue(client):
    cat = {f['key']: f for f in client.get('/api/filters/policies').json()}
    assert {o['value'] for o in cat['grant']['options']} == {
        'MFA', 'Compliant device', 'Phishing-resistant MFA', 'Custom authentication strength',
        'Password + Microsoft Authenticator (push)'}  # resolved custom strength name
    assert {o['value'] for o in cat['state']['options']} == {'enabled', 'reporting', 'disabled'}


# --- /api/policies/{id} ------------------------------------------------------------

def detail(client, ref, name):
    return PolicyDetail(**client.get(f'/api/policies/{ref[name]["id"]}').json())


def test_detail_resolves_every_reference(client, db, ref):
    p = detail(client, ref, 'Require MFA for all users')
    users = next(c for c in p.who if c.label == 'Users')
    assert [r.displayName for r in users.include] == ['All users'] and users.include[0].type == 'keyword'
    excl = ref['Require MFA for all users']['det']['Conditions']['Users']['Exclude']
    assert {(r.type, r.id) for r in users.exclude} == {('user', excl[0]['Users'][0]), ('group', excl[1]['Groups'][0])}
    assert users.exclude[0].displayName == db.get(d.User, excl[0]['Users'][0]).displayName
    assert p.targets[0].include[0].displayName == 'All resources'
    assert [r.displayName for r in p.grantControls] == ['Multifactor authentication']
    assert p.raw['objectId'] == p.id and p.parseError is None

    roles = detail(client, ref, 'Admins need phishing-resistant MFA')
    dr = next(c for c in roles.who if c.label == 'Directory roles')
    assert [(r.type, r.id, r.displayName) for r in dr.include] == [
        ('role', GA, 'Global Administrator'), ('role', PRA, 'Privileged Role Administrator'),
        ('role', USER_ADMIN, 'User Administrator')]
    loc = next(c for c in roles.conditions if c.key == 'Locations')
    assert loc.include[0].type == 'keyword' and (loc.exclude[0].type, loc.exclude[0].displayName) == ('namedLocation', 'Corporate network')
    assert [r.displayName for r in roles.grantControls] == ['Authentication strength: Phishing-resistant MFA']
    assert roles.state == 'disabled'

    risky = detail(client, ref, 'Risky guest sign-ins')
    who = risky.who[0]
    assert [r.type for r in who.include] == ['group', 'keyword'] and who.include[1].displayName.startswith('Guests')
    assert who.exclude[0].type == 'unknown'  # deleted principal
    graph = risky.targets[0].exclude[0]
    assert (graph.type, graph.sub) == ('servicePrincipal', GRAPH_APPID)
    assert graph.id == db.scalar(select(d.ServicePrincipal.objectId).where(d.ServicePrincipal.appId == GRAPH_APPID))
    keys = {c.key: c for c in risky.conditions}
    assert [r.displayName for r in keys['SignInRisks'].include] == ['high', 'medium']
    assert keys['Locations'].include[0].type == 'namedLocation'
    assert [r.displayName for r in risky.session] == ['Sign-in frequency: every 4:00:00', 'Persistent browser session: never']

    legacy = detail(client, ref, 'Block legacy authentication (report only)')
    assert {c.key for c in legacy.conditions} == {'ClientTypes', 'DevicePlatforms'}
    assert all(r.type == 'value' for c in legacy.conditions for r in c.include + c.exclude if r.displayName != 'Any platform')
    assert legacy.targets[0].include[0].displayName == 'Office 365'

    wl = detail(client, ref, 'Workload identity sign-in restriction')
    sp = next(c for c in wl.who if c.key == 'ServicePrincipals')
    assert all(r.type == 'servicePrincipal' for r in sp.include + sp.exclude) and len(sp.include) == 2
    assert wl.counts.inScope == 0 and wl.block

    sec = detail(client, ref, 'Protect security info registration')
    assert sec.targets[0].key == 'AuthenticationContext' and sec.targets[0].include[0].type == 'value'


def test_detail_counts(client, ref):
    for name in (k for k in ref if not k.startswith('_')):
        c = client.get(f'/api/policies/{ref[name]["id"]}').json()['counts']
        assert c == {'inScope': len(ref[name]['applies']), 'excluded': len(ref[name]['excluded'])}, name


def test_detail_404(client):
    assert client.get('/api/policies/nope').status_code == 404
    assert client.get('/api/policies/nope/users').status_code == 404


def test_malformed_policy_is_flagged(dbpath, tmp_path):
    path = tmp_path / 'bad.db'
    shutil.copy(dbpath, path)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO Policys (objectId, displayName, policyType, policyDetail) VALUES "
                "('bad', 'Broken', 18, ?), ('odd', 'Odd shapes', 18, ?)",
                (json.dumps(['{not json']), json.dumps([json.dumps({'State': 'Enabled', 'Conditions': {
                    'Users': {'Include': 'All'}, 'Applications': {'Include': [{'Applications': 42}]}}})])))
    con.commit()
    con.close()
    with TestClient(create_app(str(path))) as c:
        rows = {p['displayName']: p for p in c.get('/api/policies', params={'page_size': 500}).json()['items']}
        assert rows['Broken']['parseError'] and rows['Broken']['state'] == 'disabled'
        assert rows['Odd shapes']['parseError'] is None
        bad = c.get('/api/policies/bad')
        assert bad.status_code == 200 and bad.json()['parseError'] and bad.json()['counts'] == {'inScope': 0, 'excluded': 0}
        assert c.get('/api/policies/odd').status_code == 200
        assert c.get('/api/policies/affecting/role/' + GA).status_code == 200


# --- Scope -------------------------------------------------------------------------

def test_scope_select_matches_reference(db, ref):
    for name in (k for k in ref if not k.startswith('_')):
        det = ref[name]['det']
        assert set(db.scalars(pol._scope(det))) == ref[name]['applies'], name
        assert set(db.scalars(pol._scope(det, 'excluded'))) == ref[name]['excluded'], name


def test_scope_counts_role_assignable_groups_and_eligible_roles(db, ref):
    # 'Admins need ...' targets GA, PRA, User Administrator: User Administrator is held by a role-assignable group,
    # PRA by an eligible assignment, and the AU-scoped eligible User Administrator must not count.
    applies = ref['Admins need phishing-resistant MFA']['applies']
    group = db.scalar(select(d.lnk_role_member_group.c.Group))
    members = set(db.scalars(select(d.lnk_group_member_user.c.User).where(d.lnk_group_member_user.c.Group == group)))
    eligible = db.scalar(select(d.EligibleRoleAssignment.principalId).where(d.EligibleRoleAssignment.roleDefinitionId == PRA))
    assert members and members <= applies and eligible in applies
    h = pol._holders()
    holders = set(db.execute(select(h.c.principal, h.c.kind).where(h.c.role == USER_ADMIN)))
    assert (group, 'active') in holders and not any(k == 'eligible' for _p, k in holders)  # the only one is AU-scoped


# --- /api/policies/{id}/users (needs S1 users.page_users) ---------------------------

@pytest.mark.parametrize('effect', ['applies', 'excluded'])
def test_policy_users_needs_s1(client, ref, effect):
    r = ref['Require MFA for all users']
    page = client.get(f'/api/policies/{r["id"]}/users', params={'effect': effect, 'page_size': 500}).json()
    assert page['total'] == len(r[effect]) and {u['id'] for u in page['items']} == r[effect]


def test_policy_users_filters_needs_s1(client, ref):
    r = ref['Risky guest sign-ins']
    guests = {u for u in r['applies'] if ref['_users'][u].userType == 'Guest'}
    page = client.get(f'/api/policies/{r["id"]}/users', params={'userType': 'Guest', 'page_size': 500}).json()
    assert {u['id'] for u in page['items']} == guests
    page = client.get(f'/api/policies/{r["id"]}/users', params={'page_size': 2, 'page': 2}).json()
    assert page['total'] == len(r['applies']) and len(page['items']) == 2


# --- /api/policies/affecting --------------------------------------------------------

def test_affecting_users_match_reference(client, ref):
    names = [k for k in ref if not k.startswith('_')]
    touched = set().union(*(ref[n]['exc'] for n in names), *(ref[n]['inc'] - ref[n]['applies'] for n in names))
    sample = touched | set(sorted(ref['_users'])[::15])
    for uid in sample:
        got = matches(client, 'user', uid)
        for n in names:
            want = 'excluded' if uid in ref[n]['exc'] else 'included' if uid in ref[n]['inc'] else None
            assert (got[n].effect if n in got else None) == want, (uid, n)


def test_affecting_user_reasons(client, db, ref):
    group = db.scalar(select(d.lnk_role_member_group.c.Group))  # role-assignable group holding User Administrator
    member = db.scalar(select(d.lnk_group_member_user.c.User).where(d.lnk_group_member_user.c.Group == group))
    m = matches(client, 'user', member)
    admins = m['Admins need phishing-resistant MFA']
    assert any([v.id for v in r.via] == [group, USER_ADMIN] and r.condition == 'Directory roles' and not r.eligibleOnly
               for r in admins.included)
    mfa = m['Require MFA for all users']
    assert mfa.effect == 'excluded' and mfa.included[0].via[0].displayName == 'All users'
    assert [v.id for v in mfa.excluded[0].via] == [group] and mfa.excluded[0].via[0].type == 'group'

    eligible = db.scalar(select(d.EligibleRoleAssignment.principalId).where(d.EligibleRoleAssignment.roleDefinitionId == PRA))
    r = [x for x in matches(client, 'user', eligible)['Admins need phishing-resistant MFA'].included if x.via[-1].id == PRA]
    assert r and r[0].eligibleOnly

    guest = next(u for u in ref['Risky guest sign-ins']['applies'] if ref['_users'][u].userType == 'Guest')
    risky = matches(client, 'user', guest)['Risky guest sign-ins']
    assert any(x.approximate and x.via[0].type == 'keyword' for x in risky.included)

    excl = ref['Require MFA for all users']['det']['Conditions']['Users']['Exclude'][0]['Users'][0]
    direct = matches(client, 'user', excl)['Require MFA for all users']
    assert direct.effect == 'excluded' and any(x.via == [] for x in direct.excluded)


def test_affecting_group_role_sp_app(client, db, ref):
    group = db.scalar(select(d.lnk_role_member_group.c.Group))
    m = matches(client, 'group', group)
    assert m['Require MFA for all users'].effect == 'excluded' and m['Require MFA for all users'].excluded[0].via == []
    assert [v.id for v in m['Admins need phishing-resistant MFA'].included[0].via] == [USER_ADMIN]

    m = matches(client, 'role', GA)
    assert m['Block legacy authentication (report only)'].effect == 'excluded'
    assert m['Admins need phishing-resistant MFA'].effect == 'included'
    assert set(m) == {'Block legacy authentication (report only)', 'Admins need phishing-resistant MFA'}

    sps = ref['Workload identity sign-in restriction']['det']['Conditions']['ServicePrincipals']
    inc, exc = sps['Include'][0]['ServicePrincipals'][0], sps['Exclude'][0]['ServicePrincipals'][0]
    wl = matches(client, 'servicePrincipal', inc)['Workload identity sign-in restriction']
    assert wl.effect == 'included' and wl.included[0].condition == 'Workload identities'
    assert matches(client, 'servicePrincipal', exc)['Workload identity sign-in restriction'].effect == 'excluded'

    graph = db.scalar(select(d.ServicePrincipal.objectId).where(d.ServicePrincipal.appId == GRAPH_APPID))
    m = matches(client, 'servicePrincipal', graph)
    assert m['Risky guest sign-ins'].effect == 'excluded' and m['Risky guest sign-ins'].excluded[0].condition == 'Resources'
    assert m['Require MFA for all users'].included[0].via[0].displayName == 'All resources'
    assert 'Block legacy authentication (report only)' not in m  # Office 365 bundle: not expanded

    app = db.scalar(select(d.Application.objectId))
    m = matches(client, 'application', app)
    assert m and all(x.condition == 'Resources' for p in m.values() for x in p.included)
    assert pol.count_affecting(db, 'application', app) == len(m)
    assert pol.count_affecting(db, 'role', GA) == 2


def test_affecting_unknown(client):
    assert client.get('/api/policies/affecting/user/nope').status_code == 404
    assert client.get('/api/policies/affecting/device/x').status_code == 422


# --- Named locations -------------------------------------------------------------------

def test_named_locations_list(client, db, ref):
    page = Page[NamedLocationRow](**client.get('/api/named-locations').json())
    assert page.total == db.query(d.Policy).filter(d.Policy.policyType == 6).count() == 3
    rows = {r.displayName: r for r in page.items}
    corp, blocked, nordic = rows['Corporate network'], rows['Blocked countries'], rows['Nordic countries']
    assert (corp.kind, corp.trusted, corp.ipRanges, corp.countries) == ('ip', True, ['203.0.113.0/24', '198.51.100.0/24'], [])
    assert (blocked.kind, blocked.countries, blocked.includeUnknownCountries) == ('country', ['KP', 'IR', 'RU'], True)
    assert [p.displayName for p in corp.policies] == ['Admins need phishing-resistant MFA'] and corp.policyCount == 1
    assert blocked.policies[0].id == ref['Risky guest sign-ins']['id'] and blocked.policies[0].type == 'policy'
    assert (nordic.kind, nordic.trusted, nordic.countries) == ('country', True, ['NO', 'SE', 'DK', 'FI', 'IS'])
    assert [r.displayName for r in page.items] == ['Blocked countries', 'Corporate network', 'Nordic countries']
    assert client.get('/api/named-locations', params={'order': 'desc'}).json()['items'][0]['displayName'] == 'Nordic countries'
    assert client.get('/api/named-locations', params={'sort': 'nope'}).status_code == 422


@pytest.mark.parametrize('params, expected', [
    ({'filter': 'kind:eq:country'}, {'Blocked countries', 'Nordic countries'}),
    ({'filter': 'trusted:eq:true'}, {'Corporate network', 'Nordic countries'}),
    ({'filter': 'policyCount:gt:0'}, {'Blocked countries', 'Corporate network'}),
    ({'filter': 'policyCount:eq:0'}, {'Nordic countries'}),
    ({'q': 'corp'}, {'Corporate network'}),
])
def test_named_location_filters(client, params, expected):
    assert {r['displayName'] for r in client.get('/api/named-locations', params=params).json()['items']} == expected


def test_named_location_detail(client):
    rows = {r['displayName']: r for r in client.get('/api/named-locations').json()['items']}
    corp = NamedLocationDetail(**client.get(f'/api/named-locations/{rows["Corporate network"]["id"]}').json())
    [m] = corp.policyMatches
    assert m.effect == 'excluded' and m.excluded[0].condition == 'Locations' and not m.included
    assert corp.raw['policyType'] == 6
    blocked = NamedLocationDetail(**client.get(f'/api/named-locations/{rows["Blocked countries"]["id"]}').json())
    assert blocked.policyMatches[0].effect == 'included'
    assert client.get('/api/named-locations/nope').status_code == 404


def test_old_format_location_and_trusted_keyword():
    cidr = base64.b64encode(zlib.compress(b'10.0.0.0/8')[2:-4]).decode()  # raw deflate
    p = d.Policy(objectId='o', displayName=None, policyType=6, policyDetail=[json.dumps({'KnownNetworkPolicies': {
        'NetworkId': 'net1', 'NetworkName': 'Old office', 'Categories': ['trusted'], 'CompressedCidrIpRanges': cidr}})])
    key, row = pol._location(p)
    assert (key, row['displayName'], row['ipRanges'], row['trusted']) == ('net1', 'Old office', ['10.0.0.0/8'], True)
    det = {'Conditions': {'Locations': {'Include': [{'Locations': ['All']}], 'Exclude': [{'Locations': ['AllTrusted']}]}}}
    [m] = pol._location_matches([(None, det, pol._row(p, det, None, {}))], key, True)
    assert m.effect == 'excluded' and m.excluded[0].via[0].displayName == 'All trusted locations'


# --- Old dumps ----------------------------------------------------------------------------

def test_minimal_db(minimal_client):
    page = minimal_client.get('/api/policies').json()
    assert page['total'] == 8
    pid = page['items'][0]['id']
    assert minimal_client.get(f'/api/policies/{pid}').status_code == 200
    assert minimal_client.get('/api/named-locations').json()['total'] == 3
    assert minimal_client.get('/api/policies/affecting/role/' + GA).status_code == 200


def test_eligible_only_exclusion_does_not_win():
    from roadtools.roadrecon.api.models import MatchReason, PolicyRow
    row = PolicyRow(id='p', displayName='p', state='enabled', targetsAllUsers=False, targetsAllApps=False, block=False,
                    grant=[], grantOperator='OR', requiresMfa=False, mfaApproximate=False, sessionControls=[],
                    modifiedDateTime=None, parseError=None)
    from roadtools.roadrecon.api.routers.policies import _match
    inc = [MatchReason(condition='Users', via=[], approximate=False, eligibleOnly=False)]
    elig = [MatchReason(condition='Directory roles', via=[], approximate=False, eligibleOnly=True)]
    act = [MatchReason(condition='Directory roles', via=[], approximate=False, eligibleOnly=False)]
    assert _match(row, inc, elig).effect == 'included'
    assert _match(row, inc, act).effect == 'excluded'


# --- Sign-in check (what if) -------------------------------------------------------------

def _eval(conditions, loc=None, microsoft=False, **q):
    from roadtools.roadrecon.api.models import PolicyRow, WhatIfQuery
    row = PolicyRow(id='p', displayName='p', state='enabled', targetsAllUsers=False, targetsAllApps=False, block=False,
                    grant=[], grantOperator='OR', requiresMfa=False, mfaApproximate=False, sessionControls=[],
                    modifiedDateTime=None, parseError=None)
    s = {'q': WhatIfQuery(identity='u', **q), 'matches': {'p': pol._match(row, [pol._reason('Users')], [])},
         'microsoft': microsoft, 'location': loc}
    return pol._evaluate({'Conditions': conditions}, row, s)


def test_what_if_conditions():
    plat = {'DevicePlatforms': {'Include': [{'DevicePlatforms': ['All']}], 'Exclude': [{'DevicePlatforms': ['iOS']}]}}
    assert _eval(plat, platform='ios')[0] is False
    assert _eval(plat, platform='windows') == (True, [])
    assert _eval(plat) == (None, ['Device platforms'])  # unset: an excluded platform keeps it undecided

    locs = {'Locations': {'Include': [{'Locations': ['All']}], 'Exclude': [{'Locations': ['AllTrusted']}]}}
    assert _eval(locs, loc=('k', True), location='x')[0] is False
    assert _eval(locs, location='other')[0] is True
    named = {'Locations': {'Include': [{'Locations': ['k']}]}}
    assert _eval(named, loc=('k', False), location='x')[0] is True

    action = {'Applications': {'Include': [{'Acrs': ['urn:user:registersecurityinfo']}]}}
    assert _eval(action, resource='urn:user:registersecurityinfo')[0] is True
    assert _eval(action, resource=GRAPH_APPID)[0] is False
    all_apps = {'Applications': {'Include': [{'Applications': ['All']}], 'Exclude': [{'Applications': [GRAPH_APPID]}]}}
    assert _eval(all_apps, resource='urn:user:registersecurityinfo')[0] is False  # All resources skips user actions
    assert _eval(all_apps, resource=GRAPH_APPID)[0] is False
    assert _eval(all_apps, resource='c1')[0] is False
    bundle = {'Applications': {'Include': [{'Applications': ['Office365']}]}}
    assert _eval(bundle, microsoft=True, resource=GRAPH_APPID)[0] is None
    assert _eval(bundle, resource='11111111-1111-1111-1111-111111111111')[0] is False

    legacy = {'ClientTypes': {'Include': [{'ClientTypes': ['EasSupported', 'LegacySmtp']}]}}
    assert [_eval(legacy, clientApp=c)[0] for c in ('browser', 'native', 'eas', 'other')] == [False, False, True, True]
    risk = {'SignInRisks': {'Include': [{'SignInRisks': ['high', 'medium']}]}}
    assert [_eval(risk, signInRisk=r)[0] for r in ('none', 'medium')] == [False, True]
    flows = {'AuthFlows': {'Include': [{'AuthFlowType': ['deviceCodeFlow']}]}}
    assert [_eval(flows, authFlow=f)[0] for f in ('none', 'deviceCodeFlow')] == [False, True]
    rule = {'Devices': {'Include': [{'DeviceRule': 'device.isCompliant -eq True'}]}}
    assert _eval(rule) == (None, ['Device filter'])  # filter rules are not evaluated


def test_what_if_routes(client):
    pid = next(p['id'] for p in client.get('/api/policies', params={'q': 'Require MFA for all users'}).json()['items'])

    def user(effect):
        return client.get(f'/api/policies/{pid}/users', params={'effect': effect, 'page_size': 1}).json()['items'][0]['id']
    inside, excluded = user('applies'), user('excluded')
    q = {'identity': inside, 'resource': GRAPH_APPID, 'location': 'other', 'platform': 'windows', 'clientApp': 'browser',
         'signInRisk': 'none', 'userRisk': 'none', 'authFlow': 'none'}
    r = client.get('/api/policies/what-if', params=q).json()
    assert r['requiresMfa'] and 'MFA' in r['grant'] and r['identity']['id'] == inside
    rows = {p['id']: p['whatIf'] for p in client.get('/api/policies', params=q).json()['items']}
    assert rows[pid] == {'result': 'applies', 'dependsOn': []}
    rows = client.get('/api/policies', params={**q, 'identity': excluded}).json()['items']
    assert pid not in {p['id'] for p in rows}
    # Without a check the list is unchanged and carries no whatIf.
    assert all(p['whatIf'] is None for p in client.get('/api/policies').json()['items'])


def test_what_if_minimal_db(minimal_client):
    assert minimal_client.get('/api/policies/what-if', params={'platform': 'ios'}).status_code == 200
