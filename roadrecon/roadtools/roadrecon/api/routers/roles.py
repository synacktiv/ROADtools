"""S6 directory roles and role assignments.

Sources: RoleDefinitions + RoleAssignments (active) + EligibleRoleAssignments (eligible). Older dumps only have
DirectoryRoles + lnk_role_member_*: those rows are added when no RoleDefinition / directory-scoped RoleAssignment
already covers them, so both sources can coexist without double counting.
"""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import case, exists, func, literal, not_, null, or_, select, true, union, union_all
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d

from ..common import (DIRECTORY, PRIVILEGED_ROLES, Db, F, json_text, mfa_summary, not_found, paginate, register,
                      resolve_refs)
from ..models import Page, RoleAssignmentQuery, RoleAssignmentRow, RoleDetail, RoleHolderCount, RoleQuery, RoleRow

router = APIRouter(prefix='/api', tags=['roles'])

PRINCIPAL_TYPES = {'user': 'User', 'group': 'Group', 'servicePrincipal': 'Service principal'}

RD, DR, RA, ERA = d.RoleDefinition, d.DirectoryRole, d.RoleAssignment, d.EligibleRoleAssignment
U, G, SP = d.User, d.Group, d.ServicePrincipal
gm_group = d.lnk_group_member_group
ROLE_MEMBER_LINKS = [(d.lnk_role_member_user, 'User'), (d.lnk_role_member_serviceprincipal, 'ServicePrincipal'),
                     (d.lnk_role_member_group, 'Group')]


def _scope(col):
    """resourceScopes JSON text '["/administrativeUnits/x"]' -> '/administrativeUnits/x'.

    ponytail: assumes one scope per assignment (what Entra returns); split the list in Python if that changes.
    """
    t = json_text(col)
    for ch in '[]" ':
        t = func.replace(t, ch, '')
    return t


RD_ID = func.coalesce(RD.templateId, RD.objectId)

# Role catalogue: RoleDefinitions, plus activated DirectoryRoles that have no definition (old dumps).
roles_sq = union_all(
    select(RD_ID.label('id'), RD.displayName.label('name'), RD.description.label('description'),
           RD.isBuiltIn.label('isBuiltIn')),
    select(DR.roleTemplateId, DR.displayName, DR.description, true())
    .where(DR.roleTemplateId.not_in(select(RD_ID))),
).subquery('rn')
roles_sq.c.id.primary_key = True  # unique: lets paginate use it as the tie-breaker on count sorts


def _assignments(model, kind):
    return (select(model.id.label('id'), literal(kind).label('kind'),
                   func.coalesce(RD.templateId, model.roleDefinitionId).label('role_id'),
                   model.principalId.label('principal_id'), _scope(model.resourceScopes).label('scope'))
            .outerjoin(RD, RD.objectId == model.roleDefinitionId))


# Direct assignments, one row each.
direct = union_all(
    _assignments(RA, 'active'),
    _assignments(ERA, 'eligible'),
    *(select((DR.objectId + ':' + t.c[col]).label('id'), literal('active'), DR.roleTemplateId, t.c[col], literal('/'))
      .join(DR, DR.objectId == t.c.DirectoryRole)
      .where(~exists().where(RA.principalId == t.c[col], RA.roleDefinitionId == DR.roleTemplateId,
                             _scope(RA.resourceScopes) == '/'))
      for t, col in ROLE_MEMBER_LINKS),
).cte('direct')

# Groups holding a role (root) and every group nested under them (id).
nest = (select(direct.c.principal_id.label('root'), direct.c.principal_id.label('id'))
        .join(G, G.objectId == direct.c.principal_id).cte('nest', recursive=True))
nest = nest.union(select(nest.c.root, gm_group.c.childGroup).join(nest, gm_group.c.Group == nest.c.id))
members = union(*(select(nest.c.root, t.c[col].label('member')).join(nest, t.c.Group == nest.c.id)
                  for t, col in [(d.lnk_group_member_user, 'User'), (d.lnk_group_member_serviceprincipal, 'ServicePrincipal'),
                                 (gm_group, 'childGroup')])).subquery()

# Every (assignment, holder): the direct rows (via NULL), plus one row per transitive member of an assigned group
# (via = that group). principalId+transitive and expandGroups are both slices of this.
ra = union_all(
    select(direct.c.id, direct.c.kind, direct.c.role_id, direct.c.principal_id, direct.c.scope, null().label('via')),
    select((direct.c.id + ':' + members.c.member).label('id'), direct.c.kind, direct.c.role_id,
           members.c.member.label('principal_id'), direct.c.scope, direct.c.principal_id.label('via'))
    .join(members, members.c.root == direct.c.principal_id),
).subquery('ra')

