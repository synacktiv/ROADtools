"""Authentication strengths: built-in ones resolve from a constant, custom ones (only their id is in the dump) stay
unresolved, and both count as requiring MFA (custom: approximate)."""
from gendb import AUTHSTRENGTH_CUSTOM
from roadtools.roadrecon.api.models import PolicyDetail
from roadtools.roadrecon.api.routers import policies as pol

PHISH = '00000000-0000-0000-0000-000000000004'


def by_name(client, name):
    return next(p for p in client.get('/api/policies').json()['items'] if p['displayName'] == name)


def detail(client, name):
    return PolicyDetail(**client.get(f'/api/policies/{by_name(client, name)["id"]}').json())


def test_mfa_rule():
    custom = 'c0ffee00-0000-0000-0000-000000000001'
    assert pol._mfa([{'Control': ['Mfa']}]) == (True, False)
    assert pol._mfa([{'AuthStrengthIds': [PHISH]}]) == (True, False)
    assert pol._mfa([{'AuthStrengthIds': [custom]}]) == (True, True)
    assert pol._mfa([{'AuthStrengthIds': [PHISH, custom]}]) == (True, True)  # any of them: the custom one may be weak
    assert pol._mfa([{'Control': ['Mfa', 'CompliantDevice']}]) == (False, False)  # a compliant device is enough
    assert pol._mfa([{'Control': ['CompliantDevice']}, {'AuthStrengthIds': [custom]}]) == (True, True)  # AND
    assert pol._mfa([{'AuthStrengthIds': [custom]}, {'Control': ['Mfa']}]) == (True, False)
    assert pol._mfa([]) == (False, False)


def test_builtin_resolves(client):
    p = detail(client, 'Admins need phishing-resistant MFA')
    assert [(r.type, r.id, r.displayName) for r in p.grantControls] == [
        ('value', PHISH, 'Authentication strength: Phishing-resistant MFA')]
    (s,) = p.authenticationStrengths
    assert s.builtIn and s.combinations == ['Windows Hello for Business', 'FIDO2 security key',
                                            'Certificate-based authentication (multifactor)']
    assert p.grant == ['Phishing-resistant MFA'] and (p.requiresMfa, p.mfaApproximate) == (True, False)
    mfa = pol.BUILTIN_STRENGTHS['00000000-0000-0000-0000-000000000002'].combinations
    assert 'Password + Microsoft Authenticator (push notification)' in mfa


def test_custom_unresolved_but_mfa(client):
    p = detail(client, 'Protect security info registration')
    assert [(r.type, r.id) for r in p.grantControls] == [('unknown', AUTHSTRENGTH_CUSTOM)]
    assert [(s.id, s.builtIn, s.combinations) for s in p.authenticationStrengths] == [(AUTHSTRENGTH_CUSTOM, False, [])]
    assert p.grant == ['Custom authentication strength'] and (p.requiresMfa, p.mfaApproximate) == (True, True)


def test_rows_and_filter(client):
    rows = {p['displayName']: (p['requiresMfa'], p['mfaApproximate']) for p in client.get('/api/policies').json()['items']}
    assert rows['Require MFA for all users'] == (True, False)
    assert rows['Risky guest sign-ins'] == (False, False)  # MFA or compliant device
    assert rows['Block legacy authentication (report only)'] == (False, False)
    items = client.get('/api/policies', params={'filter': 'requiresMfa:eq:false'}).json()['items']
    assert 'Protect security info registration' not in {p['displayName'] for p in items}


def test_user_covered_by_custom_strength(client):
    """A user in scope of a custom-strength policy must not look like nothing requires MFA."""
    p = by_name(client, 'Protect security info registration')
    uid = client.get(f'/api/policies/{p["id"]}/users').json()['items'][0]['id']
    m = next(m for m in client.get(f'/api/policies/affecting/user/{uid}').json() if m['policy']['id'] == p['id'])
    assert m['effect'] == 'included' and m['policy']['requiresMfa'] and m['policy']['mfaApproximate']


def test_minimal_db(minimal_client):
    p = by_name(minimal_client, 'Protect security info registration')
    assert minimal_client.get(f'/api/policies/{p["id"]}').status_code == 200 and p['requiresMfa']
