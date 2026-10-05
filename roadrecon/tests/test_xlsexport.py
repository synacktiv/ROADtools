"""xlsexport plugin runs end to end on a gendb DB (MFA details lack most keys)."""
import pytest

pytest.importorskip('openpyxl')

import roadtools.roadlib.metadef.database as database  # noqa: E402
from roadtools.roadrecon.plugins.xlsexport import ExportToFilePlugin  # noqa: E402


def test_export(dbpath, tmp_path):
    session = database.get_session(database.init(dburl=database.parse_db_argument(str(dbpath))))
    ExportToFilePlugin(session, str(tmp_path / 'out.xlsx')).main()
    session.close()
    assert (tmp_path / 'out.xlsx').stat().st_size > 0