IS_DIR = or_(ra.c.scope.is_(None), ra.c.scope.in_(['/', '', 'null']))
IS_AU = ra.c.scope.like('/administrativeUnits/%')
SCOPE_TYPE = case((IS_DIR, 'Directory'), (IS_AU, 'Administrative unit'), else_='Application')
# '/<object id>' as gathered; the old GUI also saw '/applications/<id>' and '/servicePrincipals/<id>'.
SCOPE_ID = case((IS_DIR, None), *((ra.c.scope.like(f'/{p}/%'), func.substr(ra.c.scope, len(p) + 3))
                                  for p in ('administrativeUnits', 'applications', 'servicePrincipals')),
                else_=func.substr(ra.c.scope, 2))
PRINCIPAL_TYPE = case((U.objectId.isnot(None), 'user'), (G.objectId.isnot(None), 'group'),
                      (SP.objectId.isnot(None), 'servicePrincipal'))
PRINCIPAL_NAME = func.coalesce(U.displayName, G.displayName, SP.displayName, ra.c.principal_id)
PRINCIPAL_ENABLED = func.coalesce(U.accountEnabled, SP.accountEnabled)

# Direct assignment counts per role, as SQL so the roles list can filter and sort on them.
counts = (select(direct.c.role_id, func.sum(case((direct.c.kind == 'active', 1), else_=0)).label('active'),
                 func.sum(case((direct.c.kind == 'eligible', 1), else_=0)).label('eligible'))
          .group_by(direct.c.role_id).subquery())
ACTIVE, ELIGIBLE = func.coalesce(counts.c.active, 0), func.coalesce(counts.c.eligible, 0)
# Distinct users synced from on-premises holding the role, directly or through a group, active or eligible.
synced = (select(ra.c.role_id, func.count(ra.c.principal_id.distinct()).label('synced'))
          .join(U, U.objectId == ra.c.principal_id).where(U.dirSyncEnabled.is_(True))
          .group_by(ra.c.role_id).subquery())
SYNCED = func.coalesce(synced.c.synced, 0)


def _via_group(op: str, arg: str):
    return ra.c.via.isnot(None) if (arg == 'true') == (op != 'ne') else ra.c.via.is_(None)


ROLE_FIELDS = register('roles', {
    'displayName': F('Name', 'text', col=roles_sq.c.name),
    'isBuiltIn': F('Built-in', 'bool', col=roles_sq.c.isBuiltIn),
    'activeCount': F('Active assignments', 'number', col=ACTIVE),
    'eligibleCount': F('Eligible assignments', 'number', col=ELIGIBLE),
})

ASSIGNMENT_FIELDS = register('role-assignments', {
    'role': F('Role', 'enum', col=roles_sq.c.name,
              options=lambda db: db.scalars(select(roles_sq.c.name).join(direct, direct.c.role_id == roles_sq.c.id).distinct())),
    'principalType': F('Principal type', 'enum', col=PRINCIPAL_TYPE, labels=PRINCIPAL_TYPES),
    'kind': F('Assignment', 'enum', col=ra.c.kind, labels={'active': 'Active', 'eligible': 'Eligible'},
              options=lambda db: ['active', 'eligible']),
    'scopeType': F('Scope', 'enum', col=SCOPE_TYPE, labels={'Directory': 'Directory', 'Administrative unit': 'Administrative unit', 'Application': 'Application'}),
    'principalEnabled': F('Principal enabled', 'bool', col=PRINCIPAL_ENABLED),
    'viaGroup': F('Through a group', 'bool', where=_via_group),
})


def _roles_select():
    return (select(roles_sq.c.id, roles_sq.c.name, roles_sq.c.description, roles_sq.c.isBuiltIn,
                   ACTIVE.label('active'), ELIGIBLE.label('eligible'), SYNCED.label('synced'))
            .outerjoin(counts, counts.c.role_id == roles_sq.c.id)
            .outerjoin(synced, synced.c.role_id == roles_sq.c.id))


def _role_row(r) -> dict:
    return dict(id=r.id, templateId=r.id, displayName=r.name or r.id, description=r.description,
                isBuiltIn=bool(r.isBuiltIn), isPrivileged=r.id in PRIVILEGED_ROLES,
                activeCount=r.active, eligibleCount=r.eligible, syncedCount=r.synced)


def _flag(col, want: bool):
    return col.is_(True) if want else or_(col.is_(False), col.is_(None))


@router.get('/roles')
def list_roles(q: Annotated[RoleQuery, Query()], db: Db) -> Page[RoleRow]:
    stmt = _roles_select()
    if q.isBuiltIn is not None:
        stmt = stmt.where(_flag(roles_sq.c.isBuiltIn, q.isBuiltIn))
    if q.hasAssignments is not None:
        held = ACTIVE + ELIGIBLE > 0
        stmt = stmt.where(held if q.hasAssignments else not_(held))
    if not q.sort:  # default order: privileged roles first, then by name
        stmt = stmt.order_by(roles_sq.c.id.in_(PRIVILEGED_ROLES).desc())
    return paginate(db, stmt, q, resource='roles', search=[roles_sq.c.name],
                    sorts={'displayName': func.lower(roles_sq.c.name), 'activeCount': ACTIVE, 'eligibleCount': ELIGIBLE,
                           'syncedCount': SYNCED},
                    build=lambda rows: [RoleRow(**_role_row(r)) for r in rows])


