"""SQL query page: read-only SQL against the dump, on a dedicated SQLite connection."""
import sqlite3
import time
from itertools import groupby
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request

from ..common import PRIVILEGED_ROLES
from ..models import SqlExample, SqlQuery, SqlResult, SqlSchema, SqlTable

router = APIRouter(prefix='/api', tags=['sql'])

MAX_ROWS = 1000
TIMEOUT = 10.0  # seconds

_PRIV = ', '.join(f"'{t}'" for t in sorted(PRIVILEGED_ROLES))
_ROLE_HOLDERS = '''SELECT coalesce(rd.displayName, a.roleDefinitionId) AS role, '{kind}' AS kind,
  coalesce(u.displayName, g.displayName, sp.displayName, a.principalId) AS principal,
  CASE WHEN u.objectId IS NOT NULL THEN 'User' WHEN g.objectId IS NOT NULL THEN 'Group'
       WHEN sp.objectId IS NOT NULL THEN 'ServicePrincipal' END AS principalType,
  u.userPrincipalName, coalesce(u.dirSyncEnabled, g.dirSyncEnabled) AS synced
FROM {table} a
LEFT JOIN RoleDefinitions rd ON rd.objectId = a.roleDefinitionId
LEFT JOIN Users u ON u.objectId = a.principalId
LEFT JOIN Groups g ON g.objectId = a.principalId
LEFT JOIN ServicePrincipals sp ON sp.objectId = a.principalId
WHERE coalesce(rd.templateId, a.roleDefinitionId) IN ({priv})'''

QUERIES = [
    SqlExample(name='Users without MFA', description='Enabled users with no strong authentication method, FIDO key or Windows Hello.', sql='''\
SELECT displayName, userPrincipalName, userType, dirSyncEnabled, lastPasswordChangeDateTime
FROM Users
WHERE accountEnabled = 1
  AND coalesce(strongAuthenticationDetail, '') NOT LIKE '%"methodType"%'
  AND coalesce(searchableDeviceKey, '') NOT LIKE '%"FIDO"%'
  AND coalesce(searchableDeviceKey, '') NOT LIKE '%"NGC"%'
ORDER BY displayName'''),
    SqlExample(name='Guest users', description='External users, newest first.', sql='''\
SELECT displayName, mail, userPrincipalName, accountEnabled, acceptedAs, createdDateTime
FROM Users
WHERE userType = 'Guest'
ORDER BY createdDateTime DESC'''),
    SqlExample(name='Privileged role holders', description='Active and eligible assignments of tier-0 directory roles.',
               sql=_ROLE_HOLDERS.format(kind='active', table='RoleAssignments', priv=_PRIV) + '\nUNION ALL\n'
               + _ROLE_HOLDERS.format(kind='eligible', table='EligibleRoleAssignments', priv=_PRIV)
               + '\nORDER BY role, principal'),
    SqlExample(name='Stale passwords', description='Enabled users whose password is more than a year old.', sql='''\
SELECT displayName, userPrincipalName, dirSyncEnabled, lastPasswordChangeDateTime
FROM Users
WHERE accountEnabled = 1 AND lastPasswordChangeDateTime < datetime('now', '-1 year')
ORDER BY lastPasswordChangeDateTime'''),
    SqlExample(name='Service principals with credentials', description='Secrets and certificates set on service principals.', sql='''\
SELECT displayName, appId, publisherName, microsoftFirstParty,
  json_array_length(passwordCredentials) AS passwords, json_array_length(keyCredentials) AS keys
FROM ServicePrincipals
WHERE json_array_length(passwordCredentials) > 0 OR json_array_length(keyCredentials) > 0
ORDER BY passwords DESC, keys DESC'''),
    SqlExample(name='Applications with credentials', description='Secrets and certificates set on app registrations.', sql='''\
SELECT displayName, appId, availableToOtherTenants,
  json_array_length(passwordCredentials) AS passwords, json_array_length(keyCredentials) AS keys
FROM Applications
WHERE json_array_length(passwordCredentials) > 0 OR json_array_length(keyCredentials) > 0
ORDER BY passwords DESC, keys DESC'''),
    SqlExample(name='Application redirect URIs', description='One row per redirect URI; plain http and localhost first.', sql='''\
SELECT a.displayName, a.appId, r.value AS redirectUri,
  r.value LIKE 'http:%' OR r.value LIKE '%localhost%' AS suspicious
FROM Applications a, json_each(a.replyUrls) r
ORDER BY suspicious DESC, a.displayName'''),
    SqlExample(name='Application permissions', description='App roles granted to service principals (app-only access).', sql='''\
SELECT a.principalDisplayName AS client, a.resourceDisplayName AS resource,
  coalesce(json_extract(r.value, '$.value'), a.id) AS permission, a.creationTimestamp
FROM AppRoleAssignments a
LEFT JOIN ServicePrincipals sp ON sp.objectId = a.resourceId
LEFT JOIN json_each(sp.appRoles) r ON json_extract(r.value, '$.id') = a.id
WHERE a.principalType = 'ServicePrincipal'
ORDER BY client, resource'''),
    SqlExample(name='Tenant-wide delegated grants', description='OAuth2 grants consented for all users.', sql='''\
SELECT c.displayName AS client, r.displayName AS resource, g.scope, g.expiryTime
FROM OAuth2PermissionGrants g
LEFT JOIN ServicePrincipals c ON c.objectId = g.clientId
LEFT JOIN ServicePrincipals r ON r.objectId = g.resourceId
WHERE g.consentType = 'AllPrincipals'
ORDER BY client'''),
    SqlExample(name='Service principal owners', description='Users who own a service principal and can add credentials to it.', sql='''\
SELECT sp.displayName AS servicePrincipal, sp.appId, u.displayName AS owner, u.userPrincipalName
FROM lnk_serviceprincipal_owner_user l
JOIN ServicePrincipals sp ON sp.objectId = l.ServicePrincipal
JOIN Users u ON u.objectId = l.User
ORDER BY servicePrincipal'''),
    SqlExample(name='Dynamic groups', description='Membership rules, which users may be able to satisfy themselves.', sql='''\
SELECT displayName, membershipRule, isAssignableToRole, securityEnabled
FROM Groups
WHERE membershipRule IS NOT NULL
ORDER BY displayName'''),
]


