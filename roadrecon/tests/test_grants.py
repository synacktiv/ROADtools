import pytest
from sqlalchemy import select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.common import is_privileged_permission
from roadtools.roadrecon.api.models import AppRoleAssignmentRow, FilterField, OAuth2GrantRow, Page

ZERO = '00000000-0000-0000-0000-000000000000'
REF_TYPES = {'User': 'user', 'Group': 'group', 'ServicePrincipal': 'servicePrincipal'}


def aras(client, **params):
    r = client.get('/api/app-role-assignments', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[AppRoleAssignmentRow].model_validate(r.json())


def grants(client, **params):
    r = client.get('/api/oauth2-grants', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[OAuth2GrantRow].model_validate(r.json())


def ids(page):
    return {i.id for i in page.items}


def role_values(db):
    """assignment id -> expected role value, computed from the resource SP's appRoles."""
    sps = {s.objectId: s for s in db.scalars(select(d.ServicePrincipal))}
    out = {}
    for a in db.scalars(select(d.AppRoleAssignment)):
        role = next((r for r in sps[a.resourceId].appRoles or [] if r['id'] == a.id), {})
        out[a.objectId] = 'Default access' if a.id == ZERO else role.get('value')
    return out


def all_aras(db):
    return db.scalars(select(d.AppRoleAssignment)).all()


def all_grants(db):
    return db.scalars(select(d.OAuth2PermissionGrant)).all()


# --- App role assignments ----------------------------------------------------

def test_ara_rows_match_db(client, db):
    page = aras(client)
    rows = {r.id: r for r in page.items}
    objs = all_aras(db)
    values = role_values(db)
    assert page.total == len(objs) == len(rows) >= 3
    assert ZERO in {o.id for o in objs} and any(v != 'Default access' for v in values.values())
    for o in objs:
        r = rows[o.objectId]
        assert r.appRoleId == o.id
        assert r.principal.id == o.principalId and r.principal.type == REF_TYPES[o.principalType]
        assert r.resource.id == o.resourceId and r.resource.type == 'servicePrincipal'
        assert r.value == values[o.objectId]
        assert r.isPrivileged == (o.id != ZERO and is_privileged_permission(r.value))
        assert (r.description is None) == (o.id == ZERO)
        assert r.createdDateTime.startswith(o.creationTimestamp.isoformat()[:19])
    assert any(r.isPrivileged for r in page.items)


def test_ara_paging(client, db):
    total = len(all_aras(db))
    pages = [aras(client, page_size=2, page=p) for p in range(1, total // 2 + 2)]
    assert all(p.total == total for p in pages)
    assert sum(len(p.items) for p in pages) == total
    assert set().union(*(ids(p) for p in pages)) == {o.objectId for o in all_aras(db)}


def test_ara_relation_filters(client, db):
    objs = all_aras(db)
    for key, attr in (('principalId', 'principalId'), ('resourceId', 'resourceId')):
        for v in {getattr(o, attr) for o in objs}:
            assert ids(aras(client, **{key: v})) == {o.objectId for o in objs if getattr(o, attr) == v}
    for t in REF_TYPES:
        assert ids(aras(client, principalType=t)) == {o.objectId for o in objs if o.principalType == t}
    assert aras(client, principalId='nope').total == 0
    assert client.get('/api/app-role-assignments', params={'principalType': 'Device'}).status_code == 422


def test_ara_advanced_filters(client, db):
    objs = all_aras(db)
    values = role_values(db)
    want = lambda pred: {o.objectId for o in objs if pred(o)}  # noqa: E731
    assert ids(aras(client, filter='principalType:in:user,group')) == want(lambda o: o.principalType in ('User', 'Group'))
    assert ids(aras(client, filter='principalType:eq:servicePrincipal')) == want(lambda o: o.principalType == 'ServicePrincipal')
    name = objs[0].resourceDisplayName
    assert ids(aras(client, filter=f'resource:eq:{name}')) == want(lambda o: o.resourceDisplayName == name)
    assert ids(aras(client, filter='value:eq:Default access')) == want(lambda o: o.id == ZERO)
    assert ids(aras(client, filter='value:ne:Default access')) == want(lambda o: o.id != ZERO)
    assert ids(aras(client, filter='value:contains:read')) == want(lambda o: 'read' in values[o.objectId].lower())
    some = next(v for v in values.values() if v != 'Default access')
    assert ids(aras(client, filter=f'value:notContains:{some}')) == want(lambda o: some.lower() not in values[o.objectId].lower())
    assert ids(aras(client, filter=f'value:in:{some},Default%20access')) == want(lambda o: values[o.objectId] in (some, 'Default access'))
    assert aras(client, filter='value:empty:').total == 0
    cut = sorted(o.creationTimestamp.date() for o in objs)[len(objs) // 2]  # the UI sends YYYY-MM-DD
    assert ids(aras(client, filter=f'createdDateTime:lt:{cut}')) == want(lambda o: o.creationTimestamp.date() < cut)
    assert aras(client, filter='createdDateTime:gt:1999-12-31T00:00:00Z').total == len(objs)
    both = aras(client, filter=['principalType:eq:group', 'value:eq:Default access'], match='any')
    assert ids(both) == want(lambda o: o.principalType == 'Group' or o.id == ZERO)


def test_ara_search(client, db):
    objs = all_aras(db)
    values = role_values(db)
    some = next(v for v in values.values() if v != 'Default access')
    assert ids(aras(client, q=some.lower())) == {o.objectId for o in objs if some.lower() in values[o.objectId].lower()
                                                 or some.lower() in (o.principalDisplayName or '').lower()
                                                 or some.lower() in (o.resourceDisplayName or '').lower()}
    name = objs[0].principalDisplayName
    assert objs[0].objectId in ids(aras(client, q=name.upper()))
    assert aras(client, q='zzz-nothing').total == 0


@pytest.mark.parametrize('key,attr', [('principal', 'principalDisplayName'), ('resource', 'resourceDisplayName'),
                                      ('createdDateTime', 'creationTimestamp')])
def test_ara_sorts(client, db, key, attr):
    expected = [getattr(o, attr) for o in all_aras(db)]
    by_id = {o.objectId: getattr(o, attr) for o in all_aras(db)}
    for order in ('asc', 'desc'):
        got = [by_id[r.id] for r in aras(client, sort=key, order=order).items]
        assert got == sorted(expected, reverse=order == 'desc')


def test_ara_bad_sort_and_filter(client):
    assert client.get('/api/app-role-assignments', params={'sort': 'value'}).status_code == 422
    assert client.get('/api/app-role-assignments', params={'filter': 'nope:eq:x'}).status_code == 422


def test_ara_catalog(client, db):
    r = client.get('/api/filters/app-role-assignments')
    assert r.status_code == 200
    fields = {f.key: f for f in map(FilterField.model_validate, r.json())}
    assert list(fields) == ['principalType', 'resource', 'value', 'createdDateTime']
    assert {o.value for o in fields['principalType'].options} == set(REF_TYPES.values())
    assert {o.value for o in fields['resource'].options} == {o.resourceDisplayName for o in all_aras(db)}


# --- OAuth2 grants -----------------------------------------------------------

def test_grant_rows_match_db(client, db):
    page = grants(client)
    rows = {r.id: r for r in page.items}
    objs = all_grants(db)
    assert page.total == len(objs) == len(rows) >= 2
    assert {o.consentType for o in objs} == {'AllPrincipals', 'Principal'}
    for o in objs:
        r = rows[o.objectId]
        assert r.consentType == o.consentType
        assert r.scopes == o.scope.split()
        assert r.privilegedScopes == [s for s in r.scopes if is_privileged_permission(s)]
        assert (r.client.id, r.client.type) == (o.clientId, 'servicePrincipal')
        assert (r.resource.id, r.resource.type) == (o.resourceId, 'servicePrincipal')
        if o.principalId:
            assert (r.principal.id, r.principal.type) == (o.principalId, 'user')
        else:
            assert r.principal is None
        assert r.expiryTime.startswith(o.expiryTime.isoformat()[:19])
    assert any(r.privilegedScopes for r in page.items)


def test_grant_paging(client, db):
    total = len(all_grants(db))
    first, second = grants(client, page_size=1, page=1), grants(client, page_size=1, page=2)
    assert first.total == second.total == total
    assert len(first.items) == len(second.items) == 1 and ids(first) != ids(second)


def test_grant_relation_filters(client, db):
    objs = all_grants(db)
    for key in ('clientId', 'resourceId', 'principalId', 'consentType'):
        for v in {getattr(o, key) for o in objs} - {None}:
            assert ids(grants(client, **{key: v})) == {o.objectId for o in objs if getattr(o, key) == v}
    assert grants(client, clientId='nope').total == 0


def test_grant_advanced_filters(client, db):
    objs = all_grants(db)
    sp_name = {s.objectId: s.displayName for s in db.scalars(select(d.ServicePrincipal))}
    want = lambda pred: {o.objectId for o in objs if pred(o)}  # noqa: E731
    words = lambda o: o.scope.split()  # noqa: E731
    assert ids(grants(client, filter='consentType:eq:AllPrincipals')) == want(lambda o: o.consentType == 'AllPrincipals')
    name = sp_name[objs[0].clientId]
    assert ids(grants(client, filter=f'client:eq:{name}')) == want(lambda o: sp_name[o.clientId] == name)
    assert ids(grants(client, filter='resource:in:Microsoft%20Graph')) == want(lambda o: sp_name[o.resourceId] == 'Microsoft Graph')
    assert ids(grants(client, filter='scope:eq:openid')) == want(lambda o: 'openid' in words(o))
    assert ids(grants(client, filter='scope:ne:openid')) == want(lambda o: 'openid' not in words(o))
    assert ids(grants(client, filter='scope:in:Mail.Read,openid')) == want(lambda o: {'Mail.Read', 'openid'} & set(words(o)))
    assert ids(grants(client, filter='scope:notIn:Mail.Read')) == want(lambda o: 'Mail.Read' not in words(o))
    assert grants(client, filter='scope:eq:Mail').total == 0  # whole words only
    assert ids(grants(client, filter='scope:contains:Mail')) == want(lambda o: 'mail' in o.scope.lower())
    assert grants(client, filter='scope:notEmpty:').total == len(objs)
    assert client.get('/api/oauth2-grants', params={'filter': 'scope:gt:a'}).status_code == 422
    assert grants(client, filter='expiryTime:gt:2000-01-01T00:00:00Z').total == len(objs)
    assert grants(client, filter='expiryTime:lt:2000-01-01').total == 0


def test_grant_search(client, db):
    objs = all_grants(db)
    user = db.get(d.User, next(o.principalId for o in objs if o.principalId))
    assert ids(grants(client, q=user.displayName)) == {o.objectId for o in objs if o.principalId == user.objectId}
    assert ids(grants(client, q=user.userPrincipalName.upper())) == {o.objectId for o in objs if o.principalId == user.objectId}
    assert ids(grants(client, q='offline_access')) == {o.objectId for o in objs if 'offline_access' in o.scope}
    assert grants(client, q='microsoft graph').total == len(objs)
    assert grants(client, q='zzz-nothing').total == 0


@pytest.mark.parametrize('key,attr', [('client', 'clientId'), ('resource', 'resourceId')])
def test_grant_sorts(client, db, key, attr):
    sp_name = {s.objectId: s.displayName for s in db.scalars(select(d.ServicePrincipal))}
    for order in ('asc', 'desc'):
        page = grants(client, sort=key, order=order)
        got = [getattr(r, key).displayName for r in page.items]
        assert got == sorted((sp_name[getattr(o, attr)] for o in all_grants(db)), reverse=order == 'desc')
    assert client.get('/api/oauth2-grants', params={'sort': 'scope'}).status_code == 422


def test_grant_catalog(client, db):
    fields = {f.key: f for f in map(FilterField.model_validate, client.get('/api/filters/oauth2-grants').json())}
    assert list(fields) == ['consentType', 'client', 'resource', 'scope', 'expiryTime']
    assert {o.value for o in fields['scope'].options} == {s for o in all_grants(db) for s in o.scope.split()}
    assert {o.label for o in fields['consentType'].options} == {'All users', 'One user'}
    sp_name = {s.objectId: s.displayName for s in db.scalars(select(d.ServicePrincipal))}
    assert {o.value for o in fields['client'].options} == {sp_name[o.clientId] for o in all_grants(db)}


def test_minimal_db(minimal_client):
    for route in ('/api/app-role-assignments', '/api/oauth2-grants'):
        r = minimal_client.get(route, params={'q': 'a', 'filter': 'expiryTime:notEmpty:' if 'oauth2' in route else 'value:notEmpty:'})
        assert r.status_code == 200, r.text
