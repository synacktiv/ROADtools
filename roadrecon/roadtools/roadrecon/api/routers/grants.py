"""S7 app role assignments and OAuth2 permission grants."""
from typing import Annotated

from fastapi import APIRouter, Query

from ..common import Db, F, register
from ..models import AppRoleAssignmentQuery, AppRoleAssignmentRow, OAuth2GrantQuery, OAuth2GrantRow, Page

router = APIRouter(prefix='/api', tags=['grants'])

APP_ROLE_FIELDS = register('app-role-assignments', {
    'principalType': F('Principal type', 'enum', labels={'user': 'User', 'group': 'Group', 'servicePrincipal': 'Service principal'}),
    'resource': F('Application', 'enum'),
    'value': F('Role', 'text'),
    'createdDateTime': F('Assigned', 'date'),
})

GRANT_FIELDS = register('oauth2-grants', {
    'consentType': F('Consent', 'enum', labels={'AllPrincipals': 'All users', 'Principal': 'One user'}),
    'client': F('Granted to', 'enum'),
    'resource': F('On API', 'enum'),
    'scope': F('Scope', 'enum'),
    'expiryTime': F('Expires', 'date'),
})


@router.get('/app-role-assignments')
def list_app_role_assignments(q: Annotated[AppRoleAssignmentQuery, Query()], db: Db) -> Page[AppRoleAssignmentRow]:
    raise NotImplementedError


@router.get('/oauth2-grants')
def list_oauth2_grants(q: Annotated[OAuth2GrantQuery, Query()], db: Db) -> Page[OAuth2GrantRow]:
    raise NotImplementedError
