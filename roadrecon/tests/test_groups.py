import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, insert, select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.app import create_app
from roadtools.roadrecon.api.models import GroupDetail, GroupRow, Page

gm_user, gm_group = d.lnk_group_member_user, d.lnk_group_member_group


def get(client, **params):
    r = client.get('/api/groups', params=params)
    assert r.status_code == 200, r.text
    return Page[GroupRow](**r.json())


def ids(page):
    return {g.id for g in page.items}


def gid(db, name):
    return db.scalar(select(d.Group.objectId).where(d.Group.displayName == name))


def all_ids(db, where=None):
    stmt = select(d.Group.objectId)
    return set(db.scalars(stmt if where is None else stmt.where(where)))


def test_list_shape_paging_and_default_sort(client, db):
    p = get(client, page_size=5)
    names = sorted(db.scalars(select(d.Group.displayName)))
    assert p.total == len(names) and [g.displayName for g in p.items] == names[:5]
    p2 = get(client, page_size=5, page=2)
    assert [g.displayName for g in p2.items] == names[5:10]
    g = db.get(d.Group, p.items[0].id)
    assert p.items[0].groupTypes == (g.groupTypes or []) and p.items[0].securityEnabled == bool(g.securityEnabled)


def test_sorts(client, db):
    p = get(client, sort='displayName', order='desc', page_size=500)
    assert [g.displayName for g in p.items] == sorted((g.displayName for g in p.items), reverse=True)
    p = get(client, sort='createdDateTime', page_size=500)
    dates = [g.createdDateTime for g in p.items]
    assert dates == sorted(dates)
    assert client.get('/api/groups', params={'sort': 'nope'}).status_code == 422


def test_search(client, db):
    p = get(client, q='finance')
    assert {g.displayName for g in p.items} == {'Finance'}
    m365 = db.scalar(select(d.Group).where(d.Group.mail.isnot(None)))
    assert m365.objectId in ids(get(client, q=m365.mail.upper()))


def test_member_id_direct_and_transitive(client, db):
    user = db.scalar(select(gm_user.c.User).where(gm_user.c.Group == gid(db, 'Engineering')))
    direct = set(db.scalars(select(gm_user.c.Group).where(gm_user.c.User == user)))
    assert ids(get(client, memberId=user, page_size=500)) == direct
    # Walk the parents in Python.
    edges = db.execute(select(gm_group.c.Group, gm_group.c.childGroup)).all()
    todo, seen = set(direct), set()
    while todo:
        g = todo.pop()
        seen.add(g)
        todo |= {p for p, c in edges if c == g} - seen
    assert seen > direct  # Engineering is nested in the chain
    assert ids(get(client, memberId=user, transitive=True, page_size=500)) == seen
    # Other member types: a device and a service principal.
    dev = db.scalar(select(d.lnk_group_member_device.c.Device))
    assert ids(get(client, memberId=dev)) == {gid(db, 'Dynamic Devices')}
    sp = db.scalar(select(d.lnk_group_member_serviceprincipal.c.ServicePrincipal))
    assert gid(db, 'IT Admins') in ids(get(client, memberId=sp))


def test_member_of_direct_and_transitive(client, db):
    top = gid(db, 'All Staff')
    assert ids(get(client, memberOf=top)) == {gid(db, 'IT Admins')}
    chain = {gid(db, n) for n in ['IT Admins', 'Finance', 'Sales EMEA', 'Engineering']}
    assert ids(get(client, memberOf=top, transitive=True)) == chain
    assert get(client, memberOf=gid(db, 'Engineering'), transitive=True).total == 0


def test_owner_and_au(client, db):
    ou = d.lnk_group_owner_user
    user = db.scalar(select(ou.c.User))
    assert ids(get(client, ownerId=user)) == set(db.scalars(select(ou.c.Group).where(ou.c.User == user)))
    osp = d.lnk_group_owner_serviceprincipal
    sp = db.scalar(select(osp.c.ServicePrincipal))
    assert ids(get(client, ownerId=sp)) == set(db.scalars(select(osp.c.Group).where(osp.c.ServicePrincipal == sp)))
    au = d.lnk_au_member_group
    unit = db.scalar(select(au.c.AdministrativeUnit))
    assert ids(get(client, memberOfAu=unit)) == set(db.scalars(select(au.c.Group).where(au.c.AdministrativeUnit == unit)))


def test_toggles(client, db):
    G = d.Group
    assert ids(get(client, isAssignableToRole=True)) == all_ids(db, G.isAssignableToRole.is_(True))
    assert ids(get(client, isAssignableToRole=False, page_size=500)) == all_ids(db) - all_ids(db, G.isAssignableToRole.is_(True))
    dynamic = all_ids(db, G.membershipRule.isnot(None))
    assert dynamic and ids(get(client, dynamic=True)) == dynamic
    assert ids(get(client, dynamic=False, page_size=500)) == all_ids(db) - dynamic
    unified = {g.objectId for g in db.scalars(select(G)) if 'Unified' in (g.groupTypes or [])}
    assert unified and ids(get(client, kind='microsoft365')) == unified
    assert ids(get(client, kind='security', page_size=500)) == all_ids(db) - unified
    synced = all_ids(db, G.dirSyncEnabled.is_(True))
    assert ids(get(client, dirSyncEnabled=True)) == synced
    assert ids(get(client, dirSyncEnabled=False, page_size=500)) == all_ids(db) - synced


