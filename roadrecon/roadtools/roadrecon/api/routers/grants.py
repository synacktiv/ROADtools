"""S7 app role assignments and OAuth2 permission grants."""
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Text, case, func, literal, not_, or_, select, true, tuple_, type_coerce
from sqlalchemy.orm import aliased

from roadtools.roadlib.metadef import database as d

from ..common import Db, F, iso, is_privileged_permission, json_text, paginate, register, resolve_refs, sql_clause
from ..models import AppRoleAssignmentQuery, AppRoleAssignmentRow, OAuth2GrantQuery, OAuth2GrantRow, Page

router = APIRouter(prefix='/api', tags=['grants'])

ARA, G, SP = d.AppRoleAssignment, d.OAuth2PermissionGrant, d.ServicePrincipal
Client, Resource = aliased(SP), aliased(SP)
DEFAULT_ACCESS = '00000000-0000-0000-0000-000000000000'
# Negative operators are evaluated as NOT(positive) on the multi-valued / JSON-backed fields.
NEGATED = {'ne': 'eq', 'notContains': 'contains', 'notIn': 'in', 'empty': 'notEmpty'}


def _contains(col, arg: str):
    return sql_clause(F('', 'text', col=col), 'contains', arg)


def _role_value_where(op: str, arg: str):
    """The role value lives in the resource SP's appRoles JSON: match ARA (resourceId, id) against the
    (SP, role id) pairs whose value matches, one non-correlated subquery (each SP's appRoles parsed once)."""
    pos = NEGATED.get(op, op)
    if pos == 'notEmpty':
        hit = true()  # the value always falls back to something
    else:
        match = lambda col: sql_clause(F('Role', 'text', col=col), pos, arg)  # noqa: E731
        # ponytail: json_each / json_extract are SQLite json1; Postgres needs jsonb_array_elements.
        role = func.json_each(json_text(SP.appRoles)).table_valued('value')
        pairs = (select(SP.objectId, func.json_extract(role.c.value, '$.id')).select_from(SP).join(role, true())
                 .where(SP.objectId.in_(select(ARA.resourceId)), match(func.json_extract(role.c.value, '$.value'))))
        hit = or_((ARA.id == DEFAULT_ACCESS) & match(literal('Default access')),
                  tuple_(ARA.resourceId, ARA.id).in_(pairs))
    return not_(hit) if op in NEGATED else hit


def _scope_where(op: str, arg: str):
    """`scope` is a space-separated string: eq / in match whole words, contains a substring."""
    pos = NEGATED.get(op, op)
    scope = func.coalesce(G.scope, '')
    if pos == 'notEmpty':
        hit = func.trim(scope) != ''
    elif pos == 'contains':
        hit = _contains(scope, arg)
    elif pos in ('eq', 'in'):
        words = [unquote(s) for s in arg.split(',')] if pos == 'in' else [arg]
        padded = literal(' ') + scope + ' '
        hit = or_(*(_contains(padded, f' {w} ') for w in words))
    else:
        raise HTTPException(422, f'Operator {op} does not apply to Scope')
    return not_(hit) if op in NEGATED else hit


def _sp_names(col):
    """Enum options: display names of the service principals `col` points to."""
    return lambda db: db.scalars(select(SP.displayName).where(SP.objectId.in_(select(col))).distinct())


def _scopes(db):
    return {s for scope in db.scalars(select(G.scope).distinct()) for s in (scope or '').split()}


APP_ROLE_FIELDS = register('app-role-assignments', {
    'principalType': F('Principal type', 'enum', labels={'user': 'User', 'group': 'Group', 'servicePrincipal': 'Service principal'},
                       col=case({'User': 'user', 'Group': 'group', 'ServicePrincipal': 'servicePrincipal'}, value=ARA.principalType)),
    'resource': F('Application', 'enum', col=ARA.resourceDisplayName),
    'value': F('Role', 'text', where=_role_value_where),
    'createdDateTime': F('Assigned', 'date', col=ARA.creationTimestamp),
})
APP_ROLE_SORTS = {'principal': ARA.principalDisplayName, 'resource': ARA.resourceDisplayName,
                  'createdDateTime': ARA.creationTimestamp}

