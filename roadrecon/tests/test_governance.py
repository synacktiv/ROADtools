import datetime
import json
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.app import create_app
from roadtools.roadrecon.api.common import transitive_groups_of
from roadtools.roadrecon.api.models import AccessPackagePolicyRow, AzureRoleAssignmentRow, GroupPim, Page, PimAssignmentRow
from roadtools.roadrecon.api.routers import governance

AZ = d.AZroleAssignment
PA = d.PIMgovernanceRoleAssignment


def page(client, route, model, **params):
    r = client.get(route, params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[model].model_validate(r.json())


def azure(client, **params):
    return page(client, '/api/azure-role-assignments', AzureRoleAssignmentRow, **params)


def pim(client, **params):
    return page(client, '/api/pim-assignments', PimAssignmentRow, **params)


def packages(client, **params):
    return page(client, '/api/access-package-policies', AccessPackagePolicyRow, **params)


def groups_of(db, oid):
    return set(db.scalars(select(transitive_groups_of(oid).c.id)))


def member_of(db, group_id):
    """A user that is a direct member of the group."""
    gm = d.lnk_group_member_user
    return db.scalar(select(gm.c.User).where(gm.c.Group == group_id))


# --- Azure RBAC --------------------------------------------------------------

def test_azure_direct(client, db):
    for a in db.scalars(select(AZ)):
        p = azure(client, principalId=a.principal_id)
        row = next(r for r in p.items if r.id == a.id)
        rd = db.scalar(select(d.AZroleDefinition).where(d.AZroleDefinition.id == a.role_definition_id))
        assert row.kind == 'active' and row.via is None and row.principal.id == a.principal_id
        assert row.role.displayName == rd.role_name and row.role.isBuiltIn == (rd.role_type == 'BuiltInRole')
        assert row.scope == a.scope and row.conditional == bool(a.condition)
        assert p.total == db.query(AZ).filter(AZ.principal_id == a.principal_id).count()
    assert {r.role.isBuiltIn for a in db.scalars(select(AZ)) for r in azure(client, principalId=a.principal_id).items} == {True, False}


def test_azure_transitive_and_eligible(client, db):
    ea = db.scalar(select(d.AZroleEligibilityScheduleInstance))
    p = azure(client, principalId=ea.principal_id)
    assert [(r.id, r.kind) for r in p.items if r.kind == 'eligible'] == [(ea.id, 'eligible')]
    group_az = db.scalar(select(AZ).where(AZ.principal_type == 'Group'))
    user = member_of(db, group_az.principal_id)
    assert group_az.id not in {r.id for r in azure(client, principalId=user).items}
    p = azure(client, principalId=user, transitive=True)
    principals = {user} | groups_of(db, user)
    expected = {a.id for a in db.scalars(select(AZ).where(AZ.principal_id.in_(principals)))}
    expected |= {a.id for a in db.scalars(select(d.AZroleEligibilityScheduleInstance)
                                          .where(d.AZroleEligibilityScheduleInstance.principal_id.in_(principals)))}
    assert {r.id for r in p.items} == expected and p.total == governance.count_azure_roles(db, user)
    row = next(r for r in p.items if r.id == group_az.id)
    assert row.via.id == group_az.principal_id == row.principal.id and row.via.type == 'group'
    # Filters: bool, enum, kind param.
    assert {r.id for r in azure(client, principalId=user, transitive=True, filter='viaGroup:eq:true').items} == \
        {r.id for r in p.items if r.via}
    assert all(r.kind == 'active' for r in azure(client, principalId=user, transitive=True, kind='active').items)


def test_azure_filters_sorts_search(client, db):
    by_scope = {}
    for a in db.scalars(select(AZ)):
        by_scope.setdefault(governance.scope_type(a.scope), []).append(a)
    assert set(by_scope) == {'managementGroup', 'subscription', 'resourceGroup', 'resource'}
    for st, rows in by_scope.items():
        for a in rows:
            assert a.id in {r.id for r in azure(client, principalId=a.principal_id, filter=f'scopeType:eq:{st}').items}
            others = 'subscription' if st != 'subscription' else 'resource'
            assert a.id not in {r.id for r in azure(client, principalId=a.principal_id, filter=f'scopeType:eq:{others}').items}
    cond = db.scalar(select(AZ).where(AZ.condition.isnot(None)))
    assert [r.id for r in azure(client, principalId=cond.principal_id, filter='conditional:eq:true').items] == [cond.id]
    assert azure(client, principalId=cond.principal_id, filter='role:contains:zzz').total == 0
    assert azure(client, principalId=cond.principal_id, q='storage').total == 1
    sub = db.scalar(select(d.AZroleEligibilityScheduleInstance)).principal_id
    names = [r.role.displayName for r in azure(client, principalId=sub, transitive=True, sort='role', order='desc').items]
    assert names == sorted(names, key=str.lower, reverse=True)
    assert client.get('/api/azure-role-assignments', params={'principalId': sub, 'sort': 'nope'}).status_code == 422
    assert client.get('/api/azure-role-assignments').status_code == 422
    assert governance.scope_type('/') == 'managementGroup'
    assert governance.scope_type('/subscriptions/x/providers/Microsoft.Web/sites/y') == 'resource'


def test_azure_paging(client, db):
    pids = {a.principal_id for a in db.scalars(select(AZ))} | {a.principal_id for a in db.scalars(select(d.AZroleEligibilityScheduleInstance))}
    users = {member_of(db, p) for p in pids} - {None}
    pid = max(users | pids, key=lambda p: governance.count_azure_roles(db, p))
    full = azure(client, principalId=pid, transitive=True)
    assert full.total >= 2
    pages = [azure(client, principalId=pid, transitive=True, page_size=1, page=n) for n in range(1, full.total + 2)]
    assert [r.id for p in pages for r in p.items] == [r.id for r in full.items] and pages[0].total == full.total


# --- PIM ---------------------------------------------------------------------

def approval_of(db, role_def_id):
    s = db.scalar(select(d.PIMgovernanceRoleSettingV2).where(d.PIMgovernanceRoleSettingV2.roleDefinitionId == role_def_id))
    rule = next(v for v in s.lifeCycleManagement[0]['value'] if v['ruleIdentifier'] == 'ApprovalRule')
    return json.loads(rule['setting'])['enabled']


def test_pim_direct(client, db):
    eligible = db.scalars(select(PA).where(PA.assignmentState == 'Eligible')).all()
    assert {approval_of(db, a.roleDefinitionId) for a in eligible} == {True, False}
    for a in eligible:
        p = pim(client, principalId=a.subjectId)
        row = next(r for r in p.items if r.id == a.id)
        rd = db.get(d.PIMgovernanceRoleDefinition, a.roleDefinitionId)
        assert row.kind == 'eligible' and row.resourceType == 'directoryRole' and row.via is None
        assert row.resource.type == 'role' and row.resource.id == rd.templateId and row.role == rd.displayName
        assert row.approvalRequired == approval_of(db, a.roleDefinitionId) and row.endDateTime is not None
        assert p.total == db.query(PA).filter(PA.subjectId == a.subjectId).count()


def test_pim_transitive_and_filters(client, db):
    ga = db.scalar(select(PA).where(PA.assignmentState == 'Active'))
    user = member_of(db, ga.subjectId)
    assert pim(client, principalId=user).total == db.query(PA).filter(PA.subjectId == user).count()
    p = pim(client, principalId=user, transitive=True)
    expected = {a.id for a in db.scalars(select(PA).where(PA.subjectId.in_({user} | groups_of(db, user))))}
    assert {r.id for r in p.items} == expected and p.total == governance.count_pim(db, user)
    via = [r for r in p.items if r.via]
    assert via and all(r.via.id == ga.subjectId and r.kind == 'active' and r.endDateTime is None for r in via)
    assert {r.id for r in pim(client, principalId=user, transitive=True, filter='permanent:eq:true').items} == {r.id for r in via}
    assert {r.id for r in pim(client, principalId=user, transitive=True, filter='kind:eq:active').items} == {r.id for r in via}
    assert pim(client, principalId=user, transitive=True, filter='resourceType:eq:group').total == 0
    yes = {r.id for r in pim(client, principalId=user, transitive=True, filter='approvalRequired:eq:true').items}
    assert yes == {r.id for r in p.items if r.approvalRequired}
    roles = [r.role for r in pim(client, principalId=user, transitive=True, sort='role').items]
    assert roles == sorted(roles, key=str.lower)
    assert pim(client, principalId=user, transitive=True, filter='role:eq:Global Administrator').total == \
        sum(r.role == 'Global Administrator' for r in p.items)


# --- PIM for groups + access packages on a copy with more data ---------------

@pytest.fixture(scope='module')
def extra(dbpath, tmp_path_factory):
    """Copy of the test DB with a PIM group role setup and an all-members access package policy."""
    path = tmp_path_factory.mktemp('gov') / 'roadrecon.db'
    shutil.copy(dbpath, path)
    engine = create_engine(f'sqlite:///{path}')
    now = datetime.datetime(2026, 1, 1)
    with Session(engine) as s:
        lnk = d.lnk_pim_resource_aadgroup
        res_id, group = s.execute(select(lnk.c.PIMgovernanceResource, lnk.c.Group)).first()
        users = s.scalars(select(d.User.objectId).where(d.User.userType == 'Member').limit(3)).all()
        guest = s.scalar(select(d.User.objectId).where(d.User.userType == 'Guest'))
        out = {'group': group, 'users': users, 'guest': guest, 'roles': {}}
        for name, approval in (('Member', False), ('Owner', True)):
            rd = str(uuid.uuid4())
            out['roles'][name] = rd
            s.add(d.PIMgovernanceRoleDefinition(id=rd, resourceId=res_id, externalId=name.lower(), displayName=name))
            s.add(d.PIMgovernanceRoleSettingV2(id=str(uuid.uuid4()), resourceId=res_id, roleDefinitionId=rd, lifeCycleManagement=[
                {'caller': 'EndUser', 'level': 'Member', 'value': [
                    {'ruleIdentifier': 'ApprovalRule', 'setting': json.dumps({'enabled': approval})}]}]))
        for subject, role, state, end in ((users[0], 'Member', 'Eligible', now), (users[1], 'Member', 'Active', None),
                                          (users[0], 'Owner', 'Active', None)):
            s.add(d.PIMgovernanceRoleAssignment(id=str(uuid.uuid4()), resourceId=res_id, roleDefinitionId=out['roles'][role],
                                                subjectId=subject, assignmentState=state, startDateTime=now, endDateTime=end))
        pkg = s.scalar(select(d.IGaccessPackage.id))
        out['policy'] = str(uuid.uuid4())
        s.add(d.IGaccessPackageAssignmentPolicy(id=out['policy'], displayName='Everyone', accessPackageId=pkg,
                                                allowedTargetScope='allMemberUsers', canExtend=False,
                                                expiration={'type': 'afterDuration', 'duration': 'P30D'}))
        s.add(d.IGaccessPackageAssignmentPolicy(id=str(uuid.uuid4()), displayName='Deny', accessPackageId=pkg,
                                                allowedTargetScope='allDirectoryUsers', isDenyPolicy=True))
        s.commit()
    engine.dispose()
    with TestClient(create_app(str(path))) as c:
        yield c, out


def test_group_pim(client, db, extra):
    c, out = extra
    g = GroupPim.model_validate(c.get(f'/api/groups/{out["group"]}/pim').json())
    assert g.memberApprovalRequired is False and g.ownerApprovalRequired is True and g.onboardedDateTime
    assert sorted((m.subject.id, m.kind, m.endDateTime is None) for m in g.members) == \
        sorted([(out['users'][0], 'eligible', False), (out['users'][1], 'active', True)])
    assert [(o.subject.id, o.subject.type, o.kind) for o in g.owners] == [(out['users'][0], 'user', 'active')]
    # Same assignments from the principal side, as group rows.
    p = pim(c, principalId=out['users'][0])
    rows = sorted((r.resourceType, r.resource.id, r.resource.type, r.role, r.approvalRequired) for r in p.items if r.resourceType == 'group')
    assert rows == [('group', out['group'], 'group', 'Member', False), ('group', out['group'], 'group', 'Owner', True)]
    assert pim(c, principalId=out['users'][0], filter='resourceType:eq:group').total == 2
    # Onboarded without assignments, not onboarded, unknown.
    lnk = d.lnk_pim_resource_aadgroup
    other = db.scalar(select(lnk.c.Group).where(lnk.c.Group != out['group']))
    g = GroupPim.model_validate(client.get(f'/api/groups/{other}/pim').json())
    assert g.members == [] and g.owners == [] and g.onboardedDateTime
    plain = db.scalar(select(d.Group.objectId).where(d.Group.objectId.not_in(select(lnk.c.Group))))
    r = client.get(f'/api/groups/{plain}/pim')
    assert r.status_code == 200 and r.json() is None
    assert client.get('/api/groups/nope/pim').status_code == 404


def test_access_packages(client, db):
    pol = db.scalar(select(d.IGaccessPackageAssignmentPolicy))
    pkg = db.get(d.IGaccessPackage, pol.accessPackageId)
    direct = [t['objectId'] for t in pol.specificAllowedTargets if t['@odata.type'].endswith('singleUser')]
    group = next(t['objectId'] for t in pol.specificAllowedTargets if t['@odata.type'].endswith('groupMembers'))
    approver = db.get(d.User, pol.requestApprovalSettings['approvalStages'][0]['primaryApprovers'][0]['id'])
    p = packages(client, userId=direct[0])
    assert p.total == 1 == governance.count_access_packages(db, direct[0])
    row = p.items[0]
    assert (row.id, row.packageName, row.packageDescription, row.policyName) == (pol.id, pkg.displayName, pkg.description, pol.displayName)
    assert (row.via.id, row.via.type) == (direct[0], 'user')
    assert row.approvalRequired and row.approvers == [f'Stage 1: {approver.displayName}']
    assert row.durationDays == 180 and row.renewable
    res = db.scalar(select(d.IGaccessPackageResource))
    assert [(x.kind, x.resource.id, x.resource.type, x.role) for x in row.resources] == \
        [(res.resourceType, res.originId, 'group', 'Member')]
    # Through a group: a member of the scope group, or of a group nested in it.
    nested = d.lnk_group_member_group
    child = db.scalar(select(nested.c.childGroup).where(nested.c.Group == group))
    for g in [group] + ([child] if child else []):
        user = db.scalar(select(d.lnk_group_member_user.c.User).where(d.lnk_group_member_user.c.Group == g,
                                                                    d.lnk_group_member_user.c.User.not_in(direct)))
        row = packages(client, userId=user).items[0]
        assert (row.via.id, row.via.type) == (group, 'group')
    outsider = next(u for u in db.scalars(select(d.User.objectId)) if u not in direct and group not in groups_of(db, u))
    assert packages(client, userId=outsider).total == 0 and governance.count_access_packages(db, outsider) == 0
    assert packages(client, userId='nope').total == 0
    # Filters and sort.
    assert packages(client, userId=direct[0], filter='approvalRequired:eq:false').total == 0
    assert packages(client, userId=direct[0], filter='renewable:eq:true').total == 1
    assert packages(client, userId=direct[0], filter='packageName:contains:FLEET').total == 1
    assert packages(client, userId=direct[0], sort='packageName', order='desc').total == 1
    assert client.get('/api/access-package-policies', params={'userId': direct[0], 'sort': 'x'}).status_code == 422


def test_access_package_keywords(extra):
    c, out = extra
    member = out['users'][0]
    row = next(r for r in packages(c, userId=member).items if r.id == out['policy'])
    assert (row.via.type, row.via.displayName) == ('keyword', 'All member users')
    assert row.durationDays == 30 and not row.renewable and not row.approvalRequired and row.approvers == []
    # The deny policy is never listed; guests are not in "all member users".
    assert all(r.policyName != 'Deny' for r in packages(c, userId=member).items)
    assert out['policy'] not in {r.id for r in packages(c, userId=out['guest']).items}


# --- Old dumps without PIM / IG / AZ tables ----------------------------------

def test_minimal_db(minimal_client):
    c = minimal_client
    with c.app.state.sessionmaker() as s:
        user = s.scalar(select(d.User.objectId))
        group = s.scalar(select(d.Group.objectId))
        assert (governance.count_azure_roles(s, user), governance.count_pim(s, user),
                governance.count_access_packages(s, user)) == (0, 0, 0)
    assert azure(c, principalId=user, transitive=True).total == 0
    assert azure(c, principalId=user, kind='eligible', filter='kind:eq:eligible').total == 0
    assert pim(c, principalId=user, transitive=True).total == 0
    assert packages(c, userId=user).total == 0
    r = c.get(f'/api/groups/{group}/pim')
    assert r.status_code == 200 and r.json() is None
    for res in ('azure-role-assignments', 'pim-assignments', 'access-package-policies'):
        assert c.get(f'/api/filters/{res}').status_code == 200
