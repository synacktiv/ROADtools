"""Shared fixtures: one synthetic roadrecon.db (tests/gendb.py) per session, plus a minimal one without PIM/IG/AZ."""
import pytest
from fastapi.testclient import TestClient

from gendb import generate
from roadtools.roadrecon.api.app import create_app


@pytest.fixture(scope='session')
def dbpath(tmp_path_factory):
    path = tmp_path_factory.mktemp('gendb') / 'roadrecon.db'
    generate(str(path))
    return path


@pytest.fixture(scope='session')
def app(dbpath):
    return create_app(str(dbpath))


@pytest.fixture(scope='session')
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(app):
    """ORM session on the same database, to compute expected values."""
    with app.state.sessionmaker() as s:
        yield s


@pytest.fixture(scope='session')
def minimal_client(tmp_path_factory):
    path = tmp_path_factory.mktemp('gendb-min') / 'roadrecon.db'
    generate(str(path), minimal=True)
    with TestClient(create_app(str(path))) as c:
        yield c
