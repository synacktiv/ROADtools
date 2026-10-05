"""S4 service principals and applications."""
import base64
import json
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import exists, func, not_, or_, select, type_coerce, union
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d

from ..common import (ci, count_of, Db, F, flag, iso, is_privileged_permission, json_text, not_found, paginate, register,
                      resolve_appids, sql_clause)
from ..models import (AppRoleDefinition, ApplicationCounts, ApplicationDetail, ApplicationQuery, ApplicationRow,
                      Credential, MetadataEntry, ObjectRef, Page, PermissionScopeDefinition, RequiredPermission,
                      RequiredResourceAccess, ServicePrincipalCounts, ServicePrincipalDetail, ServicePrincipalQuery,
                      ServicePrincipalRow)
from . import governance, policies, roles
from .grants import NEGATED

router = APIRouter(prefix='/api', tags=['apps'])

SP, App = d.ServicePrincipal, d.Application
sp_owner_user, sp_owner_sp = d.lnk_serviceprincipal_owner_user, d.lnk_serviceprincipal_owner_serviceprincipal
app_owner_user, app_owner_sp = d.lnk_application_owner_user, d.lnk_application_owner_serviceprincipal


def _len(col):
    # ponytail: json_array_length is SQLite json1 (Postgres needs `CAST(col AS json)`: the JSON columns are TEXT).
    return func.coalesce(func.json_array_length(col), 0)


def _url_where(op: str, arg: str):
    """Any of reply URLs, homepage, logout URL matches; negative operators: none does."""
    pos = NEGATED.get(op, op)
    # coalesce: a NULL homepage would make the whole OR NULL, and NOT NULL drops the row.
    match = lambda col: sql_clause(F('URL', 'text', col=func.coalesce(col, '')), pos, arg)  # noqa: E731
    # ponytail: json_each is SQLite json1; Postgres needs jsonb_array_elements.
    reply = func.json_each(json_text(SP.replyUrls)).table_valued('value')
    hit = or_(select(reply.c.value).where(match(reply.c.value)).exists(), match(SP.homepage), match(SP.logoutUrl))
    return not_(hit) if op in NEGATED else hit


# Computed row fields, as SQL so they filter and sort.
sp_pw, sp_key, sp_roles, sp_scopes = (_len(c) for c in (SP.passwordCredentials, SP.keyCredentials, SP.appRoles,
                                                        SP.oauth2Permissions))
sp_owned = or_(exists().where(sp_owner_user.c.ServicePrincipal == SP.objectId),
               exists().where(sp_owner_sp.c.ServicePrincipal == SP.objectId))
app_pw, app_key, app_roles, app_scopes = (_len(c) for c in (App.passwordCredentials, App.keyCredentials, App.appRoles,
                                                            App.oauth2Permissions))
app_owned = or_(exists().where(app_owner_user.c.Application == App.objectId),
                exists().where(app_owner_sp.c.Application == App.objectId))

SP_ROW = select(SP.objectId.label('id'), func.coalesce(SP.displayName, SP.objectId).label('displayName'), SP.appId,
                SP.servicePrincipalType, SP.publisherName, SP.microsoftFirstParty, SP.accountEnabled,
                SP.appRoleAssignmentRequired, sp_pw.label('passwordCount'), sp_key.label('keyCount'),
                sp_roles.label('appRoleCount'), sp_scopes.label('oauth2PermissionCount'),
                sp_owned.label('hasCustomOwner'), SP.homepage, SP.logoutUrl,
                type_coerce(func.coalesce(json_text(SP.replyUrls), '[]'), SP.replyUrls.type).label('replyUrls'))
APP_ROW = select(App.objectId.label('id'), func.coalesce(App.displayName, App.objectId).label('displayName'), App.appId,
                 App.availableToOtherTenants, App.homepage, App.publicClient, App.oauth2AllowImplicitFlow,
                 app_pw.label('passwordCount'), app_key.label('keyCount'), app_roles.label('appRoleCount'),
                 app_scopes.label('oauth2PermissionCount'), app_owned.label('hasCustomOwner'))

