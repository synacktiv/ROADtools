"""Smoke test for the synthetic roadrecon.db generator (roadrecon/tests/gendb.py)."""
import os
import sys

from sqlalchemy import func

import roadtools.roadlib.metadef.database as database
from roadtools.roadlib.metadef.database import (
    Policy, RoleAssignment, User, lnk_group_member_user, lnk_policy_user_exclude)

sys.path.insert(0, os.path.dirname(__file__))
import gendb  # noqa: E402


def test_generate(tmp_path):
    path = str(tmp_path / 'roadrecon.db')
    gendb.generate(path, users=50, seed=1)
    session = database.get_session(database.init(dburl=database.parse_db_argument(path)))

    assert session.query(func.count(User.objectId)).scalar() == 50
    # Seven Conditional Access policies (policyType 18) plus named locations (type 6).
    assert session.query(func.count(Policy.objectId)).where(Policy.policyType == 18).scalar() == 7
    assert session.query(func.count(Policy.objectId)).where(Policy.policyType == 6).scalar() == 3
    # Directory role assignments and link rows got populated.
    assert session.query(func.count(RoleAssignment.id)).scalar() >= 3
    assert session.query(func.count()).select_from(lnk_group_member_user).scalar() > 0
    # policyanalysis filled the policy exclusion link table.
    assert session.query(func.count()).select_from(lnk_policy_user_exclude).scalar() > 0
    session.close()


def test_minimal_has_no_governance_tables(tmp_path):
    path = str(tmp_path / 'roadrecon.db')
    gendb.generate(path, users=20, seed=1, minimal=True)
    engine = database.init(dburl=database.parse_db_argument(path))
    from sqlalchemy import inspect
    tables = set(inspect(engine).get_table_names())
    assert not any(t.startswith(('PIM', 'IG', 'AZ')) for t in tables)
    assert 'Users' in tables and 'Policys' in tables
