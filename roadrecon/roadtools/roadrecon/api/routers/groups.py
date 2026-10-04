"""S2 groups: /api/groups, /api/groups/{id}."""
from typing import Annotated

from fastapi import APIRouter, Query

from ..common import Db, F, register
from ..models import GroupDetail, GroupQuery, GroupRow, Page

router = APIRouter(prefix='/api', tags=['groups'])

FIELDS = register('groups', {
    'displayName': F('Name', 'text'),
    'description': F('Description', 'text'),
    'mail': F('Mail', 'text'),
    'kind': F('Type', 'enum', labels={'Microsoft 365': 'Microsoft 365', 'Distribution': 'Distribution', 'Security': 'Security'}),
    'isAssignableToRole': F('Role assignable', 'bool'),
    'dynamic': F('Dynamic membership', 'bool'),
    'membershipRule': F('Membership rule', 'text'),
    'isPublic': F('Public', 'bool'),
    'dirSyncEnabled': F('Synced from AD', 'bool'),
    'createdDateTime': F('Created', 'date'),
})


@router.get('/groups')
def list_groups(q: Annotated[GroupQuery, Query()], db: Db) -> Page[GroupRow]:
    raise NotImplementedError


@router.get('/groups/{id}')
def get_group(id: str, db: Db) -> GroupDetail:
    raise NotImplementedError
