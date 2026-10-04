import shutil
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.app import create_app
from roadtools.roadrecon.api.common import PRIVILEGED_ROLES, mfa_summary
from roadtools.roadrecon.api.models import Page, RoleAssignmentRow, RoleDetail, RoleRow

GA = '62e90394-69f5-4237-9190-012177145e10'
LINKS = [(d.lnk_role_member_user, 'User'), (d.lnk_role_member_serviceprincipal, 'ServicePrincipal'),
         (d.lnk_role_member_group, 'Group')]


def tally(holders, **match):
    return sum(h.count for h in holders if all(getattr(h, k) == v for k, v in match.items()))


def roles(client, **params):
    r = client.get('/api/roles', params=params)
    assert r.status_code == 200, r.text
    return Page[RoleRow](**r.json())


def assignments(client, **params):
    r = client.get('/api/role-assignments', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[RoleAssignmentRow](**r.json())


def expected(db):
    """Direct assignments as a set of (kind, role template, principal, scope), computed straight from the tables."""
    out = {('active', a.roleDefinitionId, a.principalId, a.resourceScopes[0]) for a in db.scalars(select(d.RoleAssignment))}
    out |= {('eligible', a.roleDefinitionId, a.principalId, a.resourceScopes[0])
            for a in db.scalars(select(d.EligibleRoleAssignment))}
    for t, col in LINKS:
        for tpl, member in db.execute(select(d.DirectoryRole.roleTemplateId, t.c[col])
                                      .join(d.DirectoryRole, d.DirectoryRole.objectId == t.c.DirectoryRole)):
            out.add(('active', tpl, member, '/'))
    return out


def gid(db, name):
    return db.scalar(select(d.Group.objectId).where(d.Group.displayName == name))


def descendants(db, group):
    out, todo = {group}, [group]
    while todo:
        for child in db.scalars(select(d.lnk_group_member_group.c.childGroup)
                                .where(d.lnk_group_member_group.c.Group == todo.pop())):
            if child not in out:
                out.add(child)
                todo.append(child)
    return out


def key(r):
    return r.kind, r.role.id, r.principal.id, r.scope.id


# --- /api/roles ----------------------------------------------------------------

def test_roles_shape_counts_and_paging(client, db):
    p = roles(client, page_size=500)
    rds = db.scalars(select(d.RoleDefinition)).all()
    assert p.total == len(rds) == len(p.items)
    exp = expected(db)
    for r in p.items:
        assert r.id == r.templateId
        assert r.isPrivileged == (r.id in PRIVILEGED_ROLES)
        assert r.activeCount == sum(1 for k, t, _, _ in exp if t == r.id and k == 'active')
        assert r.eligibleCount == sum(1 for k, t, _, _ in exp if t == r.id and k == 'eligible')
    ga = next(r for r in p.items if r.id == GA)
    assert ga.activeCount == 2  # RoleAssignment user + lnk SP; the lnk user duplicates the RoleAssignment
    names = sorted(r.displayName.lower() for r in rds)
    assert [r.displayName.lower() for r in roles(client, page_size=3, page=2).items] == names[3:6]


def test_roles_toggles_filters_search_sorts(client, db):
    exp = expected(db)
    held = {t for _, t, _, _ in exp}
    assert {r.id for r in roles(client, hasAssignments=True).items} == held
    assert held.isdisjoint(r.id for r in roles(client, hasAssignments=False, page_size=500).items)
    assert roles(client, isBuiltIn=False).total == 0
    assert roles(client, isBuiltIn=True).total == roles(client).total
    assert {r.id for r in roles(client, filter='activeCount:gt:0').items} == {t for k, t, _, _ in exp if k == 'active'}
    assert {r.id for r in roles(client, filter='eligibleCount:eq:1').items} == {t for k, t, _, _ in exp if k == 'eligible'}
    assert roles(client, filter='isBuiltIn:eq:false').total == 0
    assert {r.displayName for r in roles(client, filter='displayName:startsWith:global').items} == {'Global Administrator', 'Global Reader'}
    assert {r.displayName for r in roles(client, q='GLOBAL').items} == {'Global Administrator', 'Global Reader'}
    counts = [r.activeCount for r in roles(client, sort='activeCount', order='desc', page_size=500).items]
    assert counts == sorted(counts, reverse=True)
    # Stable paging on the many equal counts.
    a, b = (roles(client, sort='activeCount', order='desc', page_size=5, page=n).items for n in (1, 2))
    assert not {r.id for r in a} & {r.id for r in b}
    assert client.get('/api/roles', params={'sort': 'nope'}).status_code == 422


def test_role_detail(client, db):
    r = client.get(f'/api/roles/{GA}')
    assert r.status_code == 200
    role = RoleDetail(**r.json())
    rd = db.get(d.RoleDefinition, GA)
    assert role.displayName == rd.displayName and role.isPrivileged and role.raw['objectId'] == GA
    assert role.allowedResourceActions == rd.rolePermissions[0]['allowedResourceActions']
    mine = [x for x in expected(db) if x[1] == GA]
    types = Counter('user' if db.get(d.User, p) else 'servicePrincipal' if db.get(d.ServicePrincipal, p) else 'group'
                    for _, _, p, _ in mine)
    h = role.holders
    assert all(tally(h, principalType=t) == types[t] for t in ('user', 'group', 'servicePrincipal'))
    assert tally(h, scope='directory') == len(mine) and tally(h, scope='administrativeUnit') == tally(h, scope='application') == 0
    assert tally(h, kind='active') == role.activeCount and tally(h, kind='eligible') == role.eligibleCount
    ua = RoleDetail(**client.get('/api/roles/fe930be7-5e62-47db-91af-98c3a49a38b1').json())
    assert (tally(ua.holders, scope='administrativeUnit'), tally(ua.holders, principalType='group'), ua.eligibleCount) == (1, 1, 1)
    assert client.get('/api/roles/nope').status_code == 404


# --- /api/role-assignments -----------------------------------------------------

def test_assignments_all_shape_and_scopes(client, db):
    p = assignments(client)
    exp = expected(db)
    assert p.total == len(exp) == len(p.items) == len({r.id for r in p.items})
    scope = lambda s: None if s == '/' else s.rsplit('/', 1)[1]  # noqa: E731
    assert {key(r) for r in p.items} == {(k, t, pr, scope(s)) for k, t, pr, s in exp}
    assert all(r.via is None for r in p.items)
    types = {r.scope.type for r in p.items}
    assert types == {'keyword', 'administrativeUnit', 'application'}
    for r in p.items:
        u = db.get(d.User, r.principal.id)
        if u:
            assert r.principal.type == 'user' and r.principal.sub == u.userPrincipalName
            assert r.principalMfa.model_dump() == mfa_summary(u) and r.principalDirSync == u.dirSyncEnabled
            assert r.principalEnabled == u.accountEnabled
        else:
            assert r.principalMfa is None and r.principalDirSync is None
        if r.principal.type == 'group':
            assert r.principalEnabled is None
    p2 = assignments(client, page_size=3, page=2)
    assert p2.total == p.total and [r.id for r in p2.items] == [r.id for r in p.items[3:6]]


def test_assignments_role_scope_kind(client, db):
    exp = expected(db)
    assert {r.principal.id for r in assignments(client, roleId=GA).items} == {p for _, t, p, _ in exp if t == GA}
    au = db.scalar(select(d.AdministrativeUnit.objectId).where(d.AdministrativeUnit.displayName == 'EMEA Region'))
    p = assignments(client, scopeId=au)
    assert p.total == 1 and p.items[0].scope.id == au and p.items[0].kind == 'eligible'
    assert client.get(f'/api/administrative-units/{au}').json()['counts']['scopedRoles'] == 1
    app = db.scalar(select(d.Application.objectId).where(d.Application.displayName == 'Fleet Portal'))
    assert assignments(client, scopeId=app).items[0].scope.type == 'application'
    assert {r.kind for r in assignments(client, kind='eligible').items} == {'eligible'}
    assert assignments(client, kind='eligible').total == sum(1 for x in exp if x[0] == 'eligible')


def test_assignments_principal_transitive(client, db):
    admins = gid(db, 'IT Admins')
    group_roles = {t for _, t, p, _ in expected(db) if p == admins}
    assert {r.role.id for r in assignments(client, principalId=admins).items} == group_roles
    # A user in a group nested under IT Admins holds its roles through IT Admins.
    child = next(g for g in descendants(db, admins) if g != admins)
    user = db.scalar(select(d.lnk_group_member_user.c.User).where(d.lnk_group_member_user.c.Group == child))
    direct = assignments(client, principalId=user)
    assert all(r.via is None for r in direct.items)
    p = assignments(client, principalId=user, transitive=True)
    via = [r for r in p.items if r.via]
    assert {r.role.id for r in via} >= group_roles and {r.via.id for r in via} >= {admins}
    assert all(r.principal.id == user for r in p.items)
    assert client.get(f'/api/users/{user}').json()['counts']['roles'] == p.total
    assert client.get(f'/api/groups/{admins}').json()['counts']['roles'] == len(group_roles)
    assert assignments(client, principalId=user, transitive=True, filter='viaGroup:eq:false').total == direct.total


def test_assignments_expand_groups(client, db):
    admins = gid(db, 'IT Admins')
    ga_admin = 'fdd7a751-b60b-444a-984c-02652fe8fa1c'  # Groups Administrator, held by IT Admins only
    groups = descendants(db, admins)
    users = set(db.scalars(select(d.lnk_group_member_user.c.User).where(d.lnk_group_member_user.c.Group.in_(groups))))
    sps = set(db.scalars(select(d.lnk_group_member_serviceprincipal.c.ServicePrincipal)
                         .where(d.lnk_group_member_serviceprincipal.c.Group.in_(groups))))
    p = assignments(client, roleId=ga_admin, expandGroups=True)
    assert {r.principal.id for r in p.items} == users | sps and p.total == len(users | sps)
    assert {r.via.id for r in p.items} == {admins}
    assert assignments(client, roleId=ga_admin).items[0].principal.id == admins
    assert assignments(client, expandGroups=True, filter='principalType:eq:group').total == 0
    assert assignments(client, roleId=ga_admin, expandGroups=True, filter='viaGroup:eq:true').total == p.total


def test_assignments_filters_search_sort(client, db):
    exp = expected(db)
    p = assignments(client, filter='role:eq:Global Administrator')
    assert {r.role.id for r in p.items} == {GA}
    p = assignments(client, filter='principalType:in:servicePrincipal,group')
    assert {r.principal.type for r in p.items} == {'servicePrincipal', 'group'}
    assert {r.scope.type for r in assignments(client, filter='scopeType:eq:Administrative unit').items} == {'administrativeUnit'}
    enabled = assignments(client, filter='principalEnabled:eq:true')
    assert enabled.items and all(r.principalEnabled for r in enabled.items)
    assert assignments(client, filter='principalEnabled:eq:false').total + enabled.total == len(exp)
    assert assignments(client, filter='viaGroup:eq:true').total == 0
    assert assignments(client, filter=['kind:eq:active', 'kind:eq:eligible'], match='any').total == len(exp)
    u = db.get(d.User, next(p for _, t, p, _ in exp if t == GA and db.get(d.User, p)))
    assert {r.principal.id for r in assignments(client, q=u.userPrincipalName.upper()).items} == {u.objectId}
    assert {r.role.id for r in assignments(client, q='global admin').items} == {GA}
    names = [r.principal.displayName.lower() for r in assignments(client, sort='principal', order='desc').items]
    assert names == sorted(names, reverse=True)
    assert client.get('/api/role-assignments', params={'sort': 'nope'}).status_code == 422
    opts = {o['value'] for o in next(f for f in client.get('/api/filters/role-assignments').json() if f['key'] == 'role')['options']}
    assert 'Global Administrator' in opts


# --- Other dumps -----------------------------------------------------------------

def test_minimal_db(minimal_client):
    assert minimal_client.get('/api/roles').json()['total'] > 0
    assert minimal_client.get('/api/role-assignments', params={'expandGroups': True}).status_code == 200


@pytest.fixture
def old_dump_client(dbpath, tmp_path):
    """A dump with DirectoryRoles + lnk_role_member_* only (no unified role definitions / assignments)."""
    path = tmp_path / 'old.db'
    shutil.copy(dbpath, path)
    engine = create_engine(f'sqlite:///{path}')
    with engine.begin() as conn:
        for t in (d.RoleAssignment, d.EligibleRoleAssignment, d.RoleDefinition):
            conn.execute(delete(t))
    engine.dispose()
    with TestClient(create_app(str(path))) as c:
        yield c


def test_old_dump_fallback(old_dump_client, db):
    p = roles(old_dump_client, page_size=500)
    assert p.total == db.query(d.DirectoryRole).count() and all(r.isBuiltIn for r in p.items)
    lnk = {(tpl, m) for t, col in LINKS for tpl, m in db.execute(
        select(d.DirectoryRole.roleTemplateId, t.c[col]).join(d.DirectoryRole, d.DirectoryRole.objectId == t.c.DirectoryRole))}
    a = assignments(old_dump_client)
    assert {(r.role.id, r.principal.id) for r in a.items} == lnk and a.total == len(lnk)
    assert all(r.kind == 'active' and r.scope.type == 'keyword' for r in a.items)
    ga = RoleDetail(**old_dump_client.get(f'/api/roles/{GA}').json())
    assert ga.activeCount == tally(ga.holders, principalType='user') + tally(ga.holders, principalType='servicePrincipal') == 2
    assert ga.allowedResourceActions == []