SP_FIELDS = register('service-principals', {
    'displayName': F('Name', 'text', col=SP.displayName),
    'appId': F('App ID', 'text', col=SP.appId),
    'servicePrincipalType': F('Type', 'enum', col=SP.servicePrincipalType),
    'publisherName': F('Publisher', 'enum', col=SP.publisherName),
    'microsoftFirstParty': F('Microsoft app', 'bool', col=SP.microsoftFirstParty),
    'accountEnabled': F('Enabled', 'bool', col=SP.accountEnabled),
    'appRoleAssignmentRequired': F('Assignment required', 'bool', col=SP.appRoleAssignmentRequired),
    'passwordCount': F('Secrets', 'number', col=sp_pw),
    'keyCount': F('Certificates', 'number', col=sp_key),
    'appRoleCount': F('App roles', 'number', col=sp_roles),
    'oauth2PermissionCount': F('Delegated scopes', 'number', col=sp_scopes),
    'hasCustomOwner': F('Has owner', 'bool', col=sp_owned),
    'url': F('URL', 'text', where=_url_where),
})
SP_SORTS = {'displayName': ci(SP.displayName), 'publisherName': SP.publisherName, 'appId': SP.appId,
            'servicePrincipalType': SP.servicePrincipalType, 'microsoftFirstParty': SP.microsoftFirstParty,
            'accountEnabled': SP.accountEnabled, 'appRoleAssignmentRequired': SP.appRoleAssignmentRequired,
            'passwordCount': sp_pw, 'keyCount': sp_key, 'appRoleCount': sp_roles,
            'oauth2PermissionCount': sp_scopes, 'hasCustomOwner': sp_owned}

APP_FIELDS = register('applications', {
    'displayName': F('Name', 'text', col=App.displayName),
    'appId': F('App ID', 'text', col=App.appId),
    'homepage': F('Homepage', 'text', col=App.homepage),
    'availableToOtherTenants': F('Multitenant', 'bool', col=App.availableToOtherTenants),
    'publicClient': F('Public client', 'bool', col=App.publicClient),
    'oauth2AllowImplicitFlow': F('Implicit flow', 'bool', col=App.oauth2AllowImplicitFlow),
    'passwordCount': F('Secrets', 'number', col=app_pw),
    'keyCount': F('Certificates', 'number', col=app_key),
    'appRoleCount': F('App roles', 'number', col=app_roles),
    'oauth2PermissionCount': F('Delegated scopes', 'number', col=app_scopes),
    'hasCustomOwner': F('Has owner', 'bool', col=app_owned),
})
APP_SORTS = {'displayName': ci(App.displayName), 'appId': App.appId, 'homepage': App.homepage,
             'availableToOtherTenants': App.availableToOtherTenants, 'publicClient': App.publicClient,
             'oauth2AllowImplicitFlow': App.oauth2AllowImplicitFlow, 'passwordCount': app_pw, 'keyCount': app_key,
             'appRoleCount': app_roles, 'oauth2PermissionCount': app_scopes, 'hasCustomOwner': app_owned}


# --- Decoding of the JSON columns -------------------------------------------

