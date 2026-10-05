"""compliancegather stores canned Graph JSON (no network), re-runs replace rows, 403 is skipped."""
from sqlalchemy import inspect

import roadtools.roadlib.metadef.database as database
from roadtools.roadlib.metadef.database import DeviceManagementSetting, DeviceCompliancePolicy, \
    DeviceCompliancePolicyAssignment
from roadtools.roadrecon import compliancegather as cg

SETTINGS = {'settings': {'secureByDefault': True, 'deviceComplianceCheckinThresholdDays': 30,
                         'enhancedJailBreak': False, 'isScheduledActionEnabled': True}}
PAGE1 = {
    'value': [{
        '@odata.type': '#microsoft.graph.windows10CompliancePolicy', 'id': 'p1', 'displayName': 'Win',
        'createdDateTime': '2024-01-02T03:04:05.1234567Z', 'lastModifiedDateTime': '2024-02-02T03:04:05Z',
        'version': 3, 'bitLockerEnabled': True,
        'assignments@odata.context': 'x',
        'assignments': [
            {'id': 'a1', 'target': {'@odata.type': '#microsoft.graph.groupAssignmentTarget', 'groupId': 'g1',
                                    'deviceAndAppManagementAssignmentFilterId': 'f1',
                                    'deviceAndAppManagementAssignmentFilterType': 'include'}},
            {'id': 'a2', 'target': {'@odata.type': '#microsoft.graph.allLicensedUsersAssignmentTarget'}},
        ],
        'scheduledActionsForRule': [{'id': 's1', 'scheduledActionConfigurations': [{'actionType': 'block', 'gracePeriodHours': 24}]}],
    }],
    '@odata.nextLink': 'next',
}
PAGE2 = {'value': [{'@odata.type': '#microsoft.graph.androidWorkProfileCompliancePolicy', 'id': 'p2',
                    'assignments': [{'id': 'a3', 'target': {'@odata.type': '#microsoft.graph.exclusionGroupAssignmentTarget', 'groupId': 'g2'}}]}]}


class Res:
    def __init__(self, status, data=None):
        self.status_code, self.data, self.text = status, data, ''

    def json(self):
        return self.data


def gather(monkeypatch, tmp_path, responses):
    monkeypatch.setattr(cg.requests, 'get', lambda url, headers: responses[url.split('/')[-1]])
    dburl = 'sqlite:///' + str(tmp_path / 'rr.db')
    cg.run({'accessToken': 'x'}, 'tenant1', dburl)
    return database.get_session(database.init(dburl=dburl))


def test_store_and_rerun(monkeypatch, tmp_path):
    ok = {'deviceManagement?$select=settings': Res(200, SETTINGS), cg.POLICIES_URL.split('/')[-1]: Res(200, PAGE1), 'next': Res(200, PAGE2)}
    gather(monkeypatch, tmp_path, ok)
    s = gather(monkeypatch, tmp_path, ok)  # re-run replaces, does not duplicate

    (setting,) = s.query(DeviceManagementSetting).all()
    assert (setting.id, setting.secureByDefault, setting.deviceComplianceCheckinThresholdDays) == ('tenant1', True, 30)
    assert setting.settings == SETTINGS['settings']

    p1, p2 = sorted(s.query(DeviceCompliancePolicy).all(), key=lambda p: p.id)
    assert (p1.platform, p2.platform) == ('windows10', 'androidWorkProfile')
    assert p1.odataType == '#microsoft.graph.windows10CompliancePolicy'
    assert p1.createdDateTime.year == 2024 and p1.version == 3
    assert p1.settings['bitLockerEnabled'] is True and '@odata.type' in p1.settings
    assert not {'assignments', 'assignments@odata.context', 'scheduledActionsForRule'} & set(p1.settings)
    assert p1.scheduledActionsForRule[0]['scheduledActionConfigurations'][0]['gracePeriodHours'] == 24

    rows = {a.id: (a.policyId, a.targetType, a.groupId, a.filterId, a.filterType) for a in s.query(DeviceCompliancePolicyAssignment)}
    assert rows == {'a1': ('p1', 'group', 'g1', 'f1', 'include'),
                    'a2': ('p1', 'allLicensedUsers', None, None, None),
                    'a3': ('p2', 'exclusionGroup', 'g2', None, None)}


def test_no_intune_skips(monkeypatch, tmp_path):
    forbidden = Res(403)
    s = gather(monkeypatch, tmp_path, {'deviceManagement?$select=settings': forbidden, cg.POLICIES_URL.split('/')[-1]: forbidden})
    assert 'DeviceCompliancePolicys' not in inspect(s.get_bind()).get_table_names()  # DB untouched, no exception
