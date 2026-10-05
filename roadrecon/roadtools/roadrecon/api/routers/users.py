"""S1 users: /api/users (incl. the MFA view filters), /api/users/{id}, /api/owners."""
from typing import Annotated, get_args
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Select, Text, false, func, literal, not_, or_, select, true, type_coerce, union, union_all
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d

from ..common import Db, F, descendant_groups, iso, mfa_summary, not_found, paginate, register
from ..models import MfaMethod, ObjectRef, OwnerQuery, Page, UserCounts, UserDetail, UserQuery, UserRow
from . import governance, policies, roles

router = APIRouter(prefix='/api', tags=['users'])

MFA_LABELS = {
    'PhoneAppNotification': 'Authenticator notification', 'PhoneAppOTP': 'Authenticator code', 'OneWaySms': 'Text message',
    'TwoWayVoiceMobile': 'Phone call', 'TwoWayVoiceOffice': 'Office phone call',
    'TwoWayVoiceAlternateMobile': 'Alternate phone call', 'Email': 'Email', 'Fido': 'FIDO2 key', 'WindowsHello': 'Windows Hello',
}

U = d.User
METHODS = set(get_args(MfaMethod))
USER_TYPE = func.coalesce(U.userType, 'Member')  # null userType in a dump = Member
# JSON columns as their stored text (type_coerce keeps the LIKE pattern from being JSON-encoded).
_SAD = func.coalesce(type_coerce(U.strongAuthenticationDetail, Text), '')
_KEYS = func.coalesce(type_coerce(U.searchableDeviceKey, Text), '')
MAILBOX_ONLY = (0, 7, 18)  # cloudMSExchRecipientDisplayType of shared / room mailboxes (old GUI /api/mfa)


def _method(m: str):
    """Users with this method: a strongAuthenticationDetail methodType, or FIDO / NGC device keys."""
    if m in METHODS:
        return _SAD.like(f'%"{m}"%')
    key = {'Fido': 'FIDO', 'WindowsHello': 'NGC'}.get(m)
    return _KEYS.like(f'%"{key}"%') if key else false()


HAS_MFA = or_(_SAD.like('%"methodType"%'), _method('Fido'), _method('WindowsHello'))
MFA_KINDS = {
    'none': not_(HAS_MFA),
    'app': or_(_method('PhoneAppOTP'), _method('PhoneAppNotification')),
    'phone': or_(*(_method(m) for m in ('OneWaySms', 'TwoWayVoiceMobile', 'TwoWayVoiceOffice', 'TwoWayVoiceAlternateMobile'))),
    'fido': _method('Fido'),
    'windowsHello': _method('WindowsHello'),
}


def _per_user(state: str):
    """Legacy per-user MFA state = requirements[0].state, any case; Disabled = neither enabled nor enforced."""
    if state == 'Disabled':
        return not_(or_(_per_user('Enabled'), _per_user('Enforced')))
    return _SAD.ilike(f'%"state": "{state}"%') if state in ('Enabled', 'Enforced') else false()


def _multi(test, any_):
    """`where` for a multi-valued enum: test(value) -> clause, any_ = the row has at least one value."""
    def where(op: str, arg: str):
        hit = or_(*(test(unquote(a)) for a in arg.split(',')))
        clauses = {'in': hit, 'eq': hit, 'notIn': not_(hit), 'ne': not_(hit), 'empty': not_(any_), 'notEmpty': any_}
        if op not in clauses:
            raise HTTPException(422, f'Operator {op} does not apply to this field')
        return clauses[op]
    return where


