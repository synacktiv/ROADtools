"""S3 devices and administrative units."""
import base64
import binascii
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import and_, not_, select, union

from roadtools.roadlib.metadef import database as d

from ..common import ci, count_of, Db, F, iso, not_found, paginate, register, resolve_refs, sql_clause
from ..models import (AdministrativeUnitDetail, AdministrativeUnitQuery, AdministrativeUnitRow, BitLockerKey,
                      DeviceDetail, DeviceQuery, DeviceRow, Page)
from . import roles

router = APIRouter(prefix='/api', tags=['devices'])

Dev, AU = d.Device, d.AdministrativeUnit

DEVICE_FIELDS = register('devices', {
    'displayName': F('Name', 'text', col=Dev.displayName),
    'deviceOSType': F('OS', 'enum', col=Dev.deviceOSType),
    'deviceOSVersion': F('OS version', 'text', col=Dev.deviceOSVersion),
    'deviceTrustType': F('Trust type', 'enum', col=Dev.deviceTrustType,
                         labels={'AzureAd': 'Entra joined', 'ServerAd': 'Hybrid joined', 'Workplace': 'Registered'}),
    'deviceManufacturer': F('Manufacturer', 'enum', col=Dev.deviceManufacturer),
    'deviceModel': F('Model', 'enum', col=Dev.deviceModel),
    'accountEnabled': F('Enabled', 'bool', col=Dev.accountEnabled),
    'isCompliant': F('Compliant', 'bool', col=Dev.isCompliant),
    'isManaged': F('Managed', 'bool', col=Dev.isManaged),
    'isRooted': F('Rooted', 'bool', col=Dev.isRooted),
})


def _dynamic(op: str, arg: str):
    has_rule = and_(AU.membershipRule.isnot(None), AU.membershipRule != '')
    return has_rule if (arg == 'true') == (op != 'ne') else not_(has_rule)


AU_FIELDS = register('administrative-units', {
    'displayName': F('Name', 'text', col=AU.displayName),
    'description': F('Description', 'text', col=AU.description),
    'dynamic': F('Dynamic membership', 'bool', where=_dynamic),
})

# MS Graph bitlockerRecoveryKey.volumeType
VOLUME_TYPES = {1: 'Operating system volume', 2: 'Fixed data volume', 3: 'Removable data volume'}


def _volume_type(v) -> str | None:
    return None if v is None else VOLUME_TYPES.get(v, str(v))


def _device_row(dev: d.Device) -> dict:
    return dict(
        id=dev.objectId, displayName=dev.displayName or dev.objectId, deviceId=dev.deviceId,
        accountEnabled=bool(dev.accountEnabled), deviceManufacturer=dev.deviceManufacturer, deviceModel=dev.deviceModel,
        deviceOSType=dev.deviceOSType, deviceOSVersion=dev.deviceOSVersion, deviceTrustType=dev.deviceTrustType,
        isCompliant=dev.isCompliant, isManaged=dev.isManaged, isRooted=dev.isRooted, dirSyncEnabled=dev.dirSyncEnabled,
    )


def _au_row(au: d.AdministrativeUnit) -> dict:
    return dict(id=au.objectId, displayName=au.displayName or au.objectId, description=au.description,
                membershipRule=au.membershipRule or None)



def recovery_key(material) -> str:
    """The dump stores the recovery password base64-encoded (the old GUI ran atob on it)."""
    try:
        return base64.b64decode(material or '', validate=True).decode('ascii')
    except (binascii.Error, UnicodeDecodeError):
        return str(material or '')