def test_advanced_filters(client, db):
    G = d.Group
    unified = {g.objectId for g in db.scalars(select(G)) if 'Unified' in (g.groupTypes or [])}
    assert ids(get(client, filter='kind:eq:Microsoft 365')) == unified
    assert ids(get(client, filter='kind:in:Security,Distribution', page_size=500)) == all_ids(db) - unified
    assert ids(get(client, filter='dynamic:eq:true')) == all_ids(db, G.membershipRule.isnot(None))
    assert ids(get(client, filter='isPublic:eq:true')) == all_ids(db, G.isPublic.is_(True))
    assert ids(get(client, filter='displayName:startsWith:fin')) == {gid(db, 'Finance')}
    p = get(client, filter=['displayName:startsWith:fin', 'isAssignableToRole:eq:true'], match='any')
    assert ids(p) == {gid(db, 'Finance'), gid(db, 'IT Admins')}
    assert client.get('/api/groups', params={'filter': 'nope:eq:x'}).status_code == 422
    cat = {f['key']: f for f in client.get('/api/filters/groups').json()}
    assert {o['value'] for o in cat['kind']['options']} == {'Microsoft 365', 'Distribution', 'Security'}


def test_detail(client, db):
    top = gid(db, 'All Staff')
    r = client.get(f'/api/groups/{top}')
    assert r.status_code == 200
    g = GroupDetail(**r.json())
    row = db.get(d.Group, top)
    assert g.securityIdentifier == row.cloudSecurityIdentifier and g.raw['objectId'] == top
    count = lambda t, col, val: db.scalar(select(func.count()).select_from(t).where(col == val))  # noqa: E731
    chain = [gid(db, n) for n in ['All Staff', 'IT Admins', 'Finance', 'Sales EMEA', 'Engineering']]
    nested_users = db.scalar(select(func.count(func.distinct(gm_user.c.User))).where(gm_user.c.Group.in_(chain)))
    c = g.counts
    assert c.memberUsers == count(gm_user, gm_user.c.Group, top)
    assert c.transitiveMemberUsers == nested_users > c.memberUsers
    assert (c.memberGroups, c.memberOf) == (1, 0)
    assert c.owners == count(d.lnk_group_owner_user, d.lnk_group_owner_user.c.Group, top) + 1
    assert c.administrativeUnits == count(d.lnk_au_member_group, d.lnk_au_member_group.c.Group, top)
    it = GroupDetail(**client.get(f'/api/groups/{chain[1]}').json())
    assert (it.counts.memberOf, it.counts.memberServicePrincipals, it.pimEnabled) == (1, 1, True)
    assert GroupDetail(**client.get(f'/api/groups/{gid(db, "Dynamic Devices")}').json()).counts.memberDevices == 1
    ara = db.scalar(select(d.AppRoleAssignment.principalId).where(d.AppRoleAssignment.principalType == 'Group'))
    assert client.get(f'/api/groups/{ara}').json()['counts']['appRoleAssignments'] == \
        count(d.AppRoleAssignment.__table__, d.AppRoleAssignment.principalId, ara)
    pim = set(db.scalars(select(d.lnk_pim_resource_aadgroup.c.Group)))
    assert not GroupDetail(**client.get(f'/api/groups/{(all_ids(db) - pim).pop()}').json()).pimEnabled
    assert client.get('/api/groups/nope').status_code == 404


def test_minimal_db(minimal_client):
    p = Page[GroupRow](**minimal_client.get('/api/groups').json())
    assert p.total > 0
    g = GroupDetail(**minimal_client.get(f'/api/groups/{p.items[0].id}').json())
    assert g.pimEnabled is False


@pytest.fixture(scope='module')
def cycle_client(dbpath, tmp_path_factory):
    """Copy of the test DB with Engineering -> All Staff, closing the nesting chain into a cycle."""
    path = tmp_path_factory.mktemp('cycle') / 'roadrecon.db'
    shutil.copy(dbpath, path)
    engine = create_engine(f'sqlite:///{path}')
    with engine.begin() as conn:
        name = lambda n: conn.scalar(select(d.Group.objectId).where(d.Group.displayName == n))  # noqa: E731
        conn.execute(insert(gm_group), {'Group': name('Engineering'), 'childGroup': name('All Staff')})
    engine.dispose()
    with TestClient(create_app(str(path))) as c:
        yield c


def test_membership_cycle(cycle_client, db):
    chain = [gid(db, n) for n in ['All Staff', 'IT Admins', 'Finance', 'Sales EMEA', 'Engineering']]
    for g in chain:
        assert ids(get(cycle_client, memberOf=g, transitive=True)) == set(chain) - {g}
        assert ids(get(cycle_client, memberId=g, transitive=True)) == set(chain) - {g}
    users = db.scalar(select(func.count(func.distinct(gm_user.c.User))).where(gm_user.c.Group.in_(chain)))
    detail = GroupDetail(**cycle_client.get(f'/api/groups/{chain[2]}').json())
    assert detail.counts.transitiveMemberUsers == users and detail.counts.memberOf == 1
