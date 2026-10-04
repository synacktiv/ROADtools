"""S9 meta: stats, tenant, global search, filter catalogues."""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d

from ..common import Db, like_escape, catalog, has_table
from . import roles
from ..models import (AuthorizationPolicySummary, DirectorySettingSummary, Domain, FilterField, FilterResource,
                      ObjectRef, SearchGroup, SearchResult, Stats, Tenant)

router = APIRouter(prefix='/api', tags=['meta'])

CA_POLICY, NAMED_LOCATION = 18, 6


@router.get('/filters/{resource}')
def get_filters(resource: FilterResource, db: Db) -> list[FilterField]:
    return catalog(db, resource)


def _role_source(db: Session):
    """(model, template id column): role definitions, or the activated DirectoryRoles on old dumps without them."""
    if has_table(db, 'RoleDefinitions') and db.scalar(select(literal(1)).select_from(d.RoleDefinition).limit(1)):
        return d.RoleDefinition, d.RoleDefinition.templateId
    return d.DirectoryRole, d.DirectoryRole.roleTemplateId


@router.get('/stats')
def get_stats(db: Db) -> Stats:
    count = lambda model, *where: select(func.count()).select_from(model).where(*where).scalar_subquery()  # noqa: E731
    row = db.execute(select(
        count(d.User).label('users'),
        count(d.User, d.User.userType == 'Guest').label('guests'),
        count(d.Group).label('groups'),
        count(d.Device).label('devices'),
        count(d.ServicePrincipal).label('servicePrincipals'),
        count(d.Application).label('applications'),
        count(d.AdministrativeUnit).label('administrativeUnits'),
        select(func.count()).select_from(roles.roles_sq).scalar_subquery().label('roles'),
        count(d.Policy, d.Policy.policyType == CA_POLICY).label('policies'),
        count(d.Policy, d.Policy.policyType == NAMED_LOCATION).label('namedLocations'),
    )).one()
    return Stats(**row._mapping)


# --- Tenant ------------------------------------------------------------------

# Strings as worded in the Entra admin center.
CONSENT = {
    'none': 'Do not allow user consent',
    'verifiedPublishers': 'Allow user consent for apps from verified publishers, for selected permissions',
    'all': 'Allow user consent for apps',
}
GUEST_ROLES = {
    'a0b1b346-4d3e-4e8b-98f8-753987be4970': ('member', 'Guest users have the same access as members (most inclusive)'),
    '10dae51f-b6af-4016-8d66-8c2a99b929b3': ('limited', 'Guest users have limited access to properties and memberships of directory objects'),
    '2af84b1e-32c8-42b7-82bc-daa82404023b': ('restricted', 'Guest user access is restricted to properties and memberships of their own directory objects (most restrictive)'),
}
INVITES = {
    'none': ('none', 'No one in the organization can invite guest users including admins (most restrictive)'),
    'admins': ('admins', 'Only users assigned to specific admin roles can invite guest users'),
    'adminsAndGuestInviters': ('adminsAndGuestInviters', 'Only users assigned to specific admin roles or the Guest Inviter role can invite guest users'),
    'adminsGuestInvitersAndAllMembers': ('members', 'Member users and users assigned to specific admin roles can invite guest users including guests with member permissions'),
    'everyone': ('everyone', 'Anyone in the organization can invite guest users including guests and non-admins (most inclusive)'),
}


def _consent(policy_ids: list[str]) -> tuple[str, str]:
    # Ids are 'ManagePermissionGrantsForSelf.<policy>'; ForOwnedResource ones are resource-specific consent (Teams, chats).
    own = [p for p in policy_ids if not p.startswith('ManagePermissionGrantsForOwnedResource.')]
    if any(p.endswith('microsoft-user-default-legacy') for p in own):
        return 'all', CONSENT['all']
    if any(p.endswith('microsoft-user-default-recommended') for p in own):
        return 'verifiedPublishers', 'Let Microsoft manage your consent settings'
    if any(p.endswith('microsoft-user-default-low') for p in own):
        return 'verifiedPublishers', CONSENT['verifiedPublishers']
    if own:
        return 'verifiedPublishers', 'Custom consent policy: ' + ', '.join(p.rpartition('.')[2] for p in own)
    return 'none', CONSENT['none']


