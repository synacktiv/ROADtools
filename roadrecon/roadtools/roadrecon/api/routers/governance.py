"""S8 governance: Azure RBAC, PIM and access packages. Tables may be missing: return empty results then.

These lists are per principal and small, so rows are built in Python and paged with `paginate_list`;
the per-principal lookups use the indexed `principal_id` / `subjectId` columns.
"""
import json
import re
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d

from ..common import (Db, F, has_table, iso, keyword, not_found, paginate_list, register, resolve_refs,
                      transitive_groups_of, value)
from ..models import (AccessPackagePolicyQuery, AccessPackagePolicyRow, AccessPackageResource, AzureRole,
                      AzureRoleAssignmentQuery, AzureRoleAssignmentRow, GroupPim, ObjectRef, Page, PimAssignmentQuery,
                      PimAssignmentRow, PimSubject)

router = APIRouter(prefix='/api', tags=['governance'])

KINDS = {'active': 'Active', 'eligible': 'Eligible'}


def scope_type(scope: str) -> str:
    s = (scope or '').lower()
    # The tenant root ('/') is wider than any management group: shown as one.
    if not s.strip('/') or '/providers/microsoft.management/managementgroups/' in s:
        return 'managementGroup'
    if '/providers/' in s:
        return 'resource'
    return 'resourceGroup' if '/resourcegroups/' in s else 'subscription'


AZURE_FIELDS = register('azure-role-assignments', {
    'role': F('Role', 'text', get=lambda r: r.role.displayName),
    'kind': F('Assignment', 'enum', labels=KINDS, get=lambda r: r.kind),
    'scopeType': F('Scope level', 'enum', labels={'managementGroup': 'Management group', 'subscription': 'Subscription',
                                                   'resourceGroup': 'Resource group', 'resource': 'Resource'},
                   get=lambda r: scope_type(r.scope)),
    'viaGroup': F('Through a group', 'bool', get=lambda r: r.via is not None),
    'conditional': F('Conditional', 'bool', get=lambda r: r.conditional),
})

PIM_FIELDS = register('pim-assignments', {
    'role': F('Role', 'text', get=lambda r: r.role),
    'resourceType': F('Resource', 'enum', labels={'directoryRole': 'Directory role', 'group': 'Group', 'other': 'Other'},
                      get=lambda r: r.resourceType),
    'kind': F('Assignment', 'enum', labels=KINDS, get=lambda r: r.kind),
    'approvalRequired': F('Approval required', 'bool', get=lambda r: r.approvalRequired),
    'permanent': F('Permanent', 'bool', get=lambda r: r.endDateTime is None),
})

ACCESS_PACKAGE_FIELDS = register('access-package-policies', {
    'packageName': F('Access package', 'text', get=lambda r: r.packageName),
    'approvalRequired': F('Approval required', 'bool', get=lambda r: r.approvalRequired),
    'renewable': F('Renewable', 'bool', get=lambda r: r.renewable),
})


def _principal_ids(db: Session, principal_id: str, transitive: bool | None) -> list[str]:
    groups = db.scalars(select(transitive_groups_of(principal_id).c.id)) if transitive else []
    return list(dict.fromkeys([principal_id, *groups]))


def _count(db: Session, stmt) -> int:
    return db.scalar(select(func.count()).select_from(stmt.subquery()))


# --- Azure RBAC --------------------------------------------------------------

AZ_SOURCES = (('active', d.AZroleAssignment), ('eligible', d.AZroleEligibilityScheduleInstance))


def _azure_selects(db: Session, ids: list[str], kind: str | None = None):
    return [(k, select(m).where(m.principal_id.in_(ids))) for k, m in AZ_SOURCES
            if (not kind or kind == k) and has_table(db, m.__tablename__)]


@router.get('/azure-role-assignments')
def list_azure_role_assignments(q: Annotated[AzureRoleAssignmentQuery, Query()], db: Db) -> Page[AzureRoleAssignmentRow]:
    pid = q.principalId
    rows = [(k, a) for k, stmt in _azure_selects(db, _principal_ids(db, pid, q.transitive), q.kind)
            for a in db.scalars(stmt)]
    guid = lambda a: (a.role_definition_id or '').rstrip('/').rsplit('/', 1)[-1]  # noqa: E731
    defs = {}
    if rows and has_table(db, d.AZroleDefinition.__tablename__):
        rd = d.AZroleDefinition
        defs = {r.name: r for r in db.scalars(select(rd).where(rd.name.in_({guid(a) for _, a in rows})))}
    refs = resolve_refs(db, [a.principal_id for _, a in rows])
    items = []
    for k, a in rows:
        r = defs.get(guid(a))
        role = (AzureRole(displayName=r.role_name or r.name, description=r.description, isBuiltIn=r.role_type == 'BuiltInRole')
                if r else AzureRole(displayName=guid(a) or 'Unknown role', description=None, isBuiltIn=False))
        ref = refs[a.principal_id]
        items.append(AzureRoleAssignmentRow(id=a.id, kind=k, role=role, principal=ref,
                                            via=ref if a.principal_id != pid else None,
                                            scope=a.scope or '', conditional=bool(a.condition)))
    return paginate_list(items, q, resource='azure-role-assignments', text=lambda r: f'{r.role.displayName} {r.scope}',
                         sorts={'role': lambda r: r.role.displayName.lower(), 'kind': lambda r: r.kind})


