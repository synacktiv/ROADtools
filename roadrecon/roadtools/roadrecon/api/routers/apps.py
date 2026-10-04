"""S4 service principals and applications."""
from typing import Annotated

from fastapi import APIRouter, Query

from ..common import Db, F, register
from ..models import (ApplicationDetail, ApplicationQuery, ApplicationRow, Page, ServicePrincipalDetail,
                      ServicePrincipalQuery, ServicePrincipalRow)

router = APIRouter(prefix='/api', tags=['apps'])

SP_FIELDS = register('service-principals', {
    'displayName': F('Name', 'text'),
    'appId': F('App ID', 'text'),
    'servicePrincipalType': F('Type', 'enum'),
    'publisherName': F('Publisher', 'enum'),
    'microsoftFirstParty': F('Microsoft app', 'bool'),
    'accountEnabled': F('Enabled', 'bool'),
    'appRoleAssignmentRequired': F('Assignment required', 'bool'),
    'passwordCount': F('Secrets', 'number'),
    'keyCount': F('Certificates', 'number'),
    'appRoleCount': F('App roles', 'number'),
    'hasCustomOwner': F('Has owner', 'bool'),
})

APP_FIELDS = register('applications', {
    'displayName': F('Name', 'text'),
    'appId': F('App ID', 'text'),
    'availableToOtherTenants': F('Multitenant', 'bool'),
    'publicClient': F('Public client', 'bool'),
    'oauth2AllowImplicitFlow': F('Implicit flow', 'bool'),
    'passwordCount': F('Secrets', 'number'),
    'keyCount': F('Certificates', 'number'),
    'appRoleCount': F('App roles', 'number'),
    'hasCustomOwner': F('Has owner', 'bool'),
})


@router.get('/service-principals')
def list_service_principals(q: Annotated[ServicePrincipalQuery, Query()], db: Db) -> Page[ServicePrincipalRow]:
    raise NotImplementedError


@router.get('/service-principals/{id}')
def get_service_principal(id: str, db: Db) -> ServicePrincipalDetail:
    raise NotImplementedError


@router.get('/applications')
def list_applications(q: Annotated[ApplicationQuery, Query()], db: Db) -> Page[ApplicationRow]:
    raise NotImplementedError


@router.get('/applications/{id}')
def get_application(id: str, db: Db) -> ApplicationDetail:
    raise NotImplementedError