GRANT_FIELDS = register('oauth2-grants', {
    'consentType': F('Consent', 'enum', labels={'AllPrincipals': 'All users', 'Principal': 'One user'}, col=G.consentType),
    'client': F('Granted to', 'enum', col=Client.displayName, options=_sp_names(G.clientId)),
    'resource': F('On API', 'enum', col=Resource.displayName, options=_sp_names(G.resourceId)),
    'scope': F('Scope', 'enum', where=_scope_where, options=_scopes),
    'expiryTime': F('Expires', 'date', col=G.expiryTime),
})
GRANT_SORTS = {'client': Client.displayName, 'resource': Resource.displayName}


@router.get('/app-role-assignments')
def list_app_role_assignments(q: Annotated[AppRoleAssignmentQuery, Query()], db: Db) -> Page[AppRoleAssignmentRow]:
    stmt = select(ARA)
    if q.principalId:
        stmt = stmt.where(ARA.principalId == q.principalId)
    if q.resourceId:
        stmt = stmt.where(ARA.resourceId == q.resourceId)
    if q.principalType:
        stmt = stmt.where(ARA.principalType == q.principalType)
    if q.q:  # the role value is not a column, so search is done here rather than by paginate
        stmt = stmt.where(or_(_contains(ARA.principalDisplayName, q.q), _contains(ARA.resourceDisplayName, q.q),
                              _role_value_where('contains', q.q)))
        q = q.model_copy(update={'q': None})

    def build(rows):
        refs = resolve_refs(db, [i for a in rows for i in (a.principalId, a.resourceId)])
        app_roles = {oid: {r.get('id'): r for r in roles or [] if isinstance(r, dict)} for oid, roles in
                     db.execute(select(SP.objectId, SP.appRoles).where(SP.objectId.in_({a.resourceId for a in rows})))}
        out = []
        for a in rows:
            r = app_roles.get(a.resourceId, {}).get(a.id) or {}
            value = 'Default access' if a.id == DEFAULT_ACCESS else r.get('value') or r.get('displayName') or a.id or ''
            out.append(AppRoleAssignmentRow(
                id=a.objectId, principal=refs[a.principalId], resource=refs[a.resourceId], appRoleId=a.id or '',
                value=value, description=r.get('displayName') or r.get('description'),
                isPrivileged=a.id != DEFAULT_ACCESS and is_privileged_permission(value),
                createdDateTime=iso(a.creationTimestamp)))
        return out

    return paginate(db, stmt, q, resource='app-role-assignments', sorts=APP_ROLE_SORTS, build=build)


@router.get('/oauth2-grants')
def list_oauth2_grants(q: Annotated[OAuth2GrantQuery, Query()], db: Db) -> Page[OAuth2GrantRow]:
    stmt = select(G).outerjoin(Client, Client.objectId == G.clientId).outerjoin(Resource, Resource.objectId == G.resourceId)
    for col, v in ((G.clientId, q.clientId), (G.resourceId, q.resourceId), (G.principalId, q.principalId),
                   (G.consentType, q.consentType)):
        if v:
            stmt = stmt.where(col == v)
    if q.q:  # names matched once per object table, not per grant row (2x faster on 50k per-user grants)
        sps = select(SP.objectId).where(_contains(SP.displayName, q.q))
        users = select(d.User.objectId).where(or_(_contains(d.User.displayName, q.q), _contains(d.User.userPrincipalName, q.q)))
        stmt = stmt.where(or_(G.clientId.in_(sps), G.resourceId.in_(sps), G.principalId.in_(users), _contains(G.scope, q.q)))
        q = q.model_copy(update={'q': None})

    def build(rows):
        refs = resolve_refs(db, [i for g in rows for i in (g.clientId, g.resourceId, g.principalId)])
        out = []
        for g in rows:
            scopes = (g.scope or '').split()
            out.append(OAuth2GrantRow(
                id=g.objectId, consentType=g.consentType, principal=refs[g.principalId] if g.principalId else None,
                client=refs[g.clientId], resource=refs[g.resourceId], scopes=scopes,
                privilegedScopes=[s for s in scopes if is_privileged_permission(s)], expiryTime=iso(g.expiryTime)))
        return out

    return paginate(db, stmt, q, resource='oauth2-grants', sorts=GRANT_SORTS, build=build)
