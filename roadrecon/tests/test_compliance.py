"""Device compliance routes (Intune), on gendb data, and on dumps without compliance data."""
import shutil
import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.app import create_app
from roadtools.roadrecon.api.models import CompliancePolicyDetail, CompliancePolicyRow, DeviceComplianceSettings, Page, Stats


def get(client, url, **params):
    r = client.get(url, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def policies(client, **params):
    return Page[CompliancePolicyRow](**get(client, '/api/device-compliance', page_size=500, **params))


def by_name(client):
    return {r.displayName: r for r in policies(client).items}


def group_id(db, name):
    return db.scalar(select(d.Group.objectId).where(d.Group.displayName == name))


def test_list(client, db):
    p = policies(client)
    assert p.total == len(p.items) == db.query(d.DeviceCompliancePolicy).count() == 5
    rows = by_name(client)
    assert {r.platform for r in rows.values()} == {
        'Windows 10/11', 'iOS/iPadOS', 'Android Enterprise (work profile)', 'macOS'}
    win = rows['Windows 10/11 baseline']
    assert [(a.type, a.id, a.displayName) for a in win.assignments] == [('group', group_id(db, 'All Staff'), 'All Staff')]
    assert [(a.type, a.id) for a in win.exclusions] == [('group', group_id(db, 'Contractors'))]
    assert win.gracePeriodHours == 72 and win.lastModifiedDateTime
    assert [(a.type, a.displayName) for a in rows['iOS corporate devices'].assignments] == [('keyword', 'All users')]
    mac = rows['macOS FileVault']
    assert [(a.type, a.displayName) for a in mac.assignments] == [('keyword', 'All devices')]
    assert [a.type for a in mac.exclusions] == ['unknown'] and mac.gracePeriodHours == 0
    assert len(rows['Android work profile'].assignments) == 2
    legacy = rows['Windows 10/11 legacy (unassigned)']
    assert legacy.assignments == [] and legacy.gracePeriodHours is None


def test_platform_filter_search_sort(client):
    assert {r.displayName for r in policies(client, platform='Windows 10/11').items} == {
        'Windows 10/11 baseline', 'Windows 10/11 legacy (unassigned)'}
    assert [r.displayName for r in policies(client, platform='ios').items] == ['iOS corporate devices']
    assert policies(client, filter='platform:eq:macOS').total == 1
    assert policies(client, q='filevault').total == 1
    names = [r.displayName for r in policies(client, sort='displayName', order='desc').items]
    assert names == sorted(names, key=str.lower, reverse=True)
    assert policies(client, sort='gracePeriodHours').items[0].gracePeriodHours == 0
    assert client.get('/api/device-compliance', params={'sort': 'nope'}).status_code == 422
    assert {o['label'] for o in get(client, '/api/filters/device-compliance')[1]['options']} >= {'macOS', 'iOS/iPadOS'}


def test_detail(client):
    row = by_name(client)['Android work profile']
    p = CompliancePolicyDetail(**get(client, f'/api/device-compliance/{row.id}'))
    assert p.model_dump(include=set(CompliancePolicyRow.model_fields)) == row.model_dump()
    assert p.version == 2 and p.createdDateTime and p.raw['id'] == row.id
    assert [(a.actionType, a.gracePeriodHours) for a in p.actions] == [('block', 24), ('notification', 0), ('retire', 720)]
    assert p.actions[1].notificationTemplateId
    settings = {s.name: s.value for s in p.settings}
    assert settings['passwordMinimumLength'] == 6 and settings['securityBlockJailbrokenDevices'] is True
    assert not {'@odata.type', 'id', 'displayName', 'version', 'roleScopeTagIds'} & settings.keys()
    win = by_name(client)['Windows 10/11 baseline']
    names = {s.name for s in CompliancePolicyDetail(**get(client, f'/api/device-compliance/{win.id}')).settings}
    assert 'bitLockerEnabled' in names and 'osMaximumVersion' not in names  # null values left out
    assert client.get('/api/device-compliance/nope').status_code == 404


def test_settings_and_stats(client):
    s = DeviceComplianceSettings(**get(client, '/api/device-compliance/settings'))
    assert s == DeviceComplianceSettings(noPolicyDevicesCompliant=True, checkinThresholdDays=30,
                                         enhancedJailBreak=False, isScheduledActionEnabled=True)
    assert Stats(**get(client, '/api/stats')).compliancePolicies == 5


def assert_not_collected(c):
    assert get(c, '/api/device-compliance') == {'items': [], 'total': 0, 'page': 1, 'page_size': 50}
    assert get(c, '/api/device-compliance', platform='ios', filter='platform:eq:iOS/iPadOS')['total'] == 0
    assert get(c, '/api/device-compliance/settings') is None
    assert Stats(**get(c, '/api/stats')).compliancePolicies is None
    assert get(c, '/api/filters/device-compliance')[1]['options'] == []
    assert c.get('/api/device-compliance/nope').status_code == 404


def test_tables_missing(minimal_client):
    assert_not_collected(minimal_client)


def test_tables_empty(dbpath, tmp_path):
    """Tables present but empty (no compliancegather run on a roadlib that has them): same as missing."""
    path = tmp_path / 'empty.db'
    shutil.copy(dbpath, path)
    with sqlite3.connect(path) as conn:
        conn.executescript('DELETE FROM DeviceCompliancePolicyAssignments; DELETE FROM DeviceCompliancePolicys; '
                           'DELETE FROM DeviceManagementSettings;')
    with TestClient(create_app(str(path))) as c:
        assert_not_collected(c)
