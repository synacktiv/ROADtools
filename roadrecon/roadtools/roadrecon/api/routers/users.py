"""S1 users: /api/users (incl. the MFA view filters), /api/users/{id}, /api/owners."""
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import Select
from sqlalchemy.orm import Session

from ..common import Db, F, register
from ..models import ObjectRef, OwnerQuery, Page, UserDetail, UserQuery, UserRow

router = APIRouter(prefix='/api', tags=['users'])

MFA_LABELS = {
    'PhoneAppNotification': 'Authenticator notification', 'PhoneAppOTP': 'Authenticator code', 'OneWaySms': 'Text message',
    'TwoWayVoiceMobile': 'Phone call', 'Fido': 'FIDO2 key', 'WindowsHello': 'Windows Hello',
}

FIELDS = register('users', {
    'displayName': F('Name', 'text'),
    'userPrincipalName': F('UPN', 'text'),
    'mail': F('Mail', 'text'),
    'userType': F('Type', 'enum'),
    'accountEnabled': F('Enabled', 'bool'),
    'dirSyncEnabled': F('Synced from AD', 'bool'),
    'department': F('Department', 'enum'),
    'jobTitle': F('Job title', 'enum'),
    'mobile': F('Mobile', 'text'),
    'lastPasswordChangeDateTime': F('Password changed', 'date'),
    'mfaMethod': F('MFA method', 'enum', labels=MFA_LABELS),
    'hasMfa': F('Has MFA', 'bool'),
    'perUserMfa': F('Per-user MFA', 'enum'),
})


@router.get('/users')
def list_users(q: Annotated[UserQuery, Query()], db: Db) -> Page[UserRow]:
    raise NotImplementedError


@router.get('/users/{id}')
def get_user(id: str, db: Db) -> UserDetail:
    raise NotImplementedError


@router.get('/owners')
def list_owners(q: Annotated[OwnerQuery, Query()], db: Db) -> Page[ObjectRef]:
    """Owners of any object: users and service principals."""
    raise NotImplementedError


# --- Shared with other slices --------------------------------------------------

def page_users(db: Session, q: UserQuery, within: Select | None = None) -> Page[UserRow]:
    """The users list with every UserQuery filter, optionally restricted to the ids of `within`
    (a one-column select of user ids). Used by /api/users and /api/policies/{id}/users."""
    raise NotImplementedError
