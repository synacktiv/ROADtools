"""S6 directory roles and role assignments."""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from ..common import Db, F, register
from ..models import Page, RoleAssignmentQuery, RoleAssignmentRow, RoleDetail, RoleQuery, RoleRow

router = APIRouter(prefix='/api', tags=['roles'])

PRINCIPAL_TYPES = {'user': 'User', 'group': 'Group', 'servicePrincipal': 'Service principal'}

ROLE_FIELDS = register('roles', {
    'displayName': F('Name', 'text'),
    'isBuiltIn': F('Built-in', 'bool'),
    'activeCount': F('Active assignments', 'number'),
    'eligibleCount': F('Eligible assignments', 'number'),
})

ASSIGNMENT_FIELDS = register('role-assignments', {
    'role': F('Role', 'enum'),
    'principalType': F('Principal type', 'enum', labels=PRINCIPAL_TYPES),
    'kind': F('Assignment', 'enum', labels={'active': 'Active', 'eligible': 'Eligible'}),
    'scopeType': F('Scope', 'enum', labels={'Directory': 'Directory', 'Administrative unit': 'Administrative unit', 'Application': 'Application'}),
    'principalEnabled': F('Principal enabled', 'bool'),
    'viaGroup': F('Through a group', 'bool'),
})


@router.get('/roles')
def list_roles(q: Annotated[RoleQuery, Query()], db: Db) -> Page[RoleRow]:
    raise NotImplementedError


@router.get('/roles/{id}')
def get_role(id: str, db: Db) -> RoleDetail:
    """`id` is the role template id."""
    raise NotImplementedError


@router.get('/role-assignments')
def list_role_assignments(q: Annotated[RoleAssignmentQuery, Query()], db: Db) -> Page[RoleAssignmentRow]:
    raise NotImplementedError


# --- Shared with other slices (counts on object pages); 0 until implemented ---

def count_roles(db: Session, principal_id: str) -> int:
    """Directory role assignments (active and eligible) of a user, group or SP, direct and through groups."""
    return 0


def count_scoped_roles(db: Session, scope_id: str) -> int:
    """Role assignments scoped to an administrative unit or application."""
    return 0