# --- PIM ---------------------------------------------------------------------

PIM_TYPES = {'aadroles': 'directoryRole', 'aadgroups': 'group'}
PA, PR, PD, PS = (d.PIMgovernanceRoleAssignment, d.PIMgovernanceResource, d.PIMgovernanceRoleDefinition,
                  d.PIMgovernanceRoleSettingV2)


def _approval_required(setting) -> bool | None:
    """Whether activating needs approval: EndUser / Member rule `ApprovalRule` of a role setting (v2)."""
    for rule in (setting.lifeCycleManagement or []) if setting else []:
        if rule.get('caller') != 'EndUser' or rule.get('level') != 'Member':
            continue
        for v in rule.get('value') or []:
            if v.get('ruleIdentifier') == 'ApprovalRule':
                s = v.get('setting')
                s = json.loads(s) if isinstance(s, str) else (s or {})
                return bool(s.get('enabled'))
    return None


def _settings(db: Session, role_def_ids) -> dict:
    out = {}
    for s in db.scalars(select(PS).where(PS.roleDefinitionId.in_(set(role_def_ids)))):
        if out.get(s.roleDefinitionId) is None:
            out[s.roleDefinitionId] = _approval_required(s)
    return out


@router.get('/pim-assignments')
def list_pim_assignments(q: Annotated[PimAssignmentQuery, Query()], db: Db) -> Page[PimAssignmentRow]:
    pid = q.principalId
    if not has_table(db, PA.__tablename__):
        return paginate_list([], q, resource='pim-assignments')
    rows = db.scalars(select(PA).where(PA.subjectId.in_(_principal_ids(db, pid, q.transitive)))).all()
    res_ids = {a.resourceId for a in rows}
    defs = {r.id: r for r in db.scalars(select(PD).where(PD.id.in_({a.roleDefinitionId for a in rows})))}
    resources = {r.id: r for r in db.scalars(select(PR).where(PR.id.in_(res_ids)))}
    lnk = d.lnk_pim_resource
    types = {r: PIM_TYPES.get(pa, 'other') for pa, r in db.execute(
        select(lnk.c.PIMprivilegedAccess, lnk.c.PIMgovernanceResource).where(lnk.c.PIMgovernanceResource.in_(res_ids)))}
    approval = _settings(db, defs)

    def target(a):  # (resource type, id to resolve, role name)
        rtype, rd, res = types.get(a.resourceId, 'other'), defs.get(a.roleDefinitionId), resources.get(a.resourceId)
        name = (rd and (rd.displayName or rd.externalId)) or a.roleDefinitionId or 'Unknown role'
        if rtype == 'directoryRole':
            return rtype, rd and (rd.templateId or rd.externalId), name
        if rtype == 'group':
            return rtype, res and res.externalId, name.capitalize()
        return rtype, None, name

    targets = {a.id: target(a) for a in rows}
    refs = resolve_refs(db, [t[1] for t in targets.values()] + [a.subjectId for a in rows])
    items = []
    for a in rows:
        rtype, oid, role = targets[a.id]
        res = resources.get(a.resourceId)
        resource = refs[oid] if oid else value((res and (res.displayName or res.externalId)) or a.resourceId or role)
        items.append(PimAssignmentRow(
            id=a.id, kind='eligible' if (a.assignmentState or '').lower() == 'eligible' else 'active',
            resourceType=rtype, resource=resource, role=role,
            via=refs[a.subjectId] if a.subjectId != pid else None, approvalRequired=approval.get(a.roleDefinitionId),
            startDateTime=iso(a.startDateTime), endDateTime=iso(a.endDateTime)))
    return paginate_list(items, q, resource='pim-assignments', text=lambda r: f'{r.role} {r.resource.displayName}',
                         sorts={'role': lambda r: r.role.lower(), 'kind': lambda r: r.kind,
                                'resourceType': lambda r: r.resourceType})


