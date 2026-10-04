"""S3 devices and administrative units."""
from typing import Annotated

from fastapi import APIRouter, Query

from ..common import Db, F, register
from ..models import (AdministrativeUnitDetail, AdministrativeUnitQuery, AdministrativeUnitRow, DeviceDetail,
                      DeviceQuery, DeviceRow, Page)

router = APIRouter(prefix='/api', tags=['devices'])

DEVICE_FIELDS = register('devices', {
    'displayName': F('Name', 'text'),
    'deviceOSType': F('OS', 'enum'),
    'deviceOSVersion': F('OS version', 'text'),
    'deviceTrustType': F('Trust type', 'enum', labels={'AzureAd': 'Entra joined', 'ServerAd': 'Hybrid joined', 'Workplace': 'Registered'}),
    'deviceManufacturer': F('Manufacturer', 'enum'),
    'deviceModel': F('Model', 'enum'),
    'accountEnabled': F('Enabled', 'bool'),
    'isCompliant': F('Compliant', 'bool'),
    'isManaged': F('Managed', 'bool'),
    'isRooted': F('Rooted', 'bool'),
})

AU_FIELDS = register('administrative-units', {
    'displayName': F('Name', 'text'),
    'description': F('Description', 'text'),
    'dynamic': F('Dynamic membership', 'bool'),
})


@router.get('/devices')
def list_devices(q: Annotated[DeviceQuery, Query()], db: Db) -> Page[DeviceRow]:
    raise NotImplementedError


@router.get('/devices/{id}')
def get_device(id: str, db: Db) -> DeviceDetail:
    raise NotImplementedError


@router.get('/administrative-units')
def list_administrative_units(q: Annotated[AdministrativeUnitQuery, Query()], db: Db) -> Page[AdministrativeUnitRow]:
    raise NotImplementedError


@router.get('/administrative-units/{id}')
def get_administrative_unit(id: str, db: Db) -> AdministrativeUnitDetail:
    raise NotImplementedError