FIELDS = register('users', {
    'displayName': F('Name', 'text', col=U.displayName),
    'userPrincipalName': F('UPN', 'text', col=U.userPrincipalName),
    'mail': F('Mail', 'text', col=U.mail),
    'userType': F('Type', 'enum', col=USER_TYPE, options=lambda db: db.scalars(select(USER_TYPE).distinct())),
    'accountEnabled': F('Enabled', 'bool', col=U.accountEnabled),
    'dirSyncEnabled': F('Synced from AD', 'bool', col=U.dirSyncEnabled),
    'department': F('Department', 'enum', col=U.department),
    'jobTitle': F('Job title', 'enum', col=U.jobTitle),
    'mobile': F('Mobile', 'text', col=U.mobile),
    'lastPasswordChangeDateTime': F('Password changed', 'date', col=U.lastPasswordChangeDateTime),
    'mfaMethod': F('MFA method', 'enum', labels=MFA_LABELS, where=_multi(_method, HAS_MFA)),
    'hasMfa': F('Has MFA', 'bool', col=HAS_MFA),
    'hasApp': F('Authenticator app', 'bool', col=MFA_KINDS['app']),
    'hasPhone': F('Phone', 'bool', col=MFA_KINDS['phone']),
    'hasFido': F('FIDO2 key', 'bool', col=MFA_KINDS['fido']),
    'perUserMfa': F('Per-user MFA', 'enum', where=_multi(_per_user, true()),
                    options=lambda db: ['Enabled', 'Enforced', 'Disabled']),
})

SORTS = {
    'displayName': func.lower(U.displayName),
    'userPrincipalName': func.lower(U.userPrincipalName),
    'lastPasswordChangeDateTime': U.lastPasswordChangeDateTime,
}

# Owner links: (table, owned object column, owner column).
USER_OWNER_LINKS = [
    (d.lnk_device_owner, 'Device', 'User'),
    (d.lnk_group_owner_user, 'Group', 'User'),
    (d.lnk_application_owner_user, 'Application', 'User'),
    (d.lnk_serviceprincipal_owner_user, 'ServicePrincipal', 'User'),
]
SP_OWNER_LINKS = [
    (d.lnk_group_owner_serviceprincipal, 'Group', 'ServicePrincipal'),
    (d.lnk_application_owner_serviceprincipal, 'Application', 'ServicePrincipal'),
    (d.lnk_serviceprincipal_owner_serviceprincipal, 'ServicePrincipal', 'childServicePrincipal'),
]


def _owners(links, oid: str):
    return union(*(select(t.c[owner]).where(t.c[owned] == oid) for t, owned, owner in links))


def _row(u: d.User) -> dict:
    mfa = mfa_summary(u)
    # The spec's MfaMethod is a closed list: drop method types it does not know rather than fail the page.
    mfa['methods'] = [m for m in mfa['methods'] if m in METHODS]
    if mfa['defaultMethod'] not in METHODS:
        mfa['defaultMethod'] = None
    return dict(
        id=u.objectId, displayName=u.displayName or u.objectId, userPrincipalName=u.userPrincipalName or '',
        accountEnabled=bool(u.accountEnabled), mail=u.mail, department=u.department, jobTitle=u.jobTitle,
        mobile=u.mobile, lastPasswordChangeDateTime=iso(u.lastPasswordChangeDateTime), dirSyncEnabled=u.dirSyncEnabled,
        userType='Guest' if u.userType == 'Guest' else 'Member', mfa=mfa,
    )


@router.get('/users')
def list_users(q: Annotated[UserQuery, Query()], db: Db) -> Page[UserRow]:
    return page_users(db, q)


@router.get('/users/{id}')
def get_user(id: str, db: Db) -> UserDetail:
    u = db.get(U, id)
    if u is None:
        raise not_found('User')

    def count(col):
        return db.scalar(select(func.count()).where(col == id))

    gm, au = d.lnk_group_member_user, d.lnk_au_member_user
    owned = {key: count(t.c.User) for key, t in (
        ('ownedDevices', d.lnk_device_owner), ('ownedServicePrincipals', d.lnk_serviceprincipal_owner_user),
        ('ownedApplications', d.lnk_application_owner_user), ('ownedGroups', d.lnk_group_owner_user))}
    counts = UserCounts(
        memberOf=count(gm.c.User), administrativeUnits=count(au.c.User), **owned,
        appRoleAssignments=count(d.AppRoleAssignment.principalId), oauth2Grants=count(d.OAuth2PermissionGrant.principalId),
        roles=roles.count_roles(db, id), policies=policies.count_affecting(db, 'user', id),
        azureRoles=governance.count_azure_roles(db, id), pim=governance.count_pim(db, id),
        accessPackages=governance.count_access_packages(db, id),
    )
    return UserDetail(**_row(u), onPremisesSecurityIdentifier=u.onPremisesSecurityIdentifier,
                      createdDateTime=iso(u.createdDateTime), lastDirSyncTime=iso(u.lastDirSyncTime),
                      counts=counts, raw=u.as_dict())