@router.get('/groups/{id}/pim')
def get_group_pim(id: str, db: Db) -> GroupPim | None:
    """PIM for Groups settings and assignments; null when the group is not onboarded."""
    if db.get(d.Group, id) is None:
        raise not_found('Group')
    lnk = d.lnk_pim_resource_aadgroup
    if not has_table(db, lnk.name):
        return None
    res = db.scalar(select(PR).join(lnk, lnk.c.PIMgovernanceResource == PR.id).where(lnk.c.Group == id))
    if res is None:
        return None
    defs = {r.id: (r.displayName or r.externalId or '').lower() for r in db.scalars(select(PD).where(PD.resourceId == res.id))}
    rows = db.scalars(select(PA).where(PA.resourceId == res.id)).all()
    refs = resolve_refs(db, [a.subjectId for a in rows])
    sides = {'member': [], 'owner': []}
    for a in rows:
        side = sides.get(defs.get(a.roleDefinitionId))
        if side is not None:
            side.append(PimSubject(subject=refs[a.subjectId] if a.subjectId else value('Unknown'),
                                   kind='eligible' if (a.assignmentState or '').lower() == 'eligible' else 'active',
                                   startDateTime=iso(a.startDateTime), endDateTime=iso(a.endDateTime)))
    approval = _settings(db, defs)
    by_side = {name: approval.get(rid) for rid, name in defs.items()}
    return GroupPim(onboardedDateTime=iso(res.onboardDateTime), memberApprovalRequired=by_side.get('member'),
                    ownerApprovalRequired=by_side.get('owner'), members=sides['member'], owners=sides['owner'])


# --- Access packages ---------------------------------------------------------

AP, PKG = d.IGaccessPackageAssignmentPolicy, d.IGaccessPackage
# allowedTargetScope keywords that cover a user, by user type (as the old GUI did).
SCOPE_KEYWORDS = {'allDirectoryUsers': 'All users', 'allMemberUsers': 'All member users',
                  'allExternalUsers': 'All external users'}
APPROVER_TYPES = {'requestorManager': 'Manager', 'internalSponsors': 'Internal sponsors',
                  'externalSponsors': 'External sponsors'}


def _policy_reasons(db: Session, user_id: str) -> dict[str, str | ObjectRef]:
    """Policy id -> why the user is in scope: the user id (direct), a group id, or a keyword ref. First reason wins."""
    if not has_table(db, AP.__tablename__):
        return {}
    user = db.get(d.User, user_id)
    if user is None:
        return {}
    inu, ing = d.lnk_ig_ap_assignment_policy_inscope_user, d.lnk_ig_ap_assignment_policy_inscope_group
    out: dict = {}
    for pol in db.scalars(select(inu.c.IGaccessPackageAssignmentPolicy).where(inu.c.User == user_id)):
        out.setdefault(pol, user_id)
    groups = select(transitive_groups_of(user_id).c.id)
    for pol, gid in db.execute(select(ing.c.IGaccessPackageAssignmentPolicy, ing.c.Group).where(ing.c.Group.in_(groups))):
        out.setdefault(pol, gid)
    scopes = ['allDirectoryUsers', 'allExternalUsers' if user.userType == 'Guest' else 'allMemberUsers']
    for pol, scope in db.execute(select(AP.id, AP.allowedTargetScope).where(AP.allowedTargetScope.in_(scopes))):
        out.setdefault(pol, keyword(SCOPE_KEYWORDS[scope]))
    return out


def _requestable(reasons):
    return select(AP).where(AP.id.in_(list(reasons)), AP.isDenyPolicy.isnot(True))


def _duration_days(p) -> int | None:
    if p.durationInDays:
        return p.durationInDays
    m = re.fullmatch(r'P(\d+)D', (p.expiration or {}).get('duration') or '')
    return int(m.group(1)) if m else None


