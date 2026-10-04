from sqlalchemy import select

from roadtools.roadlib.metadef import database as d
from roadtools.roadrecon.api.models import AdministrativeUnitDetail, AdministrativeUnitRow, DeviceDetail, DeviceRow, Page


def devices(client, **params):
    r = client.get('/api/devices', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[DeviceRow](**r.json())


def aus(client, **params):
    r = client.get('/api/administrative-units', params={'page_size': 500, **params})
    assert r.status_code == 200, r.text
    return Page[AdministrativeUnitRow](**r.json())


def ids(page):
    return {i.id for i in page.items}


def all_devices(db):
    return db.scalars(select(d.Device)).all()


def test_list_shape_paging_sort(client, db):
    rows = all_devices(db)
    p = devices(client)
    assert p.total == len(rows) == len(p.items)
    assert [i.displayName for i in p.items] == sorted((r.displayName for r in rows), key=str.lower)
    first = devices(client, page_size=5, page=2)
    assert first.total == len(rows) and [i.displayName for i in first.items] == [i.displayName for i in p.items[5:10]]
    by_os = devices(client, sort='deviceOSType', order='desc')
    assert [i.deviceOSType for i in by_os.items] == sorted((r.deviceOSType for r in rows), reverse=True)
    assert client.get('/api/devices', params={'sort': 'nope'}).status_code == 422


def test_relation_filters(client, db):
    gm, own, aum = d.lnk_group_member_device, d.lnk_device_owner, d.lnk_au_member_device
    group, dev = db.execute(select(gm.c.Group, gm.c.Device)).first()
    assert ids(devices(client, memberOf=group)) == set(db.scalars(select(gm.c.Device).where(gm.c.Group == group))) == {dev}
    user = db.scalar(select(own.c.User))
    assert ids(devices(client, ownerId=user)) == set(db.scalars(select(own.c.Device).where(own.c.User == user)))
    au = db.scalar(select(aum.c.AdministrativeUnit))
    expected = set(db.scalars(select(aum.c.Device).where(aum.c.AdministrativeUnit == au)))
    assert expected and ids(devices(client, memberOfAu=au)) == expected
    assert devices(client, memberOf='missing').total == 0


def test_toggles(client, db):
    rows = all_devices(db)
    assert ids(devices(client, isCompliant=True)) == {r.objectId for r in rows if r.isCompliant}
    assert ids(devices(client, isManaged=False)) == {r.objectId for r in rows if not r.isManaged}
    assert ids(devices(client, accountEnabled=False)) == {r.objectId for r in rows if not r.accountEnabled}
    assert ids(devices(client, deviceTrustType='ServerAd')) == {r.objectId for r in rows if r.deviceTrustType == 'ServerAd'}
    assert ids(devices(client, deviceOSType='Windows')) == {r.objectId for r in rows if r.deviceOSType == 'Windows'}


def test_advanced_filters_and_search(client, db):
    rows = all_devices(db)
    assert ids(devices(client, filter='deviceTrustType:in:AzureAd,Workplace')) == \
        {r.objectId for r in rows if r.deviceTrustType in ('AzureAd', 'Workplace')}
    assert ids(devices(client, filter='isRooted:eq:true')) == {r.objectId for r in rows if r.isRooted}
    assert ids(devices(client, filter=['displayName:startsWith:desktop', 'isCompliant:ne:true'])) == \
        {r.objectId for r in rows if r.displayName.startswith('DESKTOP') and not r.isCompliant}
    target = rows[3]
    assert ids(devices(client, q=target.deviceId.upper())) == {target.objectId}
    assert ids(devices(client, q=target.objectId)) == {target.objectId}
    assert client.get('/api/devices', params={'filter': 'nope:eq:x'}).status_code == 422

    cat = {f['key']: f for f in client.get('/api/filters/devices').json()}
    trust = {o['value']: o['label'] for o in cat['deviceTrustType']['options']}
    assert trust.items() <= {'AzureAd': 'Entra joined', 'ServerAd': 'Hybrid joined', 'Workplace': 'Registered'}.items()
    assert {o['value'] for o in cat['deviceModel']['options']} == {r.deviceModel for r in rows}


def test_device_detail(client, db):
    own = d.lnk_device_owner
    dev = next(r for r in all_devices(db) if r.bitLockerKey and db.scalar(select(own.c.User).where(own.c.Device == r.objectId)))
    r = client.get(f'/api/devices/{dev.objectId}')
    assert r.status_code == 200
    out = DeviceDetail(**r.json())
    assert out.displayName == dev.displayName and out.raw['objectId'] == dev.objectId
    assert [(k.keyIdentifier, k.keyMaterial) for k in out.bitLockerKeys] == \
        [(k['keyIdentifier'], k['keyMaterial']) for k in dev.bitLockerKey]
    assert all(k.volumeType in ('Operating system volume', 'Fixed data volume') and k.creationTime for k in out.bitLockerKeys)
    owners = set(db.scalars(select(own.c.User).where(own.c.Device == dev.objectId)))
    assert {o.id for o in out.owners} == owners and all(o.type == 'user' for o in out.owners)
    assert out.counts.owners == len(owners)
    groups = db.scalars(select(d.lnk_group_member_device.c.Group).where(d.lnk_group_member_device.c.Device == dev.objectId)).all()
    units = db.scalars(select(d.lnk_au_member_device.c.AdministrativeUnit).where(d.lnk_au_member_device.c.Device == dev.objectId)).all()
    assert (out.counts.memberOf, out.counts.administrativeUnits) == (len(groups), len(units))
    assert client.get('/api/devices/missing').status_code == 404


def test_au_list(client, db):
    rows = db.scalars(select(d.AdministrativeUnit)).all()
    p = aus(client)
    assert p.total == len(rows) and [a.displayName for a in p.items] == sorted(a.displayName for a in rows)
    dynamic = {a.objectId for a in rows if a.membershipRule}
    assert dynamic and ids(aus(client, filter='dynamic:eq:true')) == dynamic
    assert ids(aus(client, filter='dynamic:eq:false')) == {a.objectId for a in rows} - dynamic
    assert ids(aus(client, filter='dynamic:ne:true')) == {a.objectId for a in rows} - dynamic
    assert [a.displayName for a in aus(client, q='exec').items] == ['Executives']
    assert [a.displayName for a in aus(client, sort='displayName', order='desc').items] == sorted((a.displayName for a in rows), reverse=True)


def test_au_member_id(client, db):
    for table, col in ((d.lnk_au_member_user, 'User'), (d.lnk_au_member_group, 'Group'), (d.lnk_au_member_device, 'Device')):
        member = db.scalar(select(table.c[col]))
        expected = set(db.scalars(select(table.c.AdministrativeUnit).where(table.c[col] == member)))
        assert expected and ids(aus(client, memberId=member)) == expected
    assert aus(client, memberId='missing').total == 0


def test_au_detail(client, db):
    au = db.scalar(select(d.AdministrativeUnit).where(d.AdministrativeUnit.membershipRule.isnot(None)))
    out = AdministrativeUnitDetail(**client.get(f'/api/administrative-units/{au.objectId}').json())
    assert out.membershipRule == au.membershipRule and out.raw['objectId'] == au.objectId

    def count(t):
        return len(db.scalars(select(t.c.AdministrativeUnit).where(t.c.AdministrativeUnit == au.objectId)).all())
    assert (out.counts.memberUsers, out.counts.memberGroups, out.counts.memberDevices) == \
        (count(d.lnk_au_member_user), count(d.lnk_au_member_group), count(d.lnk_au_member_device))
    assert out.counts.scopedRoles >= 0  # roles.count_scoped_roles (S6)
    assert client.get('/api/administrative-units/missing').status_code == 404


def test_minimal_db(minimal_client):
    p = Page[DeviceRow](**minimal_client.get('/api/devices').json())
    assert p.total > 0
    assert minimal_client.get(f'/api/devices/{p.items[0].id}').status_code == 200
    a = Page[AdministrativeUnitRow](**minimal_client.get('/api/administrative-units').json())
    assert minimal_client.get(f'/api/administrative-units/{a.items[0].id}').status_code == 200