@router.get('/owners')
def list_owners(q: Annotated[OwnerQuery, Query()], db: Db) -> Page[ObjectRef]:
    """Owners of any object: users and service principals."""
    sp = d.ServicePrincipal
    owners = union_all(
        select(U.objectId.label('id'), U.displayName.label('name'), U.userPrincipalName.label('sub'),
               literal('user').label('type')).where(U.objectId.in_(_owners(USER_OWNER_LINKS, q.ownerOf))),
        select(sp.objectId, sp.displayName, sp.appId, literal('servicePrincipal'))
        .where(sp.objectId.in_(_owners(SP_OWNER_LINKS, q.ownerOf))),
    ).subquery()
    return paginate(db, select(owners), q, search=[owners.c.name, owners.c.sub, owners.c.id],
                    sorts={'displayName': func.lower(owners.c.name)},
                    build=lambda rows: [ObjectRef(id=r.id, type=r.type, displayName=r.name or r.id, sub=r.sub) for r in rows])


# --- Shared with other slices --------------------------------------------------

def page_users(db: Session, q: UserQuery, within: Select | None = None) -> Page[UserRow]:
    """The users list with every UserQuery filter, optionally restricted to the ids of `within`
    (a one-column select of user ids). Used by /api/users and /api/policies/{id}/users."""
    stmt = select(U)
    if within is not None:
        stmt = stmt.where(U.objectId.in_(within))
    if q.userType:
        stmt = stmt.where(USER_TYPE == q.userType)
    for col, want in ((U.accountEnabled, q.accountEnabled), (U.dirSyncEnabled, q.dirSyncEnabled)):
        if want is not None:  # null counts as false, like the advanced filter
            stmt = stmt.where(col.is_(True) if want else or_(col.is_(False), col.is_(None)))
    if q.memberOf:
        gm = d.lnk_group_member_user
        groups = select(descendant_groups(q.memberOf).c.id) if q.transitive else [q.memberOf]
        stmt = stmt.where(U.objectId.in_(select(gm.c.User).where(gm.c.Group.in_(groups))))
    if q.ownerOf:
        stmt = stmt.where(U.objectId.in_(_owners(USER_OWNER_LINKS, q.ownerOf)))
    if q.memberOfAu:
        au = d.lnk_au_member_user
        stmt = stmt.where(U.objectId.in_(select(au.c.User).where(au.c.AdministrativeUnit == q.memberOfAu)))
    if q.mfa:
        stmt = stmt.where(MFA_KINDS[q.mfa])
    if q.perUserMfa:
        stmt = stmt.where(_per_user(q.perUserMfa))
    if q.excludeMailboxOnly:
        t = U.cloudMSExchRecipientDisplayType
        stmt = stmt.where(or_(t.is_(None), t.not_in(MAILBOX_ONLY)))
    # MFA required = in scope of an enabled CA policy that requires MFA. Shown (as a column) only on the MFA view and
    # only when CA policies were collected; the required-set is computed at most once and reused for filter + column.
    show_required = bool(q.excludeMailboxOnly) and policies.ca_policies_collected(db)
    required = policies.mfa_required_users(db) if q.mfaRequired is not None or show_required else None
    if q.mfaRequired is not None:  # ids are User.objectId (PK, non-null), so NOT IN has no NULL pitfall
        stmt = stmt.where(U.objectId.in_(required) if q.mfaRequired else U.objectId.not_in(required))

    def build(users):
        marked = set(db.scalars(select(U.objectId).where(U.objectId.in_([u.objectId for u in users]),
                                                         U.objectId.in_(required)))) if show_required and users else set()
        return [UserRow(**_row(u), mfaRequired=(u.objectId in marked) if show_required else None) for u in users]
    return paginate(db, stmt, q, resource='users', search=[U.displayName, U.userPrincipalName, U.objectId],
                    sorts=SORTS, build=build)