@router.get('/devices')
def list_devices(q: Annotated[DeviceQuery, Query()], db: Db) -> Page[DeviceRow]:
    stmt = select(Dev)
    links = ((q.memberOf, d.lnk_group_member_device, 'Group'), (q.ownerId, d.lnk_device_owner, 'User'),
             (q.memberOfAu, d.lnk_au_member_device, 'AdministrativeUnit'))
    for oid, table, col in links:
        if oid:
            stmt = stmt.where(Dev.objectId.in_(select(table.c.Device).where(table.c[col] == oid)))
    for key in ('accountEnabled', 'isCompliant', 'isManaged'):
        if (v := getattr(q, key)) is not None:
            stmt = stmt.where(sql_clause(DEVICE_FIELDS[key], 'eq', str(v).lower()))
    for key in ('deviceTrustType', 'deviceOSType'):
        if v := getattr(q, key):
            stmt = stmt.where(DEVICE_FIELDS[key].col == v)
    return paginate(db, stmt, q, resource='devices', search=[Dev.displayName, Dev.deviceId, Dev.objectId],
                    sorts={'displayName': ci(Dev.displayName), 'deviceOSType': Dev.deviceOSType,
                           **{k: DEVICE_FIELDS[k].col for k in ('deviceOSVersion', 'deviceTrustType', 'deviceManufacturer',
                                                                 'deviceModel', 'accountEnabled', 'isCompliant',
                                                                 'isManaged', 'isRooted')}},
                    build=lambda rows: [DeviceRow(**_device_row(r)) for r in rows])


@router.get('/devices/{id}')
def get_device(id: str, db: Db) -> DeviceDetail:
    dev = db.get(Dev, id)
    if dev is None:
        raise not_found('Device')
    owner_ids = db.scalars(select(d.lnk_device_owner.c.User).where(d.lnk_device_owner.c.Device == id)).all()
    refs = resolve_refs(db, owner_ids)
    gdev, adev = d.lnk_group_member_device, d.lnk_au_member_device
    keys = [BitLockerKey(keyIdentifier=str(k.get('keyIdentifier') or ''), keyMaterial=recovery_key(k.get('keyMaterial')),
                         volumeType=_volume_type(k.get('volumeType')),
                         creationTime=iso(k.get('creationTime')))
            for k in dev.bitLockerKey or [] if isinstance(k, dict)]
    return DeviceDetail(
        **_device_row(dev), bitLockerKeys=keys, owners=[refs[o] for o in owner_ids],
        counts=dict(owners=len(owner_ids), memberOf=db.scalar(select(count_of(gdev, gdev.c.Device == id))),
                    administrativeUnits=db.scalar(select(count_of(adev, adev.c.Device == id)))),
        raw=dev.as_dict(),
    )


AU_MEMBER_LINKS = ((d.lnk_au_member_user, 'User'), (d.lnk_au_member_group, 'Group'), (d.lnk_au_member_device, 'Device'))


@router.get('/administrative-units')
def list_administrative_units(q: Annotated[AdministrativeUnitQuery, Query()], db: Db) -> Page[AdministrativeUnitRow]:
    stmt = select(AU)
    if q.memberId:
        stmt = stmt.where(AU.objectId.in_(union(*(select(t.c.AdministrativeUnit).where(t.c[col] == q.memberId)
                                                  for t, col in AU_MEMBER_LINKS))))
    return paginate(db, stmt, q, resource='administrative-units', search=[AU.displayName],
                    sorts={'displayName': ci(AU.displayName), 'description': ci(AU.description),
                           'membershipRule': AU.membershipRule},
                    build=lambda rows: [AdministrativeUnitRow(**_au_row(r)) for r in rows])


@router.get('/administrative-units/{id}')
def get_administrative_unit(id: str, db: Db) -> AdministrativeUnitDetail:
    au = db.get(AU, id)
    if au is None:
        raise not_found('Administrative unit')
    users, groups, devices = (db.scalar(select(count_of(t, t.c.AdministrativeUnit == id))) for t, _ in AU_MEMBER_LINKS)
    return AdministrativeUnitDetail(
        **_au_row(au), raw=au.as_dict(),
        counts=dict(memberUsers=users, memberGroups=groups, memberDevices=devices,
                    scopedRoles=roles.count_scoped_roles(db, id)),
    )
