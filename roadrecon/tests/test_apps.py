import base64
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.models import (ApplicationDetail, ApplicationRow, Page, ServicePrincipalDetail,
                                            ServicePrincipalRow)
from roadtools.roadrecon.api.routers import apps

GRAPH_APPID = '00000003-0000-0000-c000-000000000000'


def sps(client, **params):
    r = client.get('/api/service-principals', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[ServicePrincipalRow].model_validate(r.json())


def applications(client, **params):
    r = client.get('/api/applications', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[ApplicationRow].model_validate(r.json())


def ids(page):
    return {i.id for i in page.items}


def all_sps(db):
    return db.scalars(select(d.ServicePrincipal)).all()


def links(db, table, col, **where):
    stmt = select(table.c[col])
    for k, v in where.items():
        stmt = stmt.where(table.c[k] == v)
    return set(db.scalars(stmt))


# --- Service principals list -------------------------------------------------

def test_sp_list_rows_match_db(client, db):
    page = sps(client)
    rows = {r.id: r for r in page.items}
    objs = all_sps(db)
    assert page.total == len(objs) == len(rows)
    for o in objs:
        r = rows[o.objectId]
        assert (r.displayName, r.appId, r.servicePrincipalType) == (o.displayName, o.appId, o.servicePrincipalType)
        assert r.passwordCount == len(o.passwordCredentials or [])
        assert r.keyCount == len(o.keyCredentials or [])
        assert r.appRoleCount == len(o.appRoles or [])
        assert r.oauth2PermissionCount == len(o.oauth2Permissions or [])
        assert r.hasCustomOwner == bool(o.ownerUsers or o.ownerServicePrincipals)


def test_sp_paging_and_default_sort(client, db):
    names = sorted(o.displayName for o in all_sps(db))
    p = sps(client, page_size=3, page=2)
    assert p.total == len(names) and [r.displayName for r in p.items] == names[3:6]


def test_sp_relation_filters(client, db):
    gm = d.lnk_group_member_serviceprincipal
    group = next(iter(links(db, gm, 'Group')))
    assert ids(sps(client, memberOf=group)) == links(db, gm, 'ServicePrincipal', Group=group)

    ou, osp = d.lnk_serviceprincipal_owner_user, d.lnk_serviceprincipal_owner_serviceprincipal
    user = next(iter(links(db, ou, 'User')))
    assert ids(sps(client, ownerId=user)) == links(db, ou, 'ServicePrincipal', User=user)
    owned, owner = db.execute(select(osp.c.ServicePrincipal, osp.c.childServicePrincipal)).first()
    assert ids(sps(client, ownerId=owner)) == links(db, osp, 'ServicePrincipal', childServicePrincipal=owner) | \
        links(db, ou, 'ServicePrincipal', User=owner)
    assert owned in ids(sps(client, ownerId=owner))

    # ownerOf: SPs owning an SP, an application, a group.
    assert ids(sps(client, ownerOf=owned)) == {owner}
    aosp = d.lnk_application_owner_serviceprincipal
    app = next(iter(links(db, aosp, 'Application')))
    assert ids(sps(client, ownerOf=app)) == links(db, aosp, 'ServicePrincipal', Application=app)
    gosp = d.lnk_group_owner_serviceprincipal
    group = next(iter(links(db, gosp, 'Group')))
    assert ids(sps(client, ownerOf=group)) == links(db, gosp, 'ServicePrincipal', Group=group)
    assert sps(client, ownerOf='nope').total == 0


def test_sp_toggles(client, db):
    objs = all_sps(db)
    assert ids(sps(client, servicePrincipalType='ManagedIdentity')) == \
        {o.objectId for o in objs if o.servicePrincipalType == 'ManagedIdentity'}
    for v in (True, False):
        assert ids(sps(client, microsoftFirstParty=v)) == {o.objectId for o in objs if bool(o.microsoftFirstParty) == v}
        assert ids(sps(client, accountEnabled=v)) == {o.objectId for o in objs if bool(o.accountEnabled) == v}
        assert ids(sps(client, hasCredentials=v)) == \
            {o.objectId for o in objs if bool(o.passwordCredentials or o.keyCredentials) == v}


def test_sp_advanced_filters(client, db):
    objs = all_sps(db)
    assert ids(sps(client, filter='publisherName:in:Zoom%20Inc.,Datadog%20Inc.')) == \
        {o.objectId for o in objs if o.publisherName in ('Zoom Inc.', 'Datadog Inc.')}
    owned = {o.objectId for o in objs if o.ownerUsers or o.ownerServicePrincipals}
    assert owned and ids(sps(client, filter='hasCustomOwner:eq:true')) == owned
    assert ids(sps(client, filter='hasCustomOwner:eq:false')) == {o.objectId for o in objs} - owned
    assert ids(sps(client, filter='appRoleCount:gt:1')) == {o.objectId for o in objs if len(o.appRoles or []) > 1}
    assert ids(sps(client, filter='oauth2PermissionCount:gt:0')) == {o.objectId for o in objs if o.oauth2Permissions}
    # The dashboard's "SPs with credentials" slice.
    assert ids(sps(client, filter=['passwordCount:gt:0', 'keyCount:gt:0'], match='any')) == \
        {o.objectId for o in objs if o.passwordCredentials or o.keyCredentials}
    assert client.get('/api/service-principals', params={'filter': 'nope:eq:x'}).status_code == 422


def test_sp_search(client, db):
    graph = db.scalar(select(d.ServicePrincipal).where(d.ServicePrincipal.appId == GRAPH_APPID))
    assert ids(sps(client, q=GRAPH_APPID)) == {graph.objectId}
    assert ids(sps(client, q=graph.objectId[:13])) == {graph.objectId}
    assert graph.objectId in ids(sps(client, q='graph'))


@pytest.mark.parametrize('key', list(apps.SP_SORTS))
def test_sp_sorts(client, key):
    for order in ('asc', 'desc'):
        assert sps(client, sort=key, order=order).total > 0


def test_sp_sort_values(client):
    counts = [r.passwordCount for r in sps(client, sort='passwordCount', order='desc').items]
    assert counts == sorted(counts, reverse=True) and counts[0] > 0
    assert client.get('/api/service-principals', params={'sort': 'nope'}).status_code == 422


# --- Service principal detail -----------------------------------------------

def sp_detail(client, oid):
    r = client.get(f'/api/service-principals/{oid}')
    assert r.status_code == 200, r.text
    return ServicePrincipalDetail.model_validate(r.json())


def test_sp_detail_graph(client, db):
    o = db.scalar(select(d.ServicePrincipal).where(d.ServicePrincipal.appId == GRAPH_APPID))
    s = sp_detail(client, o.objectId)
    assert s.raw['objectId'] == o.objectId and s.application is None
    assert {r.value: r.isPrivileged for r in s.appRoles}['RoleManagement.ReadWrite.Directory'] is True
    assert {r.value: r.isPrivileged for r in s.appRoles}['User.Read.All'] is False
    assert {p.value: p.type for p in s.oauth2Permissions}['Directory.AccessAsUser.All'] == 'Admin'
    ara, grant = d.AppRoleAssignment, d.OAuth2PermissionGrant
    c = s.counts
    assert c.appRoleAssignedTo == len(db.scalars(select(ara.objectId).where(ara.resourceId == o.objectId)).all()) > 0
    assert c.appRoleAssignments == len(db.scalars(select(ara.objectId).where(ara.principalId == o.objectId)).all())
    assert c.oauth2GrantsAsResource == len(db.scalars(select(grant.objectId).where(grant.resourceId == o.objectId)).all())
    assert c.oauth2GrantsAsClient == len(db.scalars(select(grant.objectId).where(grant.clientId == o.objectId)).all())


def test_sp_detail_counts_and_links(client, db):
    for o in all_sps(db):
        s = sp_detail(client, o.objectId)
        assert s.counts.owners == len(o.ownerUsers) + len(o.ownerServicePrincipals)
        assert s.counts.memberOf == len(o.memberOf)
        assert len(s.credentials) == s.passwordCount + s.keyCount
        assert [c.kind for c in s.credentials].count('certificate') == len(o.keyCredentials or [])
        app = db.scalar(select(d.Application).where(d.Application.appId == o.appId))
        assert (s.application.id if s.application else None) == (app.objectId if app else None)
        assert s.servicePrincipalNames == (o.servicePrincipalNames or [])


def test_sp_detail_404(client):
    assert client.get('/api/service-principals/nope').status_code == 404


# --- Applications ------------------------------------------------------------

def all_apps(db):
    return db.scalars(select(d.Application)).all()


def test_app_list_rows_match_db(client, db):
    page = applications(client)
    rows = {r.id: r for r in page.items}
    objs = all_apps(db)
    assert page.total == len(objs) == len(rows)
    for o in objs:
        r = rows[o.objectId]
        assert (r.displayName, r.appId, r.homepage, r.publicClient) == (o.displayName, o.appId, o.homepage, o.publicClient)
        assert (r.passwordCount, r.keyCount) == (len(o.passwordCredentials or []), len(o.keyCredentials or []))
        assert (r.appRoleCount, r.oauth2PermissionCount) == (len(o.appRoles or []), len(o.oauth2Permissions or []))
        assert r.hasCustomOwner == bool(o.ownerUsers or o.ownerServicePrincipals)
    names = sorted(o.displayName for o in objs)
    p = applications(client, page_size=2, page=2)
    assert p.total == len(objs) and [r.displayName for r in p.items] == names[2:4]


def test_app_filters(client, db):
    objs = all_apps(db)
    ou, osp = d.lnk_application_owner_user, d.lnk_application_owner_serviceprincipal
    user = next(iter(links(db, ou, 'User')))
    assert ids(applications(client, ownerId=user)) == links(db, ou, 'Application', User=user)
    sp = next(iter(links(db, osp, 'ServicePrincipal')))
    assert ids(applications(client, ownerId=sp)) == links(db, osp, 'Application', ServicePrincipal=sp)
    for v in (True, False):
        assert ids(applications(client, availableToOtherTenants=v)) == \
            {o.objectId for o in objs if bool(o.availableToOtherTenants) == v}
        assert ids(applications(client, publicClient=v)) == {o.objectId for o in objs if bool(o.publicClient) == v}
        assert ids(applications(client, hasCredentials=v)) == \
            {o.objectId for o in objs if bool(o.passwordCredentials or o.keyCredentials) == v}
    assert ids(applications(client, filter='oauth2AllowImplicitFlow:eq:true')) == \
        {o.objectId for o in objs if o.oauth2AllowImplicitFlow}
    assert ids(applications(client, filter='keyCount:eq:0')) == {o.objectId for o in objs if not o.keyCredentials}
    assert ids(applications(client, filter='oauth2PermissionCount:eq:0')) == {o.objectId for o in objs if not o.oauth2Permissions}
    assert ids(applications(client, filter=f'homepage:eq:{objs[0].homepage}')) == {o.objectId for o in objs if o.homepage == objs[0].homepage}
    assert ids(applications(client, q=objs[0].appId)) == {objs[0].objectId}


@pytest.mark.parametrize('key', list(apps.APP_SORTS))
def test_app_sorts(client, key):
    assert applications(client, sort=key, order='desc').total > 0


def test_app_detail(client, db):
    graph = db.scalar(select(d.ServicePrincipal).where(d.ServicePrincipal.appId == GRAPH_APPID))
    for o in all_apps(db):
        r = client.get(f'/api/applications/{o.objectId}')
        assert r.status_code == 200, r.text
        a = ApplicationDetail.model_validate(r.json())
        sp = db.scalar(select(d.ServicePrincipal).where(d.ServicePrincipal.appId == o.appId))
        assert a.servicePrincipal.id == sp.objectId
        assert (a.publisherName, a.appOwnerTenantId, a.accountEnabled, a.appRoleAssignmentRequired) == \
            (sp.publisherName, sp.appOwnerTenantId, sp.accountEnabled, sp.appRoleAssignmentRequired)
        assert a.counts.owners == len(o.ownerUsers) + len(o.ownerServicePrincipals)
        assert a.identifierUris == o.identifierUris and a.raw['objectId'] == o.objectId
        (rra,) = a.requiredResourceAccess
        assert rra.resource.id == graph.objectId and rra.resource.type == 'servicePrincipal'
        values = {p.type: p.value for p in rra.permissions}
        assert values == {'Scope': 'User.Read', 'Role': 'User.Read.All'}
        assert not any(p.isPrivileged for p in rra.permissions)


def test_app_detail_404(client):
    assert client.get('/api/applications/nope').status_code == 404


def test_required_access_unresolved(db):
    # Unknown resource appId and permission id: kept as ids, the resource an unknown ref.
    (r,) = apps._required_access(db, [{'resourceAppId': 'x-app', 'resourceAccess': [{'id': 'p1', 'type': 'Role'}]}])
    assert r.resource.type == 'unknown' and r.permissions[0].value == 'p1'


# --- Decoding helpers ---------------------------------------------------------

def b64(s: str, enc='utf-8') -> str:
    return base64.b64encode(s.encode(enc)).decode()


def test_metadata_decoding():
    o = SimpleNamespace(appMetadata={'version': 1, 'data': [
        {'key': 'json', 'value': b64(json.dumps({'a': 1}))},
        {'key': 'text', 'value': b64('plain text')},
        {'key': 'raw', 'value': 'not base64!'},
    ]})
    assert [(m.key, m.value) for m in apps._metadata(o)] == [('json', {'a': 1}), ('text', 'plain text'),
                                                              ('raw', 'not base64!')]
    assert apps._metadata(SimpleNamespace(appMetadata=None)) == []


def test_secret_name():
    assert apps._secret_name(b64('prod secret', 'utf-16-le')) == 'prod secret'
    assert apps._secret_name(b64('legacy')) == 'legacy'
    assert apps._secret_name(base64.b64encode(b'\x01\xff\x10').decode()) is None
    assert apps._secret_name(None) is None


# --- Minimal DB ----------------------------------------------------------------

def test_minimal_db(minimal_client):
    for route in ('/api/service-principals', '/api/applications'):
        items = minimal_client.get(route).json()['items']
        assert items
        assert minimal_client.get(f'{route}/{items[0]["id"]}').status_code == 200
