"""S5 Conditional Access: policies, in-scope users, policies affecting an object, named locations (ADR 0001)."""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from ..common import Db, F, register
from ..models import (NamedLocationDetail, NamedLocationRow, Page, PageQuery, PolicyDetail, PolicyMatch,
                      PolicyQuery, PolicyRow, PolicyTargetType, PolicyUserQuery, UserRow)

router = APIRouter(prefix='/api', tags=['policies'])

POLICY_FIELDS = register('policies', {
    'displayName': F('Name', 'text'),
    'state': F('State', 'enum', labels={'enabled': 'Enabled', 'reporting': 'Report-only', 'disabled': 'Disabled'}),
    'block': F('Blocks access', 'bool'),
    'targetsAllUsers': F('All users', 'bool'),
    'targetsAllApps': F('All resources', 'bool'),
    'grant': F('Grant control', 'enum'),
    'sessionControls': F('Session control', 'enum'),
    'modifiedDateTime': F('Modified', 'date'),
})

LOCATION_FIELDS = register('named-locations', {
    'displayName': F('Name', 'text'),
    'kind': F('Kind', 'enum', labels={'ip': 'IP ranges', 'country': 'Countries'}),
    'trusted': F('Trusted', 'bool'),
    'policyCount': F('Used by policies', 'number'),
})


@router.get('/policies')
def list_policies(q: Annotated[PolicyQuery, Query()], db: Db) -> Page[PolicyRow]:
    raise NotImplementedError


@router.get('/policies/affecting/{type}/{id}')
def policies_affecting(type: PolicyTargetType, id: str, db: Db) -> list[PolicyMatch]:
    """Policies that include or exclude the object, directly or through groups and roles."""
    raise NotImplementedError


@router.get('/policies/{id}')
def get_policy(id: str, db: Db) -> PolicyDetail:
    raise NotImplementedError


@router.get('/policies/{id}/users')
def policy_users(id: str, q: Annotated[PolicyUserQuery, Query()], db: Db) -> Page[UserRow]:
    """Users in the policy scope (effect=applies, the default) or excluded from it."""
    raise NotImplementedError


@router.get('/named-locations')
def list_named_locations(q: Annotated[PageQuery, Query()], db: Db) -> Page[NamedLocationRow]:
    raise NotImplementedError


@router.get('/named-locations/{id}')
def get_named_location(id: str, db: Db) -> NamedLocationDetail:
    raise NotImplementedError


# --- Shared with other slices (counts on object pages); 0 until implemented ---

def count_affecting(db: Session, type: str, id: str) -> int:
    """len(policies_affecting(type, id)), possibly cheaper."""
    return 0
