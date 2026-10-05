"""Device compliance (Intune): tenant settings and compliance policies, from `roadrecon compliancegather`.

Not collected by the original roadrecon: without the tables (or with them empty) the list is empty,
the settings are null and `Stats.compliancePolicies` is null, so the frontend hides the page.
"""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d

from ..common import Db, F, has_table, iso, keyword, not_found, paginate_list, register, resolve_refs
from ..models import (ComplianceAction, CompliancePolicyDetail, CompliancePolicyRow, ComplianceQuery, ComplianceSetting,
                      DeviceComplianceSettings, Page)

router = APIRouter(prefix='/api', tags=['compliance'])

CP, CPA, DMS = d.DeviceCompliancePolicy, d.DeviceCompliancePolicyAssignment, d.DeviceManagementSetting

PLATFORMS = {  # As labelled in the Intune admin center.
    'windows10': 'Windows 10/11', 'windows81': 'Windows 8.1', 'windowsPhone81': 'Windows Phone 8.1',
    'ios': 'iOS/iPadOS', 'macOS': 'macOS', 'android': 'Android device administrator',
    'androidWorkProfile': 'Android Enterprise (work profile)', 'androidDeviceOwner': 'Android Enterprise (fully managed)',
    'aospDeviceOwner': 'AOSP',
}
TARGETS = {'allLicensedUsers': 'All users', 'allDevices': 'All devices'}
METADATA = {'@odata.type', 'id', 'displayName', 'description', 'createdDateTime', 'lastModifiedDateTime', 'version',
            'roleScopeTagIds'}

COMPLIANCE_FIELDS = register('device-compliance', {
    'displayName': F('Name', 'text', get=lambda r: r.displayName),
    'platform': F('Platform', 'enum', get=lambda r: r.platform,
                  options=lambda db: {r.platform for r in _rows(db, _policies(db))}),
    'gracePeriodHours': F('Grace period (hours)', 'number', get=lambda r: r.gracePeriodHours),
    'lastModifiedDateTime': F('Modified', 'date', get=lambda r: r.lastModifiedDateTime),
})


def collected(db: Session) -> bool:
    """Compliance data was gathered: the tenant settings row exists (the original roadrecon never writes it)."""
    return has_table(db, DMS.__tablename__) and db.scalar(select(DMS.id).limit(1)) is not None


def count_policies(db: Session) -> int | None:
    """`Stats.compliancePolicies`: null when compliance was not collected."""
    if not collected(db):
        return None
    return db.scalar(select(func.count()).select_from(CP)) if has_table(db, CP.__tablename__) else 0


def _actions(p: d.DeviceCompliancePolicy) -> list[ComplianceAction]:
    return [ComplianceAction(actionType=c.get('actionType') or '', gracePeriodHours=c.get('gracePeriodHours') or 0,
                             notificationTemplateId=c.get('notificationTemplateId'))
            for rule in p.scheduledActionsForRule or [] for c in rule.get('scheduledActionConfigurations') or []]


def _policies(db: Session) -> list[d.DeviceCompliancePolicy]:
    return db.scalars(select(CP)).all() if has_table(db, CP.__tablename__) else []


def _rows(db: Session, policies: list[d.DeviceCompliancePolicy]) -> list[CompliancePolicyRow]:
    targets = {}  # policyId -> [assignment]
    if has_table(db, CPA.__tablename__):
        for a in db.scalars(select(CPA).where(CPA.policyId.in_([p.id for p in policies]))):
            targets.setdefault(a.policyId, []).append(a)
    refs = resolve_refs(db, [a.groupId for asg in targets.values() for a in asg])
    rows = []
    for p in policies:
        asg = targets.get(p.id, [])
        block = [a.gracePeriodHours for a in _actions(p) if a.actionType == 'block']
        rows.append(CompliancePolicyRow(
            id=p.id, displayName=p.displayName or p.id, description=p.description,
            platform=PLATFORMS.get(p.platform, p.platform or ''),
            assignments=[keyword(TARGETS[a.targetType]) if a.targetType in TARGETS else refs[a.groupId]
                         for a in asg if a.targetType != 'exclusionGroup' and (a.targetType in TARGETS or a.groupId)],
            exclusions=[refs[a.groupId] for a in asg if a.targetType == 'exclusionGroup' and a.groupId],
            gracePeriodHours=block[0] if block else None,
            lastModifiedDateTime=iso(p.lastModifiedDateTime)))
    return rows


@router.get('/device-compliance')
def list_compliance_policies(q: Annotated[ComplianceQuery, Query()], db: Db) -> Page[CompliancePolicyRow]:
    policies = _policies(db)
    rows = [r for r, p in zip(_rows(db, policies), policies) if not q.platform or q.platform in (r.platform, p.platform)]
    return paginate_list(rows, q, resource='device-compliance', text=lambda r: f'{r.displayName} {r.description or ""}',
                         sorts={'displayName': lambda r: r.displayName.lower(), 'platform': lambda r: r.platform,
                                'gracePeriodHours': lambda r: r.gracePeriodHours,
                                'lastModifiedDateTime': lambda r: r.lastModifiedDateTime})


@router.get('/device-compliance/settings')
def get_compliance_settings(db: Db) -> DeviceComplianceSettings | None:
    s = db.scalar(select(DMS).limit(1)) if collected(db) else None
    if s is None:
        return None
    return DeviceComplianceSettings(
        noPolicyDevicesCompliant=None if s.secureByDefault is None else not s.secureByDefault,
        checkinThresholdDays=s.deviceComplianceCheckinThresholdDays, enhancedJailBreak=s.enhancedJailBreak,
        isScheduledActionEnabled=s.isScheduledActionEnabled)


@router.get('/device-compliance/{id}')
def get_compliance_policy(id: str, db: Db) -> CompliancePolicyDetail:
    p = db.get(CP, id) if has_table(db, CP.__tablename__) else None
    if p is None:
        raise not_found('Compliance policy')
    settings = p.settings if isinstance(p.settings, dict) else {}
    return CompliancePolicyDetail(
        **_rows(db, [p])[0].model_dump(), createdDateTime=iso(p.createdDateTime), version=p.version,
        settings=[ComplianceSetting(name=k, value=v) for k, v in settings.items()
                  if v is not None and k not in METADATA and '@odata' not in k],
        actions=_actions(p), raw=p.as_dict())