def _package_resources(db: Session, pkg_ids) -> dict[str, list[AccessPackageResource]]:
    """Package -> resource role scopes -> role -> resource."""
    rrs, rrs_role, rr = d.lnk_ig_ap_rr_scope, d.lnk_ig_ap_rrs_role, d.lnk_ig_ap_rr
    R, Role = d.IGaccessPackageResource, d.IGaccessPackageResourceRole
    rows = db.execute(select(rrs.c.IGaccessPackage, R, Role.displayName).select_from(rrs)
                      .join(rrs_role, rrs_role.c.IGaccessPackageResourceRoleScope == rrs.c.IGaccessPackageResourceRoleScope)
                      .join(Role, Role.id == rrs_role.c.IGaccessPackageResourceRole)
                      .join(rr, rr.c.IGaccessPackageResourceRole == Role.id)
                      .join(R, R.id == rr.c.IGaccessPackageResource)
                      .where(rrs.c.IGaccessPackage.in_(set(pkg_ids)))).all()
    directory = ('AadGroup', 'AadApplication')
    refs = resolve_refs(db, [r.originId for _, r, _ in rows if r.originSystem in directory])
    out: dict[str, list] = {}
    for pkg, r, role in rows:
        if r.originSystem in directory and r.originId:
            ref = refs[r.originId]
            if ref.type == 'unknown':
                ref = ObjectRef(id=r.originId, type='unknown', displayName=r.displayName or r.originId)
        else:
            ref = value(r.url or r.displayName or r.originId or r.id)
        out.setdefault(pkg, []).append(AccessPackageResource(kind=r.resourceType or r.originSystem or 'Resource',
                                                             resource=ref, role=role))
    return out


def _approval(p, refs) -> tuple[bool, list[str]]:
    s = p.requestApprovalSettings or p.approvalSettings or {}
    required = bool(s.get('isApprovalRequiredForAdd', s.get('isApprovalRequired')))

    def name(a):
        ref = refs.get(a.get('id'))
        if ref and ref.type != 'unknown':
            return ref.displayName
        kind = (a.get('@odata.type') or '').rsplit('.', 1)[-1]
        return a.get('displayName') or a.get('description') or APPROVER_TYPES.get(kind) or a.get('id') or kind

    approvers = []
    for i, stage in enumerate(s.get('approvalStages') or [], 1):
        for key, label in (('primaryApprovers', f'Stage {i}'), ('fallbackPrimaryApprovers', f'Stage {i} fallback')):
            names = [name(a) for a in stage.get(key) or []]
            if names:
                approvers.append(f'{label}: {", ".join(names)}')
    return required, approvers


def _approver_ids(p):
    s = p.requestApprovalSettings or p.approvalSettings or {}
    return [a.get('id') for st in s.get('approvalStages') or []
            for key in ('primaryApprovers', 'fallbackPrimaryApprovers') for a in st.get(key) or []]


@router.get('/access-package-policies')
def list_access_package_policies(q: Annotated[AccessPackagePolicyQuery, Query()], db: Db) -> Page[AccessPackagePolicyRow]:
    """Access package policies the user can request, directly or through a group."""
    reasons = _policy_reasons(db, q.userId)
    if not reasons:
        return paginate_list([], q, resource='access-package-policies')
    policies = db.scalars(_requestable(reasons)).all()
    pkgs = {p.id: p for p in db.scalars(select(PKG).where(PKG.id.in_({p.accessPackageId for p in policies})))}
    resources = _package_resources(db, pkgs) if pkgs else {}
    refs = resolve_refs(db, [r for r in reasons.values() if isinstance(r, str)]
                        + [i for p in policies for i in _approver_ids(p)])
    items = []
    for p in policies:
        pkg = pkgs.get(p.accessPackageId)
        required, approvers = _approval(p, refs)
        why = reasons[p.id]
        items.append(AccessPackagePolicyRow(
            id=p.id, packageName=(pkg and pkg.displayName) or p.accessPackageId or p.id,
            packageDescription=pkg and pkg.description, policyName=p.displayName or '',
            resources=resources.get(p.accessPackageId, []), approvalRequired=required, approvers=approvers,
            durationDays=_duration_days(p), renewable=bool(p.canExtend),
            via=refs[why] if isinstance(why, str) else why))
    return paginate_list(items, q, resource='access-package-policies',
                         text=lambda r: f'{r.packageName} {r.policyName} {r.packageDescription or ""}',
                         sorts={'packageName': lambda r: r.packageName.lower()})


# --- Shared with other slices (counts on object pages) -----------------------

def count_azure_roles(db: Session, principal_id: str) -> int:
    """Azure role assignments (active and eligible), direct and through groups."""
    ids = _principal_ids(db, principal_id, True)
    return sum(_count(db, stmt) for _, stmt in _azure_selects(db, ids))


def count_pim(db: Session, principal_id: str) -> int:
    """PIM assignments, direct and through groups."""
    if not has_table(db, PA.__tablename__):
        return 0
    return _count(db, select(PA.id).where(PA.subjectId.in_(_principal_ids(db, principal_id, True))))


def count_access_packages(db: Session, user_id: str) -> int:
    """Access package policies the user can request."""
    reasons = _policy_reasons(db, user_id)
    return _count(db, _requestable(reasons)) if reasons else 0
