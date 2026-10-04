"""Database access for the GUI API: engine, sessions and the indexes it relies on (ADR 0002)."""
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from roadtools.roadlib.metadef import database

# table -> indexed columns. Created only when the table exists, never altered.
INDEXES = {
    'lnk_group_member_user': ['Group', 'User'],
    'lnk_group_member_group': ['Group', 'childGroup'],
    'lnk_group_member_device': ['Group', 'Device'],
    'lnk_group_member_serviceprincipal': ['Group', 'ServicePrincipal'],
    'lnk_group_member_contact': ['Group', 'Contact'],
    'lnk_group_owner_user': ['Group', 'User'],
    'lnk_group_owner_serviceprincipal': ['Group', 'ServicePrincipal'],
    'lnk_device_owner': ['Device', 'User'],
    'lnk_application_owner_user': ['Application', 'User'],
    'lnk_application_owner_serviceprincipal': ['Application', 'ServicePrincipal'],
    'lnk_serviceprincipal_owner_user': ['ServicePrincipal', 'User'],
    'lnk_serviceprincipal_owner_serviceprincipal': ['ServicePrincipal', 'childServicePrincipal'],
    'lnk_role_member_user': ['DirectoryRole', 'User'],
    'lnk_role_member_group': ['DirectoryRole', 'Group'],
    'lnk_role_member_serviceprincipal': ['DirectoryRole', 'ServicePrincipal'],
    'lnk_au_member_user': ['AdministrativeUnit', 'User'],
    'lnk_au_member_group': ['AdministrativeUnit', 'Group'],
    'lnk_au_member_device': ['AdministrativeUnit', 'Device'],
    'AppRoleAssignments': ['principalId', 'resourceId'],
    'OAuth2PermissionGrants': ['clientId', 'resourceId', 'principalId'],
    'RoleAssignments': ['principalId', 'roleDefinitionId'],
    'EligibleRoleAssignments': ['principalId', 'roleDefinitionId'],
    'ServicePrincipals': ['appId'],
    'Applications': ['appId'],
    'Policys': ['policyType'],
    'PIMgovernanceRoleAssignments': ['subjectId', 'resourceId'],
    'AZroleAssignments': ['principal_id'],
    'AZroleEligibilityScheduleInstances': ['principal_id'],
}


def make_engine(dburl: str, read_only: bool = False) -> Engine:
    """Engine on an existing roadrecon database. Never creates or drops tables."""
    dburl = database.parse_db_argument(dburl)
    if dburl.startswith('sqlite:///'):
        if read_only:
            # mode=ro also works on files the process cannot write.
            engine = create_engine('sqlite:///file:' + dburl[len('sqlite:///'):] + '?mode=ro&uri=true')
        else:
            engine = create_engine(dburl)

        @event.listens_for(engine, 'connect')
        def _pragmas(conn, _):
            cur = conn.cursor()
            cur.execute('PRAGMA cache_size=-65536')
            cur.execute('PRAGMA temp_store=MEMORY')
            if read_only:
                cur.execute('PRAGMA query_only=ON')
            cur.close()
        return engine
    return database.init(create=False, dburl=dburl)


def ensure_indexes(engine: Engine) -> None:
    """Additive `CREATE INDEX IF NOT EXISTS` on the tables present. Safe to run on every start."""
    tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        for table, cols in INDEXES.items():
            if table not in tables:
                continue
            for col in cols:
                conn.execute(text(f'CREATE INDEX IF NOT EXISTS "ix_{table}_{col}" ON "{table}" ("{col}")'))


def make_sessionmaker(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
