import pytest
from fastapi import HTTPException
from sqlalchemy import insert, select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api import common as c
from roadtools.roadrecon.api.db import ensure_indexes, make_engine, make_sessionmaker
from roadtools.roadrecon.api.models import PageQuery


@pytest.fixture(scope='module')
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp('db') / 'roadrecon.db'
    d.init(create=True, dburl=f'sqlite:///{path}')
    engine = make_engine(str(path))
    ensure_indexes(engine)
    with make_sessionmaker(engine)() as s:
        s.add_all([
            d.User(objectId='u1', displayName='Alice', userPrincipalName='alice@x', accountEnabled=True, department='IT',
                   strongAuthenticationDetail={'methods': [{'methodType': 'PhoneAppOTP', 'isDefault': False},
                                                           {'methodType': 'PhoneAppNotification', 'isDefault': True}],
                                               'requirements': [{'state': 'Enforced'}]},
                   searchableDeviceKey=[{'usage': 'FIDO'}, {'usage': 'NGC'}, {'usage': 'NGC'}]),
            d.User(objectId='u2', displayName='Bob_1', userPrincipalName='bob@x', accountEnabled=False),
            d.User(objectId='u3', displayName='Carol', userPrincipalName='carol@x', accountEnabled=None, department='HR'),
            d.Group(objectId='g1', displayName='Top'), d.Group(objectId='g2', displayName='Mid'),
            d.Group(objectId='g3', displayName='Leaf'),
            d.ServicePrincipal(objectId='sp1', displayName='Graph', appId='app-graph'),
            d.RoleDefinition(objectId='r1', templateId='r1', displayName='Global Administrator'),
            d.DirectoryRole(objectId='dr1', roleTemplateId='r1', displayName='Global Administrator'),
            d.Policy(objectId='p1', displayName='Block legacy', policyType=18),
        ])
        s.execute(insert(d.lnk_group_member_group), [{'Group': 'g1', 'childGroup': 'g2'}, {'Group': 'g2', 'childGroup': 'g3'},
                                                     {'Group': 'g3', 'childGroup': 'g1'}])  # cycle
        s.execute(insert(d.lnk_group_member_user), [{'Group': 'g3', 'User': 'u1'}, {'Group': 'g1', 'User': 'u2'}])
        s.commit()
        yield s
    engine.dispose()


USER_FIELDS = {
    'displayName': c.F('Name', 'text', col=d.User.displayName),
    'accountEnabled': c.F('Enabled', 'bool', col=d.User.accountEnabled),
    'department': c.F('Department', 'enum', col=d.User.department),
}
c.register('test-users', USER_FIELDS)


def names(page):
    return [u.displayName for u in page.items]


def page(db, **kw):
    return c.paginate(db, select(d.User), PageQuery(**kw), resource='test-users', search=[d.User.displayName],
                      sorts={'displayName': d.User.displayName})


def test_paginate_sort_count_slice(db):
    p = page(db, page_size=2)
    assert p.total == 3 and names(p) == ['Alice', 'Bob_1']
    assert names(page(db, page=2, page_size=2)) == ['Carol']
    assert names(page(db, order='desc')) == ['Carol', 'Bob_1', 'Alice']


def test_search_escapes_like(db):
    assert names(page(db, q='b_')) == ['Bob_1']
    assert names(page(db, q='%')) == []
    assert names(page(db, q='ALI')) == ['Alice']


def test_filters(db):
    assert names(page(db, filter=['accountEnabled:eq:false'])) == ['Bob_1', 'Carol']  # null counts as false
    assert names(page(db, filter=['accountEnabled:eq:true'])) == ['Alice']
    assert names(page(db, filter=['department:in:IT,HR'])) == ['Alice', 'Carol']
    assert names(page(db, filter=['department:notIn:IT'])) == ['Bob_1', 'Carol']
    assert names(page(db, filter=['department:empty:'])) == ['Bob_1']
    assert names(page(db, filter=['displayName:startsWith:a', 'department:eq:hr'], match='any')) == ['Alice', 'Carol']
    assert names(page(db, filter=['displayName:notContains:o'])) == ['Alice']


@pytest.mark.parametrize('bad', [['nope:eq:1'], ['displayName:like:x']])
def test_unknown_filter_is_422(db, bad):
    with pytest.raises(HTTPException) as e:
        page(db, filter=bad)
    assert e.value.status_code == 422


def test_unknown_sort_is_422(db):
    with pytest.raises(HTTPException):
        page(db, sort='nope')


def test_catalog_enum_options(db):
    cat = {f.key: f for f in c.catalog(db, 'test-users')}
    assert [o.value for o in cat['department'].options] == ['HR', 'IT']
    assert cat['displayName'].options is None


def test_paginate_list():
    c.register('test-list', {'n': c.F('N', 'number', get=lambda r: r['n']), 'tags': c.F('Tags', 'enum', get=lambda r: r['tags'])})
    rows = [{'n': i, 'tags': ['a'] if i % 2 else ['b', 'c']} for i in range(5)]
    p = c.paginate_list(rows, PageQuery(filter=['tags:in:c', 'n:gt:1'], sort='n', order='desc'), resource='test-list',
                        sorts={'n': lambda r: r['n']})
    assert [r['n'] for r in p.items] == [4, 2] and p.total == 2


def test_resolve_refs(db):
    refs = c.resolve_refs(db, ['u1', 'g1', 'sp1', 'r1', 'dr1', 'p1', 'gone', None])
    assert (refs['u1'].type, refs['u1'].sub) == ('user', 'alice@x')
    assert (refs['sp1'].type, refs['sp1'].sub) == ('servicePrincipal', 'app-graph')
    assert refs['r1'].type == 'role' and refs['dr1'].id == 'r1'
    assert refs['p1'].type == 'policy'
    assert refs['gone'].type == 'unknown'
    assert c.resolve_appids(db, ['app-graph', 'nope'])['app-graph'].id == 'sp1'


def test_group_ctes_handle_cycles(db):
    desc = c.descendant_groups('g2')
    assert set(db.scalars(select(desc.c.id))) == {'g1', 'g2', 'g3'}
    anc = c.transitive_groups_of('u1')
    assert set(db.scalars(select(anc.c[0]))) == {'g1', 'g2', 'g3'}


def test_mfa_summary(db):
    m = c.mfa_summary(db.get(d.User, 'u1'))
    assert m == {'methods': ['PhoneAppOTP', 'PhoneAppNotification'], 'defaultMethod': 'PhoneAppNotification',
                 'perUserMfa': 'Enforced', 'fido': 1, 'windowsHello': 2}
    assert c.mfa_summary(db.get(d.User, 'u2'))['methods'] == []


def test_privileged_permission():
    assert c.is_privileged_permission('RoleManagement.ReadWrite.Directory')
    assert c.is_privileged_permission('Sites.FullControl.All')
    assert not c.is_privileged_permission('User.Read')


def test_read_only_engine(tmp_path):
    path = tmp_path / 'ro.db'
    d.init(create=True, dburl=f'sqlite:///{path}')
    path.chmod(0o444)
    engine = make_engine(str(path), read_only=True)
    with make_sessionmaker(engine)() as s:
        assert s.scalar(select(d.User.objectId)) is None
