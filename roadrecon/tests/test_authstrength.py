"""Authentication strengths: built-in ones resolve from a constant; custom ones resolve from the policyType-44 rows
the dump collects (name, combinations, MFA from requirementsSatisfied), and fall back to unresolved + approximate MFA
when those rows are absent (old dump)."""
from gendb import AUTHSTRENGTH_CUSTOM, AUTHSTRENGTH_CUSTOM_UNRESOLVED
from roadtools.roadrecon.api.models import PolicyDetail
from roadtools.roadrecon.api.routers import policies as pol

PHISH = '00000000-0000-0000-0000-000000000004'


def by_name(client, name):
    return next(p for p in client.get('/api/policies').json()['items'] if p['displayName'] == name)


def detail(client, name):
    return PolicyDetail(**client.get(f'/api/policies/{by_name(client, name)["id"]}').json())


def test_mfa_rule():
    custom = 'c0ffee00-0000-0000-0000-000000000001'
    none = {}                              # no custom strengths resolved (old dump)
    mfa_strength = {custom: (None, True)}  # resolved, satisfies MFA (only [1] is read here)
    weak_strength = {custom: (None, False)}  # resolved, does NOT satisfy MFA
    assert pol._mfa([{'Control': ['Mfa']}], none) == (True, False)
    assert pol._mfa([{'AuthStrengthIds': [PHISH]}], none) == (True, False)
    assert pol._mfa([{'AuthStrengthIds': [custom]}], none) == (True, True)            # unresolved: approximate
    assert pol._mfa([{'AuthStrengthIds': [custom]}], mfa_strength) == (True, False)   # resolved MFA: exact
    assert pol._mfa([{'AuthStrengthIds': [custom]}], weak_strength) == (False, False)  # resolved non-MFA: no MFA
    assert pol._mfa([{'AuthStrengthIds': [PHISH, custom]}], none) == (True, True)     # any of them: custom may be weak
    assert pol._mfa([{'Control': ['Mfa', 'CompliantDevice']}], none) == (False, False)  # a compliant device is enough
    assert pol._mfa([{'Control': ['CompliantDevice']}, {'AuthStrengthIds': [custom]}], none) == (True, True)  # AND
    assert pol._mfa([{'AuthStrengthIds': [custom]}, {'Control': ['Mfa']}], none) == (True, False)
    assert pol._mfa([], none) == (False, False)


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


def test_custom_resolves(client):
    """A custom strength with a policyType-44 row: real name + combinations, exact MFA from requirementsSatisfied."""
    name = 'Password + Microsoft Authenticator (push)'
    p = detail(client, 'Protect security info registration')
    assert [(r.type, r.id, r.displayName) for r in p.grantControls] == [
        ('value', AUTHSTRENGTH_CUSTOM, f'Authentication strength: {name}')]
    assert [(s.id, s.builtIn, s.combinations) for s in p.authenticationStrengths] == [
        (AUTHSTRENGTH_CUSTOM, False, ['Password + Microsoft Authenticator (push notification)'])]
    assert p.grant == [name] and (p.requiresMfa, p.mfaApproximate) == (True, False)


def test_custom_unresolved_but_mfa(client):
    """A custom strength with no type-44 row stays unresolved and counts as MFA approximately."""
    p = detail(client, 'Legacy custom-strength MFA')
    assert [(r.type, r.id) for r in p.grantControls] == [('unknown', AUTHSTRENGTH_CUSTOM_UNRESOLVED)]
    assert [(s.id, s.builtIn, s.combinations) for s in p.authenticationStrengths] == [
        (AUTHSTRENGTH_CUSTOM_UNRESOLVED, False, [])]
    assert p.grant == ['Custom authentication strength'] and (p.requiresMfa, p.mfaApproximate) == (True, True)


def test_rows_and_filter(client):
    rows = {p['displayName']: (p['requiresMfa'], p['mfaApproximate']) for p in client.get('/api/policies').json()['items']}
    assert rows['Require MFA for all users'] == (True, False)
    assert rows['Protect security info registration'] == (True, False)  # resolved custom strength
    assert rows['Legacy custom-strength MFA'] == (True, True)           # unresolved custom strength
    assert rows['Risky guest sign-ins'] == (False, False)  # MFA or compliant device
    assert rows['Block legacy authentication (report only)'] == (False, False)
    items = client.get('/api/policies', params={'filter': 'requiresMfa:eq:false'}).json()['items']
    assert 'Protect security info registration' not in {p['displayName'] for p in items}


def test_user_covered_by_custom_strength(client):
    """A user in scope of a (resolved) custom-strength policy must not look like nothing requires MFA."""
    p = by_name(client, 'Protect security info registration')
    uid = client.get(f'/api/policies/{p["id"]}/users').json()['items'][0]['id']
    m = next(m for m in client.get(f'/api/policies/affecting/user/{uid}').json() if m['policy']['id'] == p['id'])
    assert m['effect'] == 'included' and m['policy']['requiresMfa'] and not m['policy']['mfaApproximate']


def test_minimal_db(minimal_client):
    """An old dump has no type-44 rows: the custom strength stays unresolved, still counted as MFA (approximate)."""
    p = by_name(minimal_client, 'Protect security info registration')
    assert minimal_client.get(f'/api/policies/{p["id"]}').status_code == 200
    assert p['requiresMfa'] and p['mfaApproximate']
