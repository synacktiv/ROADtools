"""S1 users: /api/users (incl. MFA view filters), /api/users/{id}, /api/owners, and the page_users hook."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.app import create_app
from roadtools.roadrecon.api.common import mfa_summary
from roadtools.roadrecon.api.models import ObjectRef, Page, UserDetail, UserQuery, UserRow
from roadtools.roadrecon.api.routers import policies as pol
from roadtools.roadrecon.api.routers.users import page_users


def get(client, **params):
    r = client.get('/api/users', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[UserRow].model_validate(r.json())


def ids(client, **params):
    return {u.id for u in get(client, **params).items}


@pytest.fixture(scope='module')
def users(app):
    with app.state.sessionmaker() as s:
        return {u.objectId: (u, mfa_summary(u)) for u in s.scalars(select(d.User))}


def where(users, pred):
    return {oid for oid, (u, m) in users.items() if pred(u, m)}


def test_shape_paging_total(client, users):
    p = get(client, page_size=7, page=2)
    assert p.total == len(users) == 300 and len(p.items) == 7 and p.page == 2
    first = get(client, page_size=7).items
    assert not {u.id for u in first} & {u.id for u in p.items}
    row = p.items[0]
    u, m = users[row.id]
    assert row.userPrincipalName == u.userPrincipalName and row.mfa.model_dump() == m


def test_search(client, users):
    some = next(iter(users.values()))[0]
    assert some.objectId in ids(client, q=some.userPrincipalName.upper())
    assert ids(client, q=some.objectId) == {some.objectId}
    assert ids(client, q='alice') == where(users, lambda u, m: 'alice' in (u.displayName + u.userPrincipalName).lower())


@pytest.mark.parametrize('key', ['displayName', 'userPrincipalName', 'lastPasswordChangeDateTime'])
def test_sorts(client, key):
    for order in ('asc', 'desc'):
        vals = [getattr(u, key) for u in get(client, sort=key, order=order).items]
        norm = [v.lower() if key != 'lastPasswordChangeDateTime' else v for v in vals]
        assert norm == sorted(norm, reverse=order == 'desc')
    assert client.get('/api/users', params={'sort': 'nope'}).status_code == 422


def test_toggles(client, users):
    assert ids(client, userType='Guest') == where(users, lambda u, m: u.userType == 'Guest')
    assert ids(client, userType='Member') == where(users, lambda u, m: u.userType != 'Guest')
    assert ids(client, accountEnabled=False) == where(users, lambda u, m: not u.accountEnabled)
    assert ids(client, dirSyncEnabled=True) == where(users, lambda u, m: u.dirSyncEnabled)


def test_member_of_direct_and_transitive(client, db):
    gm, gg = d.lnk_group_member_user, d.lnk_group_member_group

    def nested(head):
        groups, todo = {head}, [head]
        while todo:
            for child in db.scalars(select(gg.c.childGroup).where(gg.c.Group == todo.pop())):
                if child not in groups:
                    groups.add(child)
                    todo.append(child)
        return groups
    head, groups = max(((g, nested(g)) for g in db.scalars(select(gg.c.Group))), key=lambda x: len(x[1]))
    direct = set(db.scalars(select(gm.c.User).where(gm.c.Group == head)))
    trans = set(db.scalars(select(gm.c.User).where(gm.c.Group.in_(groups))))
    assert len(groups) > 2 and direct < trans
    assert ids(client, memberOf=head) == direct
    assert ids(client, memberOf=head, transitive=True) == trans
    assert get(client, memberOf=head, transitive=True, page_size=1).total == len(trans)


@pytest.mark.parametrize('table,owned', [(d.lnk_device_owner, 'Device'), (d.lnk_group_owner_user, 'Group'),
                                         (d.lnk_application_owner_user, 'Application'),
                                         (d.lnk_serviceprincipal_owner_user, 'ServicePrincipal')])
def test_owner_of(client, db, table, owned):
    oid = db.scalar(select(table.c[owned]))
    expected = set(db.scalars(select(table.c.User).where(table.c[owned] == oid)))
    assert expected and ids(client, ownerOf=oid) == expected


def test_member_of_au(client, db):
    au = d.lnk_au_member_user
    aid = db.scalar(select(au.c.AdministrativeUnit))
    assert ids(client, memberOfAu=aid) == set(db.scalars(select(au.c.User).where(au.c.AdministrativeUnit == aid)))


MFA_KINDS = {
    'none': lambda m: not (m['methods'] or m['fido'] or m['windowsHello']),
    'app': lambda m: any(x.startswith('PhoneApp') for x in m['methods']),
    'phone': lambda m: any('Voice' in x or x == 'OneWaySms' for x in m['methods']),
    'fido': lambda m: m['fido'] > 0,
    'windowsHello': lambda m: m['windowsHello'] > 0,
}


@pytest.mark.parametrize('kind', MFA_KINDS)
def test_mfa_view(client, users, kind):
    expected = where(users, lambda u, m: MFA_KINDS[kind](m))
    assert expected and ids(client, mfa=kind) == expected


def test_per_user_mfa_and_mailbox_only(client, users):
    for state in ('Enabled', 'Enforced', 'Disabled'):
        expected = where(users, lambda u, m: (m['perUserMfa'] or 'Disabled') == state)
        assert expected and ids(client, perUserMfa=state) == expected
        assert ids(client, filter=f'perUserMfa:in:{state}') == expected
    shared = where(users, lambda u, m: u.cloudMSExchRecipientDisplayType in (0, 7, 18))
    assert shared and ids(client, excludeMailboxOnly=True) == set(users) - shared


def test_advanced_filters(client, users):
    kinds = lambda m: m['methods'] + ['Fido'] * bool(m['fido']) + ['WindowsHello'] * bool(m['windowsHello'])  # noqa: E731
    fido_or_sms = where(users, lambda u, m: {'Fido', 'OneWaySms'} & set(kinds(m)))
    assert ids(client, filter='mfaMethod:in:Fido,OneWaySms') == fido_or_sms
    assert ids(client, filter='mfaMethod:notIn:Fido,OneWaySms') == set(users) - fido_or_sms
    assert ids(client, filter='mfaMethod:empty:') == where(users, lambda u, m: not kinds(m))
    no_mfa_enabled = where(users, lambda u, m: not kinds(m) and u.accountEnabled)
    assert ids(client, filter=['hasMfa:eq:false', 'accountEnabled:eq:true']) == no_mfa_enabled
    assert ids(client, filter='hasMfa:eq:true') == where(users, lambda u, m: kinds(m))
    for key, kind in (('hasApp', 'app'), ('hasPhone', 'phone'), ('hasFido', 'fido')):
        assert ids(client, filter=f'{key}:eq:true') == where(users, lambda u, m: MFA_KINDS[kind](m))
    assert ids(client, filter='userType:in:Guest') == where(users, lambda u, m: u.userType == 'Guest')
    assert ids(client, filter='department:in:IT,HR') == where(users, lambda u, m: u.department in ('IT', 'HR'))
    assert ids(client, filter=['department:in:IT', 'userType:in:Guest'], match='any') == \
        where(users, lambda u, m: u.department == 'IT' or u.userType == 'Guest')
    assert client.get('/api/users', params={'filter': 'mfaMethod:contains:x'}).status_code == 422


def test_mfa_required(client, db, users):
    """MFA required = in scope of an enabled CA policy requiring MFA. Shown only on the MFA view, filterable."""
    required = set(db.scalars(pol.mfa_required_users(db)))
    assert required and required != set(users)  # gendb has both covered and uncovered users
    rows = get(client, excludeMailboxOnly=True).items
    view = {r.id for r in rows}
    assert rows and all(r.mfaRequired is not None for r in rows)  # populated on the MFA view
    assert {r.id for r in rows if r.mfaRequired} == required & view
    assert ids(client, excludeMailboxOnly=True, mfaRequired=True) == required & view
    assert ids(client, excludeMailboxOnly=True, mfaRequired=False) == view - required
    # The custom-strength MFA policy (resolved) puts its in-scope users into the required set.
    p = next(p for p in client.get('/api/policies').json()['items'] if p['displayName'] == 'Protect security info registration')
    custom = {u['id'] for u in client.get(f"/api/policies/{p['id']}/users").json()['items']}
    assert custom and custom <= required
    # The normal users list does not compute or carry it.
    assert all(r.mfaRequired is None for r in get(client).items)


def test_mfa_required_not_collected(odd_client):
    """No Conditional Access policies collected: no column (mfaRequired null), filter matches nobody as required."""
    rows = get(odd_client, excludeMailboxOnly=True).items
    assert rows and all(r.mfaRequired is None for r in rows)
    assert ids(odd_client, excludeMailboxOnly=True, mfaRequired=True) == set()
    assert ids(odd_client, excludeMailboxOnly=True, mfaRequired=False) == {r.id for r in rows}


def test_filter_catalogue(client):
    fields = {f['key']: f for f in client.get('/api/filters/users').json()}
    opts = lambda k: {o['value'] for o in fields[k]['options']}  # noqa: E731
    assert opts('userType') == {'Member', 'Guest'}
    assert opts('perUserMfa') == {'Enabled', 'Enforced', 'Disabled'}
    assert {'Fido', 'WindowsHello', 'OneWaySms'} <= opts('mfaMethod')
    assert 'IT' in opts('department')


def test_detail(client, db, users):
    gm = d.lnk_group_member_user
    oid = db.scalar(select(gm.c.User).where(gm.c.User.in_(select(d.lnk_device_owner.c.User))))
    r = client.get(f'/api/users/{oid}')
    assert r.status_code == 200
    u = UserDetail.model_validate(r.json())
    assert u.id == oid and u.raw['objectId'] == oid and u.mfa.model_dump() == users[oid][1]
    count = lambda t: len(db.execute(select(t).where(t.c.User == oid)).all())  # noqa: E731
    assert u.counts.memberOf == count(gm) > 0
    assert u.counts.ownedDevices == count(d.lnk_device_owner) > 0
    assert u.counts.ownedGroups == count(d.lnk_group_owner_user)
    assert u.counts.administrativeUnits == count(d.lnk_au_member_user)
    assert u.counts.appRoleAssignments == len(db.scalars(select(d.AppRoleAssignment).where(d.AppRoleAssignment.principalId == oid)).all())
    assert client.get('/api/users/nope').status_code == 404


def test_owners(client, db):
    app_id = db.scalar(select(d.lnk_application_owner_serviceprincipal.c.Application)
                       .where(d.lnk_application_owner_serviceprincipal.c.Application.in_(
                           select(d.lnk_application_owner_user.c.Application))))
    r = client.get('/api/owners', params={'ownerOf': app_id, 'sort': 'displayName'})
    p = Page[ObjectRef].model_validate(r.json())
    users_ = set(db.scalars(select(d.lnk_application_owner_user.c.User).where(d.lnk_application_owner_user.c.Application == app_id)))
    sps = set(db.scalars(select(d.lnk_application_owner_serviceprincipal.c.ServicePrincipal)
                         .where(d.lnk_application_owner_serviceprincipal.c.Application == app_id)))
    assert {(o.id, o.type) for o in p.items} == {(i, 'user') for i in users_} | {(i, 'servicePrincipal') for i in sps}
    assert p.total == len(users_) + len(sps)
    assert all(o.sub for o in p.items)  # UPN / appId
    # SP owned by another SP: the owner is childServicePrincipal.
    so = d.lnk_serviceprincipal_owner_serviceprincipal
    owned, owner = db.execute(select(so.c.ServicePrincipal, so.c.childServicePrincipal)).first()
    assert owner in {o['id'] for o in client.get('/api/owners', params={'ownerOf': owned}).json()['items']}
    assert client.get('/api/owners', params={'ownerOf': 'nope'}).json()['total'] == 0
    assert client.get('/api/owners').status_code == 422


def test_page_users_within(db, users):
    some = sorted(users)[:5]
    p = page_users(db, UserQuery(userType='Member'), within=select(d.User.objectId).where(d.User.objectId.in_(some)))
    assert {u.id for u in p.items} == {i for i in some if users[i][0].userType != 'Guest'}


def test_minimal_db(minimal_client):
    p = minimal_client.get('/api/users', params={'page_size': 1}).json()
    assert p['total'] > 0
    assert minimal_client.get(f"/api/users/{p['items'][0]['id']}").status_code == 200


@pytest.fixture(scope='module')
def odd_client(tmp_path_factory):
    """Dump quirks gendb does not produce: null userType / MFA columns, capitalised state, unknown method."""
    path = tmp_path_factory.mktemp('odd') / 'roadrecon.db'
    engine = d.init(create=True, dburl=f'sqlite:///{path}')
    with d.get_session(engine) as s:
        s.add_all([
            d.User(objectId='u1', displayName='Null type', userPrincipalName='a@x', accountEnabled=True),
            d.User(objectId='u2', displayName='Enforced', userPrincipalName='b@x', userType='Guest',
                   strongAuthenticationDetail={'methods': [{'methodType': 'HardwareOTP', 'default': True},
                                                           {'methodType': 'PhoneAppOTP'}],
                                               'requirements': [{'relyingParty': '*', 'state': 'Enforced'}]}),
        ])
        s.commit()
    engine.dispose()
    with TestClient(create_app(str(path))) as c:
        yield c


def test_dump_quirks(odd_client):
    assert ids(odd_client, userType='Member') == ids(odd_client, filter='userType:in:Member') == {'u1'}
    assert ids(odd_client, mfa='none') == {'u1'}
    assert ids(odd_client, perUserMfa='Enforced') == {'u2'} and ids(odd_client, perUserMfa='Disabled') == {'u1'}
    u2 = UserDetail.model_validate(odd_client.get('/api/users/u2').json())
    assert u2.mfa.methods == ['PhoneAppOTP'] and u2.mfa.defaultMethod is None and u2.mfa.perUserMfa == 'Enforced'