@router.get('/roles/{id}')
def get_role(id: str, db: Db) -> RoleDetail:
    """`id` is the role template id."""
    row = db.execute(_roles_select().where(roles_sq.c.id == id)).first()
    if row is None:
        raise not_found('Role')
    obj = db.scalar(select(RD).where(RD_ID == id)) or db.scalar(select(DR).where(DR.roleTemplateId == id))
    actions = [a for p in (getattr(obj, 'rolePermissions', None) or []) for a in (p.get('allowedResourceActions') or [])]
    scope_key = {'Directory': 'directory', 'Administrative unit': 'administrativeUnit', 'Application': 'application'}
    holders = [RoleHolderCount(kind=kind, principalType=ptype or 'unknown', scope=scope_key[stype], count=n)
               for kind, ptype, stype, n in db.execute(
                   _assignments_select().where(ra.c.role_id == id, ra.c.via.is_(None))
                   .with_only_columns(ra.c.kind, PRINCIPAL_TYPE, SCOPE_TYPE, func.count())
                   .group_by(ra.c.kind, PRINCIPAL_TYPE, SCOPE_TYPE))]
    return RoleDetail(**_role_row(row), allowedResourceActions=actions, holders=holders, raw=obj.as_dict())


def _assignments_select():
    return (select(ra.c.id, ra.c.kind, ra.c.role_id, roles_sq.c.name.label('role_name'), ra.c.principal_id,
                   ra.c.via, ra.c.scope, SCOPE_ID.label('scope_id'), PRINCIPAL_TYPE.label('principal_type'),
                   PRINCIPAL_ENABLED.label('enabled'), U.dirSyncEnabled, U.strongAuthenticationDetail,
                   U.searchableDeviceKey)
            .select_from(ra)
            .outerjoin(U, U.objectId == ra.c.principal_id)
            .outerjoin(G, G.objectId == ra.c.principal_id)
            .outerjoin(SP, SP.objectId == ra.c.principal_id)
            .outerjoin(roles_sq, roles_sq.c.id == ra.c.role_id))


def _assignment_rows(db: Session, rows) -> list[RoleAssignmentRow]:
    refs = resolve_refs(db, [i for r in rows for i in (r.principal_id, r.via, r.scope_id)])
    return [RoleAssignmentRow(
        id=r.id, kind=r.kind,
        role={'id': r.role_id, 'type': 'role', 'displayName': r.role_name or r.role_id},
        principal=refs[r.principal_id], via=refs[r.via] if r.via else None,
        scope=refs[r.scope_id] if r.scope_id else DIRECTORY,
        principalEnabled=r.enabled, principalDirSync=r.dirSyncEnabled if r.principal_type == 'user' else None,
        principalMfa=mfa_summary(r) if r.principal_type == 'user' else None,
    ) for r in rows]


@router.get('/role-assignments')
def list_role_assignments(q: Annotated[RoleAssignmentQuery, Query()], db: Db) -> Page[RoleAssignmentRow]:
    stmt = _assignments_select()
    if q.principalId:
        stmt = stmt.where(ra.c.principal_id == q.principalId)
        if not q.transitive:
            stmt = stmt.where(ra.c.via.is_(None))
    elif q.expandGroups:
        stmt = stmt.where(G.objectId.is_(None))  # assigned groups are replaced by their members
    else:
        stmt = stmt.where(ra.c.via.is_(None))
    if q.roleId:
        stmt = stmt.where(ra.c.role_id == q.roleId)
    if q.scopeId:
        stmt = stmt.where(SCOPE_ID == q.scopeId)
    if q.kind:
        stmt = stmt.where(ra.c.kind == q.kind)
    return paginate(db, stmt, q, resource='role-assignments', search=[PRINCIPAL_NAME, U.userPrincipalName, roles_sq.c.name],
                    sorts={'principal': func.lower(PRINCIPAL_NAME)},
                    build=lambda rows: _assignment_rows(db, rows))


# --- Shared with other slices (counts on object pages) ---

def count_roles(db: Session, principal_id: str, transitive: bool = True) -> int:
    """Directory role assignments (active and eligible) of a user, group or SP, direct and (`transitive`) through groups."""
    return db.scalar(select(func.count()).select_from(ra).where(
        ra.c.principal_id == principal_id, *([] if transitive else [ra.c.via.is_(None)])))


def count_scoped_roles(db: Session, scope_id: str) -> int:
    """Role assignments scoped to an administrative unit or application."""
    return db.scalar(select(func.count()).select_from(ra).where(ra.c.via.is_(None), SCOPE_ID == scope_id))
