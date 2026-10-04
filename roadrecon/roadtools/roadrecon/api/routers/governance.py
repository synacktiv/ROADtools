"""S8 governance: Azure RBAC, PIM and access packages. Tables may be missing: return empty results then."""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from ..common import Db, F, register
from ..models import (AccessPackagePolicyQuery, AccessPackagePolicyRow, AzureRoleAssignmentQuery,
                      AzureRoleAssignmentRow, GroupPim, Page, PimAssignmentQuery, PimAssignmentRow)

router = APIRouter(prefix='/api', tags=['governance'])

KINDS = {'active': 'Active', 'eligible': 'Eligible'}

AZURE_FIELDS = register('azure-role-assignments', {
    'role': F('Role', 'text'),
    'kind': F('Assignment', 'enum', labels=KINDS),
    'scopeType': F('Scope level', 'enum', labels={'managementGroup': 'Management group', 'subscription': 'Subscription',
                                                   'resourceGroup': 'Resource group', 'resource': 'Resource'}),
    'viaGroup': F('Through a group', 'bool'),
    'conditional': F('Conditional', 'bool'),
})

PIM_FIELDS = register('pim-assignments', {
    'role': F('Role', 'text'),
    'resourceType': F('Resource', 'enum', labels={'directoryRole': 'Directory role', 'group': 'Group', 'other': 'Other'}),
    'kind': F('Assignment', 'enum', labels=KINDS),
    'approvalRequired': F('Approval required', 'bool'),
    'permanent': F('Permanent', 'bool'),
})

ACCESS_PACKAGE_FIELDS = register('access-package-policies', {
    'packageName': F('Access package', 'text'),
    'approvalRequired': F('Approval required', 'bool'),
    'renewable': F('Renewable', 'bool'),
})


@router.get('/azure-role-assignments')
def list_azure_role_assignments(q: Annotated[AzureRoleAssignmentQuery, Query()], db: Db) -> Page[AzureRoleAssignmentRow]:
    raise NotImplementedError


@router.get('/pim-assignments')
def list_pim_assignments(q: Annotated[PimAssignmentQuery, Query()], db: Db) -> Page[PimAssignmentRow]:
    raise NotImplementedError


@router.get('/groups/{id}/pim')
def get_group_pim(id: str, db: Db) -> GroupPim | None:
    """PIM for Groups settings and assignments; null when the group is not onboarded."""
    raise NotImplementedError


@router.get('/access-package-policies')
def list_access_package_policies(q: Annotated[AccessPackagePolicyQuery, Query()], db: Db) -> Page[AccessPackagePolicyRow]:
    """Access package policies the user can request, directly or through a group."""
    raise NotImplementedError


# --- Shared with other slices (counts on object pages); 0 until implemented ---

def count_azure_roles(db: Session, principal_id: str) -> int:
    """Azure role assignments (active and eligible), direct and through groups."""
    return 0


def count_pim(db: Session, principal_id: str) -> int:
    """PIM assignments, direct and through groups."""
    return 0


def count_access_packages(db: Session, user_id: str) -> int:
    """Access package policies the user can request."""
    return 0