def _auth_policy(ap: d.AuthorizationPolicy) -> AuthorizationPolicySummary:
    perms = ap.defaultUserRolePermissions or {}
    consent_policy, consent = _consent(ap.permissionGrantPolicyIdsAssignedToDefaultUserRole or [])
    # Unknown values fall back to the Entra defaults (limited guests, everyone invites); the text says so.
    guest_role, guest_access = GUEST_ROLES.get(ap.guestUserRoleId, ('limited', f'Unknown guest role: {ap.guestUserRoleId}'))
    invites_from, invites = INVITES.get(ap.allowInvitesFrom, ('everyone', f'Unknown: {ap.allowInvitesFrom}'))
    return AuthorizationPolicySummary(
        selfServicePasswordReset=ap.allowedToUseSSPR,
        blockMsolPowerShell=ap.blockMsolPowerShell,
        usersCanRegisterApps=perms.get('allowedToCreateApps'),
        usersCanCreateSecurityGroups=perms.get('allowedToCreateSecurityGroups'),
        usersCanReadOtherUsers=perms.get('allowedToReadOtherUsers'),
        userConsent=consent, guestAccess=guest_access, guestInvites=invites,
        userConsentPolicy=consent_policy, guestRole=guest_role, guestInvitesFrom=invites_from,
    )


def _domain(v: dict) -> Domain:
    caps = v.get('capabilities') or []
    if isinstance(caps, str):  # AAD Graph: 'Email, OfficeCommunicationsOnline'
        caps = caps.split(',')
    return Domain(name=v.get('name') or '', type=v.get('type') or '', capabilities=[c.strip() for c in caps if c.strip()],
                  isDefault=bool(v.get('default') or v.get('isDefault')), isInitial=bool(v.get('initial') or v.get('isInitial')))


@router.get('/tenant')
def get_tenant(db: Db) -> Tenant:
    td = db.scalars(select(d.TenantDetail).limit(1)).first()
    ap = db.scalars(select(d.AuthorizationPolicy).limit(1)).first() if has_table(db, 'AuthorizationPolicys') else None
    settings = db.scalars(select(d.DirectorySetting)).all() if has_table(db, 'DirectorySettings') else []
    domains = [_domain(v) for v in (td.verifiedDomains if td else None) or [] if isinstance(v, dict)]
    return Tenant(
        displayName=(td and td.displayName) or '',
        tenantId=(td and td.objectId) or '',
        dirSyncEnabled=td.dirSyncEnabled if td else None,
        domains=sorted(domains, key=lambda x: (not x.isDefault, not x.isInitial, x.name)),
        authorizationPolicy=_auth_policy(ap) if ap else None,
        directorySettings=[DirectorySettingSummary(
            name=s.displayName or s.templateId or s.id,
            values=[{'name': v.get('name') or '', 'value': '' if v.get('value') is None else str(v['value'])}
                    for v in s.values or [] if isinstance(v, dict)],
        ) for s in settings],
        raw=td.as_dict() if td else {},
    )


# --- Search ------------------------------------------------------------------

def _search_sources(db: Session):
    """(type, id, displayName, sub, extra searched columns, where), in the order shown to the user."""
    role, role_id = _role_source(db)
    P = d.Policy
    return [
        ('user', d.User.objectId, d.User.displayName, d.User.userPrincipalName, [], None),
        ('group', d.Group.objectId, d.Group.displayName, None, [d.Group.mail], None),
        ('device', d.Device.objectId, d.Device.displayName, None, [d.Device.deviceId], None),
        ('servicePrincipal', d.ServicePrincipal.objectId, d.ServicePrincipal.displayName, d.ServicePrincipal.appId, [], None),
        ('application', d.Application.objectId, d.Application.displayName, d.Application.appId, [], None),
        ('administrativeUnit', d.AdministrativeUnit.objectId, d.AdministrativeUnit.displayName, None, [], None),
        ('role', role_id, role.displayName, None, [], None),
        ('policy', P.objectId, P.displayName, None, [], P.policyType == CA_POLICY),
        ('namedLocation', P.objectId, P.displayName, None, [], P.policyType == NAMED_LOCATION),
    ]


@router.get('/search')
def search(q: Annotated[str, Query(min_length=1)], db: Db, limit: Annotated[int, Query(ge=1, le=50)] = 5) -> SearchResult:
    """Objects of every type matching `q`, grouped by type, `limit` per type."""
    q = q.strip()
    pattern = f'%{like_escape(q)}%'
    groups = []
    # ponytail: LIKE '%q%' full scan per type (~10 ms per 50k rows); FTS5 trigram if tenants get much larger.
    for typ, idcol, name, sub, extra, where in _search_sources(db):
        cols = [c for c in (idcol, name, sub, *extra) if c is not None]
        stmt = (select(idcol, name, sub if sub is not None else literal(None), func.count().over())
                .where(or_(*(c.ilike(pattern, escape='\\') for c in cols)))
                .order_by(case((idcol == q, 0), else_=1), name, idcol).limit(limit))
        if where is not None:
            stmt = stmt.where(where)
        rows = db.execute(stmt).all()
        if rows:
            groups.append(SearchGroup(type=typ, total=rows[0][3], items=[
                ObjectRef(id=oid, type=typ, displayName=dn or oid, sub=s) for oid, dn, s, _ in rows]))
    return SearchResult(groups=groups)
