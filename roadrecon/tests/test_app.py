import json
from pathlib import Path

import pytest

from roadtools.roadrecon.api.common import FIELDS

OPENAPI = Path(__file__).resolve().parent.parent / 'frontend-react' / 'openapi.json'


def test_openapi_matches_committed_spec(app):
    """The frontend types are generated from openapi.json: a spec change must re-export it (see types.ts)."""
    assert app.openapi() == json.loads(OPENAPI.read_text())


@pytest.mark.parametrize('resource', sorted(r for r in FIELDS if not r.startswith('test-')))
def test_filter_catalogue(client, resource):
    fields = client.get(f'/api/filters/{resource}').json()
    assert fields and all(f['type'] != 'enum' or f['options'] is not None for f in fields)


def test_unknown_resource(client):
    assert client.get('/api/filters/nope').status_code == 422


def test_minimal_db_starts(minimal_client):
    assert minimal_client.get('/api/filters/users').status_code == 200


@pytest.mark.parametrize('url', ['/api/users?filter=lastPasswordChangeDateTime:gt:2020-01-01',
                                 '/api/groups?filter=createdDateTime:lt:2030-01-01T00:00:00Z'])
def test_date_filters_accept_plain_dates(client, url):
    r = client.get(url)
    assert r.status_code == 200 and r.json()['total'] > 0