def _deny_attach(action, *_):
    # ATTACH would read (or, on a writable connection, create) any SQLite file on the server.
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK


def _connect(request: Request) -> sqlite3.Connection:
    """A new read-only connection, never the pooled ones: `mode=ro` plus `query_only`, ATTACH denied."""
    engine = request.app.state.engine
    if engine.dialect.name != 'sqlite':
        raise HTTPException(501, 'SQL queries are only supported on SQLite databases')
    path = engine.url.database.removeprefix('file:')  # the read-only engine uses a file: URI
    con = sqlite3.connect(f'file:{quote(path)}?mode=ro', uri=True)
    con.execute('PRAGMA query_only=ON')
    con.set_authorizer(_deny_attach)
    return con


@router.post('/sql')
def run_sql(body: SqlQuery, request: Request) -> SqlResult:
    con = _connect(request)
    start = time.monotonic()
    deadline = start + TIMEOUT
    con.set_progress_handler(lambda: time.monotonic() > deadline, 10_000)
    try:
        cur = con.execute(body.sql)
        columns = [c[0] for c in cur.description or []]
        rows = cur.fetchmany(MAX_ROWS + 1)
    except sqlite3.Error as e:
        if time.monotonic() > deadline:
            raise HTTPException(400, f'Query stopped after {TIMEOUT:g} s')
        raise HTTPException(400, str(e))
    finally:
        con.close()
    return SqlResult(
        columns=columns,
        rows=[[v.hex() if isinstance(v, bytes) else v for v in r] for r in rows[:MAX_ROWS]],
        truncated=len(rows) > MAX_ROWS,
        elapsedMs=round((time.monotonic() - start) * 1000),
    )


@router.get('/sql/schema')
def sql_schema(request: Request) -> SqlSchema:
    con = _connect(request)
    try:
        cols = con.execute("SELECT m.name, p.name FROM sqlite_master m, pragma_table_info(m.name) p "
                           "WHERE m.type IN ('table', 'view') AND m.name NOT LIKE 'sqlite_%' ORDER BY m.name, p.cid").fetchall()
    finally:
        con.close()
    return SqlSchema(tables=[SqlTable(name=t, columns=[c for _, c in g]) for t, g in groupby(cols, key=lambda r: r[0])],
                     queries=QUERIES)