def _secret_name(b64: str | None) -> str | None:
    """Password descriptions are stored in customKeyIdentifier, base64 of UTF-16LE (older tools: UTF-8)."""
    try:
        raw = base64.b64decode(b64 or '')
        text = raw.decode('utf-16-le' if raw[1::2] == bytes(len(raw) // 2) else 'utf-8')
    except ValueError:  # binascii.Error and UnicodeDecodeError
        return None
    return text if text and text.isprintable() else None


def _credentials(o) -> list[Credential]:
    out = []
    for kind, creds in (('password', o.passwordCredentials), ('certificate', o.keyCredentials)):
        for c in creds or []:
            name = c.get('displayName') or (_secret_name(c.get('customKeyIdentifier')) if kind == 'password' else None)
            out.append(Credential(kind=kind, keyId=c.get('keyId') or '', displayName=name,
                                  startDate=iso(c.get('startDate')), endDate=iso(c.get('endDate'))))
    return out


def _app_roles(items) -> list[AppRoleDefinition]:
    return [AppRoleDefinition(id=r.get('id') or '', value=r.get('value'),
                              displayName=r.get('displayName') or r.get('value') or '',
                              description=r.get('description'), allowedMemberTypes=r.get('allowedMemberTypes') or [],
                              isEnabled=r.get('isEnabled') is not False, isPrivileged=is_privileged_permission(r.get('value')))
            for r in items or []]


def _scopes(items) -> list[PermissionScopeDefinition]:
    return [PermissionScopeDefinition(id=p.get('id') or '', value=p.get('value') or '',
                                      type='Admin' if p.get('type') == 'Admin' else 'User',
                                      adminConsentDisplayName=p.get('adminConsentDisplayName'),
                                      adminConsentDescription=p.get('adminConsentDescription'),
                                      userConsentDisplayName=p.get('userConsentDisplayName'),
                                      userConsentDescription=p.get('userConsentDescription'),
                                      isEnabled=p.get('isEnabled') is not False,
                                      isPrivileged=is_privileged_permission(p.get('value')))
            for p in items or []]


def _metadata(o) -> list[MetadataEntry]:
    """appMetadata.data[]: base64 values, decoded to JSON if it parses, text otherwise (as the old GUI did)."""
    md = o.appMetadata if isinstance(o.appMetadata, dict) else {}
    out = []
    for m in md.get('data') or []:
        value = m.get('value')
        try:
            value = base64.b64decode(value, validate=True).decode()
            value = json.loads(value)
        except (TypeError, ValueError):
            pass
        out.append(MetadataEntry(key=m.get('key') or '', value=value))
    return out


# --- Service principals ------------------------------------------------------

@router.get('/service-principals')
def list_service_principals(q: Annotated[ServicePrincipalQuery, Query()], db: Db) -> Page[ServicePrincipalRow]:
    stmt = SP_ROW
    if q.memberOf:
        gm = d.lnk_group_member_serviceprincipal
        stmt = stmt.where(SP.objectId.in_(select(gm.c.ServicePrincipal).where(gm.c.Group == q.memberOf)))
    if q.ownerId:
        stmt = stmt.where(SP.objectId.in_(union(
            select(sp_owner_user.c.ServicePrincipal).where(sp_owner_user.c.User == q.ownerId),
            select(sp_owner_sp.c.ServicePrincipal).where(sp_owner_sp.c.childServicePrincipal == q.ownerId))))
    if q.ownerOf:
        go = d.lnk_group_owner_serviceprincipal
        stmt = stmt.where(SP.objectId.in_(union(
            select(app_owner_sp.c.ServicePrincipal).where(app_owner_sp.c.Application == q.ownerOf),
            select(sp_owner_sp.c.childServicePrincipal).where(sp_owner_sp.c.ServicePrincipal == q.ownerOf),
            select(go.c.ServicePrincipal).where(go.c.Group == q.ownerOf))))
    if q.servicePrincipalType:
        stmt = stmt.where(SP.servicePrincipalType == q.servicePrincipalType)
    if q.microsoftFirstParty is not None:
        stmt = stmt.where(flag(SP.microsoftFirstParty, q.microsoftFirstParty))
    if q.accountEnabled is not None:
        stmt = stmt.where(flag(SP.accountEnabled, q.accountEnabled))
    if q.hasCredentials is not None:
        stmt = stmt.where((sp_pw + sp_key > 0) if q.hasCredentials else (sp_pw + sp_key == 0))
    return paginate(db, stmt, q, resource='service-principals', search=[SP.displayName, SP.appId, SP.objectId],
                    sorts=SP_SORTS, build=lambda rows: [ServicePrincipalRow(**r._mapping) for r in rows])


@router.get('/service-principals/{id}')
def get_service_principal(id: str, db: Db) -> ServicePrincipalDetail:
    row = db.execute(SP_ROW.where(SP.objectId == id)).first()
    if not row:
        raise not_found('Service principal')
    sp = db.get(SP, id)
    app = db.execute(select(App.objectId, App.displayName).where(App.appId == sp.appId)).first() if sp.appId else None
    c = db.execute(select(
        count_of(sp_owner_user, sp_owner_user.c.ServicePrincipal == id) + count_of(sp_owner_sp, sp_owner_sp.c.ServicePrincipal == id),
        count_of(d.lnk_group_member_serviceprincipal, d.lnk_group_member_serviceprincipal.c.ServicePrincipal == id),
        count_of(d.AppRoleAssignment, d.AppRoleAssignment.principalId == id),
        count_of(d.AppRoleAssignment, d.AppRoleAssignment.resourceId == id),
        count_of(d.OAuth2PermissionGrant, d.OAuth2PermissionGrant.clientId == id),
        count_of(d.OAuth2PermissionGrant, d.OAuth2PermissionGrant.resourceId == id),
    )).one()
    return ServicePrincipalDetail(
        **row._mapping,
        appOwnerTenantId=sp.appOwnerTenantId,
        servicePrincipalNames=sp.servicePrincipalNames or [],
        application=app and ObjectRef(id=app[0], type='application', displayName=app[1] or sp.appId, sub=sp.appId),
        credentials=_credentials(sp),
        appRoles=_app_roles(sp.appRoles),
        oauth2Permissions=_scopes(sp.oauth2Permissions),
        metadata=_metadata(sp),
        counts=ServicePrincipalCounts(
            owners=c[0], memberOf=c[1], roles=roles.count_roles(db, id), appRoleAssignments=c[2],
            appRoleAssignedTo=c[3], oauth2GrantsAsClient=c[4], oauth2GrantsAsResource=c[5],
            policies=policies.count_affecting(db, 'servicePrincipal', id),
            azureRoles=governance.count_azure_roles(db, id)),
        raw=sp.as_dict(),
    )


# --- Applications ------------------------------------------------------------

@router.get('/applications')
def list_applications(q: Annotated[ApplicationQuery, Query()], db: Db) -> Page[ApplicationRow]:
    stmt = APP_ROW
    if q.ownerId:
        stmt = stmt.where(App.objectId.in_(union(
            select(app_owner_user.c.Application).where(app_owner_user.c.User == q.ownerId),
            select(app_owner_sp.c.Application).where(app_owner_sp.c.ServicePrincipal == q.ownerId))))
    if q.availableToOtherTenants is not None:
        stmt = stmt.where(flag(App.availableToOtherTenants, q.availableToOtherTenants))
    if q.publicClient is not None:
        stmt = stmt.where(flag(App.publicClient, q.publicClient))
    if q.hasCredentials is not None:
        stmt = stmt.where((app_pw + app_key > 0) if q.hasCredentials else (app_pw + app_key == 0))
    return paginate(db, stmt, q, resource='applications', search=[App.displayName, App.appId, App.objectId],
                    sorts=APP_SORTS, build=lambda rows: [ApplicationRow(**r._mapping) for r in rows])


def _required_access(db: Session, items) -> list[RequiredResourceAccess]:
    """requiredResourceAccess with each resource resolved by appId and each permission id to its value."""
    items = [r for r in items or [] if r.get('resourceAppId')]
    app_ids = {r['resourceAppId'] for r in items}
    refs = resolve_appids(db, app_ids)
    values: dict[str, dict] = {}  # appId -> {(type, permission id): value}
    for model in (SP, App):  # same fallback as resolve_appids: the app registration when the tenant has no SP
        todo = app_ids - values.keys()
        for app_id, approles, scopes in db.execute(select(model.appId, model.appRoles, model.oauth2Permissions)
                                                   .where(model.appId.in_(todo))):
            values[app_id] = {**{('Role', p.get('id')): p.get('value') for p in approles or []},
                              **{('Scope', p.get('id')): p.get('value') for p in scopes or []}}
    out = []
    for r in items:
        perms = []
        for a in r.get('resourceAccess') or []:
            kind = 'Role' if a.get('type') == 'Role' else 'Scope'
            value = values.get(r['resourceAppId'], {}).get((kind, a.get('id'))) or a.get('id') or ''
            perms.append(RequiredPermission(id=a.get('id') or '', value=value, type=kind,
                                            isPrivileged=is_privileged_permission(value)))
        out.append(RequiredResourceAccess(resource=refs[r['resourceAppId']], permissions=perms))
    return out


@router.get('/applications/{id}')
def get_application(id: str, db: Db) -> ApplicationDetail:
    row = db.execute(APP_ROW.where(App.objectId == id)).first()
    if not row:
        raise not_found('Application')
    app = db.get(App, id)
    sp = db.execute(select(SP.objectId, SP.displayName, SP.publisherName, SP.appOwnerTenantId, SP.accountEnabled,
                           SP.appRoleAssignmentRequired).where(SP.appId == app.appId)).first() if app.appId else None
    owners = db.scalar(select(count_of(app_owner_user, app_owner_user.c.Application == id)
                              + count_of(app_owner_sp, app_owner_sp.c.Application == id)))
    return ApplicationDetail(
        **row._mapping,
        servicePrincipal=sp and ObjectRef(id=sp.objectId, type='servicePrincipal', displayName=sp.displayName or app.appId,
                                          sub=app.appId),
        publisherName=sp and sp.publisherName,
        appOwnerTenantId=sp and sp.appOwnerTenantId,
        accountEnabled=sp and sp.accountEnabled,
        appRoleAssignmentRequired=sp and sp.appRoleAssignmentRequired,
        replyUrls=app.replyUrls or [],
        identifierUris=app.identifierUris or [],
        credentials=_credentials(app),
        appRoles=_app_roles(app.appRoles),
        oauth2Permissions=_scopes(app.oauth2Permissions),
        requiredResourceAccess=_required_access(db, app.requiredResourceAccess),
        metadata=_metadata(app),
        counts=ApplicationCounts(owners=owners, policies=policies.count_affecting(db, 'application', id)),
        raw=app.as_dict(),
    )
