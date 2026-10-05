"""S2 groups: /api/groups, /api/groups/{id}."""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import Text, and_, case, func, not_, select, type_coerce, union

from roadtools.roadlib.metadef import database as d

from ..common import (ci, count_of, Db, F, descendant_groups, flag, gm_group, has_table, iso, member_groups_select,
                      not_found, paginate, register, transitive_groups_of)
from ..models import GroupDetail, GroupQuery, GroupRow, Page
from . import governance, policies, roles

router = APIRouter(prefix='/api', tags=['groups'])

G = d.Group
GROUP_TYPES = func.coalesce(type_coerce(G.groupTypes, Text), '')  # JSON text; plain Text so LIKE args are not JSON-encoded
UNIFIED = GROUP_TYPES.like('%Unified%')
DYNAMIC = func.coalesce(G.membershipRule, '') != ''
KIND = case((UNIFIED, 'Microsoft 365'), (and_(G.mailEnabled.is_(True), not_(G.securityEnabled.is_(True))), 'Distribution'),
            else_='Security')

FIELDS = register('groups', {
    'displayName': F('Name', 'text', col=G.displayName),
    'description': F('Description', 'text', col=G.description),
    'mail': F('Mail', 'text', col=G.mail),
    'kind': F('Type', 'enum', col=KIND, labels={'Microsoft 365': 'Microsoft 365', 'Distribution': 'Distribution', 'Security': 'Security'}),
    'isAssignableToRole': F('Role assignable', 'bool', col=G.isAssignableToRole),
    'dynamic': F('Dynamic membership', 'bool', col=DYNAMIC),
    'membershipRule': F('Membership rule', 'text', col=G.membershipRule),
    'isPublic': F('Public', 'bool', col=G.isPublic),
    'dirSyncEnabled': F('Synced from AD', 'bool', col=G.dirSyncEnabled),
    'createdDateTime': F('Created', 'date', col=G.createdDateTime),
})


def _row(g: d.Group) -> dict:
    return dict(
        id=g.objectId, displayName=g.displayName or g.objectId, description=g.description,
        groupTypes=g.groupTypes or [], securityEnabled=bool(g.securityEnabled), mailEnabled=bool(g.mailEnabled),
        mail=g.mail, isPublic=g.isPublic, isAssignableToRole=g.isAssignableToRole, membershipRule=g.membershipRule,
        dirSyncEnabled=g.dirSyncEnabled, createdDateTime=iso(g.createdDateTime),
    )


@router.get('/groups')
def list_groups(q: Annotated[GroupQuery, Query()], db: Db) -> Page[GroupRow]:
    stmt = select(G)
    if q.memberId:
        if q.transitive:
            # A group in a membership cycle is its own ancestor: leave it out.
            stmt = stmt.where(G.objectId.in_(select(transitive_groups_of(q.memberId).c.id)), G.objectId != q.memberId)
        else:
            stmt = stmt.where(G.objectId.in_(member_groups_select(q.memberId)))
    if q.memberOf:
        if q.transitive:
            stmt = stmt.where(G.objectId.in_(select(descendant_groups(q.memberOf).c.id)), G.objectId != q.memberOf)
        else:
            stmt = stmt.where(G.objectId.in_(select(gm_group.c.childGroup).where(gm_group.c.Group == q.memberOf)))
    if q.ownerId:
        ou, osp = d.lnk_group_owner_user, d.lnk_group_owner_serviceprincipal
        stmt = stmt.where(G.objectId.in_(union(select(ou.c.Group).where(ou.c.User == q.ownerId),
                                               select(osp.c.Group).where(osp.c.ServicePrincipal == q.ownerId))))
    if q.memberOfAu:
        au = d.lnk_au_member_group
        stmt = stmt.where(G.objectId.in_(select(au.c.Group).where(au.c.AdministrativeUnit == q.memberOfAu)))
    if q.isAssignableToRole is not None:
        stmt = stmt.where(flag(G.isAssignableToRole, q.isAssignableToRole))
    if q.dynamic is not None:
        stmt = stmt.where(DYNAMIC if q.dynamic else not_(DYNAMIC))
    if q.kind:
        stmt = stmt.where(KIND == ('Microsoft 365' if q.kind == 'microsoft365' else 'Security'))
    if q.dirSyncEnabled is not None:
        stmt = stmt.where(flag(G.dirSyncEnabled, q.dirSyncEnabled))
    return paginate(db, stmt, q, resource='groups', search=[G.displayName, G.mail, G.objectId],
                    sorts={'displayName': ci(G.displayName), 'createdDateTime': G.createdDateTime},
                    build=lambda rows: [GroupRow(**_row(g)) for g in rows])


@router.get('/groups/{id}')
def get_group(id: str, db: Db) -> GroupDetail:
    g = db.get(G, id)
    if g is None:
        raise not_found('Group')
    gu, gsp, gdev = d.lnk_group_member_user, d.lnk_group_member_serviceprincipal, d.lnk_group_member_device
    ou, osp, au = d.lnk_group_owner_user, d.lnk_group_owner_serviceprincipal, d.lnk_au_member_group
    desc = descendant_groups(id)
    c = db.execute(select(
        count_of(gu, gu.c.Group == id, distinct=gu.c.User).label('memberUsers'),
        count_of(gu, gu.c.Group.in_(select(desc.c.id)), distinct=gu.c.User).label('transitiveMemberUsers'),
        count_of(gm_group, gm_group.c.Group == id, distinct=gm_group.c.childGroup).label('memberGroups'),
        count_of(gsp, gsp.c.Group == id, distinct=gsp.c.ServicePrincipal).label('memberServicePrincipals'),
        count_of(gdev, gdev.c.Group == id, distinct=gdev.c.Device).label('memberDevices'),
        count_of(gm_group, gm_group.c.childGroup == id, distinct=gm_group.c.Group).label('memberOf'),
        count_of(ou, ou.c.Group == id).label('ownerUsers'),
        count_of(osp, osp.c.Group == id).label('ownerSps'),
        count_of(au, au.c.Group == id, distinct=au.c.AdministrativeUnit).label('administrativeUnits'),
        count_of(d.AppRoleAssignment.__table__, d.AppRoleAssignment.principalId == id).label('appRoleAssignments'),
    )).one()._asdict()
    c['owners'] = c.pop('ownerUsers') + c.pop('ownerSps')
    pim = d.lnk_pim_resource_aadgroup
    pim_enabled = has_table(db, pim.name) and db.scalar(select(func.count()).select_from(pim).where(pim.c.Group == id)) > 0
    return GroupDetail(
        **_row(g), pimEnabled=pim_enabled, securityIdentifier=g.cloudSecurityIdentifier,
        onPremisesSecurityIdentifier=g.onPremisesSecurityIdentifier,
        counts=dict(c, roles=roles.count_roles(db, id, transitive=False), policies=policies.count_affecting(db, 'group', id),
                    azureRoles=governance.count_azure_roles(db, id), pim=governance.count_pim(db, id, transitive=False)),
        raw=g.as_dict(),
    )
