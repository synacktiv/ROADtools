import pytest

from roadtools.roadrecon.api.routers import sql


def run(client, query):
    return client.post('/api/sql', json={'sql': query})


def test_select(client, db):
    from roadtools.roadlib.metadef import database as d
    r = run(client, 'SELECT count(*) AS n, 1 AS one FROM Users')
    assert r.status_code == 200
    body = r.json()
    assert body['columns'] == ['n', 'one']
    assert body['rows'] == [[db.query(d.User).count(), 1]] and body['truncated'] is False


@pytest.mark.parametrize('query', [
    'DELETE FROM Users',
    'DROP TABLE Users',
    "INSERT INTO Users (objectId) VALUES ('x')",
    'CREATE TABLE t (x)',
    "ATTACH DATABASE '/tmp/rr-sql-test.db' AS x",
])
def test_read_only(client, query):
    r = run(client, query)
    assert r.status_code == 400 and r.json()['detail']
    assert run(client, 'SELECT count(*) FROM Users').json()['rows'][0][0] > 0


def test_one_statement_only(client):
    assert run(client, 'PRAGMA query_only=OFF; DELETE FROM Users').status_code == 400


def test_bad_sql(client):
    r = run(client, 'SELECT nope FROM Users')
    assert r.status_code == 400 and 'nope' in r.json()['detail']


def test_row_cap(client, monkeypatch):
    monkeypatch.setattr(sql, 'MAX_ROWS', 5)
    body = run(client, 'WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c LIMIT 6) SELECT x FROM c').json()
    assert body['rows'] == [[1], [2], [3], [4], [5]] and body['truncated'] is True
    assert run(client, 'SELECT 1 UNION ALL SELECT 2').json()['truncated'] is False


def test_timeout(client, monkeypatch):
    monkeypatch.setattr(sql, 'TIMEOUT', 0.2)
    r = run(client, 'WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT count(*) FROM c')
    assert r.status_code == 400 and 'stopped' in r.json()['detail']


def test_schema(client):
    body = client.get('/api/sql/schema').json()
    tables = {t['name']: t['columns'] for t in body['tables']}
    assert 'userPrincipalName' in tables['Users'] and tables['lnk_group_member_user'] == ['Group', 'User']


@pytest.mark.parametrize('example', sql.QUERIES, ids=lambda q: q.name)
def test_builtin_queries_run(client, example):
    r = run(client, example.sql)
    assert r.status_code == 200, r.text
