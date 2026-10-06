"""S5 Conditional Access: policies, in-scope users, policies affecting an object, named locations (ADR 0001).

Scope is computed live from the policy JSON (`json.loads(Policy.policyDetail[0])`) and the membership
tables, never from lnk_policy_*. Policies are few, so they are parsed in Python on every request;
the users in scope stay in SQL (`_scope`), since a tenant can have hundreds of thousands of them.
"""
import base64
import json
import zlib
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import Select, Text, and_, false, func, literal, or_, select, type_coerce, union, union_all
from sqlalchemy.orm import Session

from roadtools.roadlib.metadef import database as d

from ..common import (Db, F, count_rows, gm_group, gm_user, iso, keyword, member_groups_select, not_found, paginate_list,
                      register, resolve_appids, resolve_ref, resolve_refs, unresolved, value)
from ..models import (AuthenticationStrength, Condition, MatchReason, NamedLocationDetail, NamedLocationRow, ObjectRef,
                      Page, PageQuery, PolicyCounts, PolicyDetail, PolicyMatch, PolicyQuery, PolicyRow, PolicyTargetType,
                      PolicyUserQuery, UserRow, WhatIfMatch, WhatIfQuery, WhatIfResult)
from . import users

router = APIRouter(prefix='/api', tags=['policies'])

U = d.User


def _options(attr):
    return lambda db: {x for _p, _d, row in _policies(db) for x in getattr(row, attr)}


POLICY_FIELDS = register('policies', {
    'displayName': F('Name', 'text', get=lambda r: r.displayName),
    'state': F('State', 'enum', get=lambda r: r.state,
               labels={'enabled': 'Enabled', 'reporting': 'Report-only', 'disabled': 'Disabled'}),
    'block': F('Blocks access', 'bool', get=lambda r: r.block),
    'requiresMfa': F('Requires MFA', 'bool', get=lambda r: r.requiresMfa),
    'targetsAllUsers': F('All users', 'bool', get=lambda r: r.targetsAllUsers),
    'targetsAllApps': F('All resources', 'bool', get=lambda r: r.targetsAllApps),
    'grant': F('Grant control', 'enum', get=lambda r: r.grant, options=_options('grant')),
    'sessionControls': F('Session control', 'enum', get=lambda r: r.sessionControls, options=_options('sessionControls')),
    'modifiedDateTime': F('Modified', 'date', get=lambda r: r.modifiedDateTime),
})

LOCATION_FIELDS = register('named-locations', {
    'displayName': F('Name', 'text', get=lambda r: r.displayName),
    'kind': F('Kind', 'enum', get=lambda r: r.kind, labels={'ip': 'IP ranges', 'country': 'Countries'}),
    'trusted': F('Trusted', 'bool', get=lambda r: r.trusted),
    'policyCount': F('Used by policies', 'number', get=lambda r: r.policyCount),
})

# --- Policy JSON ---------------------------------------------------------------

STATES = {'Enabled': 'enabled', 'Reporting': 'reporting'}
CONTROLS = {  # Control -> (short label for rows, long label for the detail)
    'Mfa': ('MFA', 'Multifactor authentication'),
    'CompliantDevice': ('Compliant device', 'Require device to be marked as compliant'),
    'DomainJoinedDevice': ('Hybrid joined device', 'Require Microsoft Entra hybrid joined device'),
    'ApprovedApplication': ('Approved client app', 'Require approved client app'),
    'CompliantApplication': ('App protection policy', 'Require app protection policy'),
    'PasswordChange': ('Password change', 'Require password change'),
}
_PHISHING_RESISTANT = ['windowsHelloForBusiness', 'fido2', 'x509CertificateMultiFactor']
AUTH_STRENGTHS = {  # Built-in strengths (Graph v1.0 authenticationStrengthPolicies): id -> (name, allowed combinations)
    '00000000-0000-0000-0000-000000000002': ('Multifactor authentication', [
        *_PHISHING_RESISTANT, 'deviceBasedPush', 'temporaryAccessPassOneTime', 'temporaryAccessPassMultiUse',
        'password,microsoftAuthenticatorPush', 'password,softwareOath', 'password,hardwareOath',
        'password,x509CertificateSingleFactor', 'password,x509CertificateMultiFactor', 'password,sms', 'password,voice',
        'federatedMultiFactor', 'microsoftAuthenticatorPush,federatedSingleFactor', 'softwareOath,federatedSingleFactor',
        'hardwareOath,federatedSingleFactor', 'sms,federatedSingleFactor', 'voice,federatedSingleFactor']),
    '00000000-0000-0000-0000-000000000003': ('Passwordless MFA', [*_PHISHING_RESISTANT, 'deviceBasedPush']),
    '00000000-0000-0000-0000-000000000004': ('Phishing-resistant MFA', _PHISHING_RESISTANT),
}
METHODS = {  # authenticationMethodModes -> label in the Entra admin center
    'password': 'Password', 'voice': 'Voice call', 'sms': 'SMS',
    'hardwareOath': 'Hardware OATH token', 'softwareOath': 'Software OATH token', 'fido2': 'FIDO2 security key',
    'windowsHelloForBusiness': 'Windows Hello for Business', 'deviceBasedPush': 'Microsoft Authenticator (phone sign-in)',
    'microsoftAuthenticatorPush': 'Microsoft Authenticator (push notification)',
    'temporaryAccessPassOneTime': 'Temporary Access Pass (one-time use)',
    'temporaryAccessPassMultiUse': 'Temporary Access Pass (multi-use)',
    'x509CertificateSingleFactor': 'Certificate-based authentication (single-factor)',
    'x509CertificateMultiFactor': 'Certificate-based authentication (multifactor)',
    'federatedSingleFactor': 'Federated single-factor', 'federatedMultiFactor': 'Federated multifactor',
}
# All three are multifactor. The dump (AAD Graph) has only the ids of custom strengths, not their combinations.
CUSTOM_STRENGTH = 'Custom authentication strength'
BUILTIN_STRENGTHS = {k: AuthenticationStrength(id=k, displayName=name, builtIn=True, combinations=[
    ' + '.join(METHODS.get(m, m) for m in c.split(',')) for c in combos]) for k, (name, combos) in AUTH_STRENGTHS.items()}
SESSIONS = {'SignInFrequency': 'Sign-in frequency', 'PersistentBrowserSessionMode': 'Persistent browser session',
            'AppEnforcedRestrictions': 'App enforced restrictions', 'CloudAppSecurity': 'Conditional Access App Control'}
LABELS = {'Users': 'Users', 'ServicePrincipals': 'Workload identities', 'Applications': 'Resources',
          'Locations': 'Locations', 'DevicePlatforms': 'Device platforms', 'ClientTypes': 'Client apps',
          'SignInRisks': 'Sign-in risk', 'UserRisks': 'User risk', 'ServicePrincipalRisks': 'Workload identity risk',
          'Devices': 'Device filter', 'AuthFlows': 'Authentication flows'}
# Criterion keys shown as their own condition: (Condition.key, label). Keys follow the frontend icons.
SUB_CONDITIONS = {'Roles': ('Users', 'Directory roles'), 'Acrs': ('AuthenticationContext', 'Authentication context'),
                  'UserActions': ('UserActions', 'User actions')}
FRONTEND_KEYS = {'AuthFlows': 'AuthenticationFlows'}  # policy JSON key -> frontend icon key
WHO, TARGETS = {'Users', 'ServicePrincipals'}, {'Applications', 'UserActions', 'AuthenticationContext'}
ALL = {'Users': 'All users', 'ServicePrincipals': 'All workload identities', 'Applications': 'All resources',
       'Locations': 'Any location', 'DevicePlatforms': 'Any platform'}
GUEST_WORDS = {'Guests', 'GuestsOrExternalUsers'}  # older dumps: a word inside the Users list
KEYWORDS = {'AllTrusted': 'All trusted locations', 'Office365': 'Office 365', 'MicrosoftAdminPortals': 'Microsoft Admin Portals',
            'None': 'None', 'ServicePrincipalsInMyTenant': 'All owned service principals',
            'Guests': 'Guests and external users', 'GuestsOrExternalUsers': 'Guests and external users'}
VALUES = {'EasSupported': 'Exchange ActiveSync clients', 'EasUnsupported': 'Exchange ActiveSync clients',
          'Native': 'Mobile apps and desktop clients', 'OtherLegacy': 'Other clients',
          'urn:user:registersecurityinfo': 'Register security information', 'urn:user:registerdevice': 'Register or join devices'}
OBJECT_KEYS = {'Users', 'Groups', 'Roles', 'ServicePrincipals', 'AgenticServicePrincipals'}


def _vals(v) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        return [f'{k}: {x}' for k, x in v.items()]
    return [v]


def _crits(cond: dict, key: str, side: str) -> list[dict]:
    """The criteria dicts of one side (Include / Exclude) of a condition."""
    c = cond.get(key)
    return [x for x in (c.get(side) if isinstance(c, dict) else None) or [] if isinstance(x, dict)]


def _custom_strengths(db: Session) -> dict[str, tuple[AuthenticationStrength, bool]]:
    """id -> (strength def, satisfies MFA). Custom authentication strengths the dump collects as policyType-44 rows
    (AAD Graph exposes them); the tenant default "container" row (tenantDefaultPolicy set, no allowedCombinations) is
    skipped. Empty on an old dump without such rows, so custom ids then fall back to unresolved."""
    out = {}
    for p in db.scalars(select(d.Policy).where(d.Policy.policyType == 44, d.Policy.tenantDefaultPolicy.is_(None))):
        try:
            det = json.loads(p.policyDetail[0])
        except Exception:  # noqa: BLE001 - a malformed strength just stays unresolved
            continue
        # allowedCombinations: each string is one combination of ", "-separated PascalCase methods.
        combos = [' + '.join(METHODS.get(m[:1].lower() + m[1:], m) for m in c.split(', '))
                  for c in det.get('allowedCombinations') or []]
        out[p.objectId] = (AuthenticationStrength(id=p.objectId, displayName=p.displayName or p.objectId,
                                                  builtIn=False, combinations=combos),
                           det.get('requirementsSatisfied') == 'Mfa')
    return out


def _grants(det: dict, strengths: dict) -> list[tuple[str, ObjectRef]]:
    out = []
    for c in det.get('Controls') or []:
        for k, v in c.items() if isinstance(c, dict) else ():
            if not isinstance(v, list):
                continue
            for x in v:
                if k == 'Control' and x != 'Block':
                    short, long = CONTROLS.get(x, (x, x))
                    out.append((short, value(long)))
                elif k == 'AuthStrengthIds' and (x in BUILTIN_STRENGTHS or x in strengths):
                    name = (BUILTIN_STRENGTHS.get(x) or strengths[x][0]).displayName
                    out.append((name, ObjectRef(id=x, type='value', displayName=f'Authentication strength: {name}')))
                elif k == 'AuthStrengthIds':  # custom strength not in the dump: only its id is known
                    out.append((CUSTOM_STRENGTH, ObjectRef(id=x, type='unknown', displayName=f'Authentication strength: {x}')))
                elif k != 'Control':
                    out.append((k, value(f'{k}: {x}')))
    return out


def _mfa(controls: list[dict], strengths: dict) -> tuple[bool, bool]:
    """(requiresMfa, mfaApproximate). Entries are ANDed and each is met by any of its controls, so one entry whose
    every control is MFA or an MFA authentication strength is enough. Built-in strengths are all MFA; a resolved
    custom strength uses its requirementsSatisfied; an unresolved custom strength counts as MFA but approximately,
    unless an entry without an unresolved strength settles it."""
    def is_mfa(k, x):  # this control, chosen alone, forces MFA
        if (k, x) == ('Control', 'Mfa') or (k == 'AuthStrengthIds' and x in BUILTIN_STRENGTHS):
            return True
        if k == 'AuthStrengthIds':
            return strengths[x][1] if x in strengths else True  # unresolved: assume MFA (approximate)
        return False

    def unresolved(k, x):
        return k == 'AuthStrengthIds' and x not in BUILTIN_STRENGTHS and x not in strengths

    entries = [[(k, x) for k, v in c.items() if isinstance(v, list) for x in v] for c in controls]
    mfa = [e for e in entries if e and all(is_mfa(k, x) for k, x in e)]
    return bool(mfa), bool(mfa) and all(any(unresolved(k, x) for k, x in e) for e in mfa)


def _strength_defs(det: dict, strengths: dict) -> list[AuthenticationStrength]:
    ids = [x for c in det.get('Controls') or [] if isinstance(c, dict) for x in _vals(c.get('AuthStrengthIds') or [])]
    return [BUILTIN_STRENGTHS.get(x) or (strengths[x][0] if x in strengths else
            AuthenticationStrength(id=x, displayName=CUSTOM_STRENGTH, builtIn=False, combinations=[]))
            for x in dict.fromkeys(ids)]


def _sessions(det: dict) -> list[tuple[str, str]]:
    out = []
    for s in _vals(det.get('SessionControls') or []):
        short = long = SESSIONS.get(s, str(s))
        if s == 'SignInFrequency':
            t = det.get('SignInFrequencyType')
            long += ': every time' if t == 30 else f': every {det.get("SignInFrequencyTimeSpan")}' if t == 10 else ''
        elif s == 'PersistentBrowserSessionMode' and det.get(s):
            long += f': {str(det[s]).lower()}'
        out.append((short, long))
    return out


def _row(p: d.Policy, det: dict, error: str | None, strengths: dict) -> PolicyRow:
    cond = det.get('Conditions') or {}
    controls = [c for c in det.get('Controls') or [] if isinstance(c, dict)]
    block = any('Block' in _vals(c.get('Control') or []) for c in controls)
    mfa, approximate = (False, False) if block else _mfa(controls, strengths)
    return PolicyRow(
        id=p.objectId, displayName=p.displayName or p.objectId,
        state=STATES.get(det.get('State'), 'disabled'),
        targetsAllUsers=any('All' in _vals(v) for c in _crits(cond, 'Users', 'Include') for v in c.values()),
        targetsAllApps=any('All' in _vals(c.get('Applications') or []) for c in _crits(cond, 'Applications', 'Include')),
        block=block,
        grant=list(dict.fromkeys(s for s, _ in _grants(det, strengths))),
        # One controls entry = any of its controls; several entries must all be met (old policies plugin).
        grantOperator='AND' if len(controls) > 1 else 'OR',
        requiresMfa=mfa, mfaApproximate=approximate,
        sessionControls=list(dict.fromkeys(s for s, _ in _sessions(det))),
        modifiedDateTime=iso(det.get('ModificationDateTime')),
        parseError=error,
    )


def _parse(p: d.Policy, strengths: dict) -> tuple[d.Policy, dict, PolicyRow]:
    """(policy, decoded JSON, row). A malformed policy gets an empty JSON and `parseError`, never a 500."""
    try:
        det = json.loads(p.policyDetail[0])
        if not isinstance(det, dict):
            raise ValueError('policy detail is not a JSON object')
        return p, det, _row(p, det, None, strengths)
    except Exception as e:  # noqa: BLE001
        return p, {}, _row(p, {}, f'{type(e).__name__}: {e}', strengths)


def _policies(db: Session) -> list[tuple[d.Policy, dict, PolicyRow]]:
    strengths = _custom_strengths(db)
    return [_parse(p, strengths) for p in db.scalars(select(d.Policy).where(d.Policy.policyType == 18))]


def _get(db: Session, id: str) -> tuple[d.Policy, dict, PolicyRow, dict]:
    p = db.scalar(select(d.Policy).where(d.Policy.objectId == id, d.Policy.policyType == 18))
    if p is None:
        raise not_found('Policy')
    strengths = _custom_strengths(db)
    return (*_parse(p, strengths), strengths)


def _items(key: str, sub: str, v) -> list:
    """Refs (keywords, values) or ('id' | 'app' | 'loc', raw) placeholders resolved in one batch later."""
    if sub == 'GuestsOrExternalUsers':
        types = v.get('GuestOrExternalUserTypes') if isinstance(v, dict) else None
        types = ', '.join(types if isinstance(types, list) else str(types or '').split(','))
        return [keyword('Guests and external users' + (f': {types}' if types else ''))]
    out = []
    for x in _vals(v):
        if x == 'All':
            out.append(keyword(ALL.get(key, 'All')))
        elif x in KEYWORDS:
            out.append(keyword(KEYWORDS[x]))
        elif sub in OBJECT_KEYS:
            out.append(('id', x))
        elif sub == 'Applications':
            out.append(('app', x))
        elif sub == 'Locations':
            out.append(('loc', x))
        else:
            x = str(x)
            out.append(value(VALUES.get(x, 'Other clients' if x.startswith('Legacy') else x)))
    return out


def _conditions(db: Session, det: dict) -> tuple[list[Condition], list[Condition], list[Condition]]:
    """(who, targets, conditions) with every id resolved to an ObjectRef."""
    cond = det.get('Conditions') or {}
    acc: dict[tuple[str, str], dict[str, list]] = {}
    for key in cond:
        for side in ('Include', 'Exclude'):
            for crit in _crits(cond, key, side):
                for sub, v in crit.items():
                    if sub == 'Acrs':  # user actions are stored as Acrs too: urn:user:registersecurityinfo
                        vals = _vals(v)
                        for s2, xs in (('UserActions', [x for x in vals if str(x).startswith('urn:user:')]),
                                       ('Acrs', [x for x in vals if not str(x).startswith('urn:user:')])):
                            if xs:
                                acc.setdefault(SUB_CONDITIONS[s2], {'Include': [], 'Exclude': []})[side] += _items(key, s2, xs)
                    elif sub != 'IsAgentic':
                        ck = SUB_CONDITIONS.get(sub, (key, LABELS.get(key, key)))
                        acc.setdefault(ck, {'Include': [], 'Exclude': []})[side] += _items(key, sub, v)
    raw = [x for sides in acc.values() for xs in sides.values() for x in xs if isinstance(x, tuple)]
    found = {'id': resolve_refs(db, [x for k, x in raw if k == 'id']),
             'app': resolve_appids(db, [x for k, x in raw if k == 'app']),
             'loc': {k: ObjectRef(id=row['id'], type='namedLocation', displayName=row['displayName'])
                     for k, row, _p in _locations(db)} if any(k == 'loc' for k, _ in raw) else {}}

    def refs(xs):
        out = [x if isinstance(x, ObjectRef) else found[x[0]].get(x[1]) or unresolved(x[1]) for x in xs]
        return list({(r.type, r.id, r.displayName): r for r in out}.values())

    groups = ([], [], [])
    for (key, label), sides in acc.items():
        groups[0 if key in WHO else 1 if key in TARGETS else 2].append(
            Condition(key=FRONTEND_KEYS.get(key, key), label=label, include=refs(sides['Include']), exclude=refs(sides['Exclude'])))
    return groups


# --- Scope (SQL) -------------------------------------------------------------------

def _holders():
    """(principal, role template id, kind) of every directory-scoped role assignment.

    Conditional Access ignores assignments scoped to an administrative unit or an object, so only
    the directory scope ('/') counts. Built-in role definition ids equal their template ids.
    """
    dr = d.DirectoryRole
    parts = [select(t.c[col].label('principal'), dr.roleTemplateId.label('role'), literal('active').label('kind'))
             .join(dr, dr.objectId == t.c.DirectoryRole)
             for t, col in ((d.lnk_role_member_user, 'User'), (d.lnk_role_member_group, 'Group'),
                            (d.lnk_role_member_serviceprincipal, 'ServicePrincipal'))]
    for model, kind in ((d.RoleAssignment, 'active'), (d.EligibleRoleAssignment, 'eligible')):
        parts.append(select(model.principalId, model.roleDefinitionId, literal(kind))
                     .where(type_coerce(model.resourceScopes, Text).like('%"/"%')))
    return union_all(*parts).subquery()


def _guest_clause(spec):
    """Users matching a guest / external user criterion. ponytail: inferred from userType (approximate)."""
    types = spec.get('GuestOrExternalUserTypes') if isinstance(spec, dict) else None
    types = None if types is None else set(types if isinstance(types, list) else str(types).split(','))
    clauses = []
    if types is None or types & {'internalGuest', 'b2bCollaborationGuest'}:
        clauses.append(U.userType == 'Guest')
    if types and 'b2bCollaborationMember' in types:
        clauses.append(and_(U.userType == 'Member', U.userPrincipalName.like('%#EXT#%')))
    return or_(*clauses) if clauses else false()


ALL_USERS = select(U.objectId)


def _side(crits: list[dict], name: str, active_only: bool = False) -> Select | None:
    """One-column select of the ids one side of the Users condition targets (non-user ids are filtered later)."""
    parts, groups, roles = [], [], []
    for crit in crits:
        for sub, v in crit.items():
            if sub == 'GuestsOrExternalUsers':
                parts.append(select(U.objectId).where(_guest_clause(v)))
                continue
            vals = _vals(v)
            if sub == 'All' or (sub == 'Users' and 'All' in vals):
                return ALL_USERS
            elif sub == 'Users':
                parts.append(select(U.objectId).where(U.objectId.in_(vals)))
                if GUEST_WORDS & set(vals):
                    parts.append(select(U.objectId).where(_guest_clause(None)))
            elif sub == 'Groups':
                groups += vals
            elif sub == 'Roles':
                roles += vals
    if roles:
        h = _holders()
        holders = select(h.c.principal).where(h.c.role.in_(roles), *([h.c.kind == 'active'] if active_only else []))
        parts.append(holders)
        seed = select(d.Group.objectId).where(or_(d.Group.objectId.in_(groups), d.Group.objectId.in_(holders)))
    else:
        seed = select(d.Group.objectId).where(d.Group.objectId.in_(groups))
    if groups or roles:
        tree = seed.cte(name, recursive=True)
        tree = tree.union(select(gm_group.c.childGroup).join(tree, gm_group.c.Group == tree.c[0]))
        parts.append(select(gm_user.c.User).where(gm_user.c.Group.in_(select(tree.c[0]))))
    return union(*parts) if parts else None


def _scope(det: dict, effect: str = 'applies', tag: str = '') -> Select:
    """One-column select of the user ids in scope (`applies`), or included but excluded (`excluded`).

    `tag` suffixes the CTE names so several scopes can be combined in one statement (see mfa_required_users)."""
    cond = det.get('Conditions') or {}
    inc = _side(_crits(cond, 'Users', 'Include'), 'scope_include' + tag)
    # An eligible (not activated) role does not exclude: CA only sees active role assignments.
    exc = _side(_crits(cond, 'Users', 'Exclude'), 'scope_exclude' + tag, active_only=True)
    if inc is None:
        return select(U.objectId).where(false())
    stmt = ALL_USERS if inc is ALL_USERS else select(U.objectId).where(U.objectId.in_(inc))
    if exc is None:
        return stmt.where(false()) if effect == 'excluded' else stmt
    if effect == 'excluded':
        return stmt.where(U.objectId.in_(exc))
    sq = exc.subquery()
    return stmt.where(U.objectId.not_in(select(sq.c[0]).where(sq.c[0].isnot(None))))  # NOT IN + NULL = nothing


def ca_policies_collected(db: Session) -> bool:
    """Whether Conditional Access policies (policyType 18) were collected at all (the feature's data gate)."""
    return db.scalar(select(d.Policy.objectId).where(d.Policy.policyType == 18).limit(1)) is not None


def mfa_required_users(db: Session) -> Select:
    """One-column select of the user ids an ENABLED Conditional Access policy requiring MFA puts in scope (the union
    of `_scope` over those policies). Empty select when there is no such policy, including a dump with no CA policies."""
    scopes = [_scope(det, tag=f'_m{i}') for i, (_p, det, row) in enumerate(_policies(db))
              if row.state == 'enabled' and row.requiresMfa]
    return union(*scopes) if scopes else select(U.objectId).where(false())


# --- Matches -------------------------------------------------------------------

def _reason(condition: str, via=(), approximate=False, eligible=False) -> MatchReason:
    return MatchReason(condition=condition, via=list(via), approximate=approximate, eligibleOnly=eligible)


def _match(row: PolicyRow, included: list, excluded: list) -> PolicyMatch | None:
    if included or excluded:
        # Exclusion wins, except one that only holds through an eligible role (inactive until activated).
        wins = excluded and (not included or any(not r.eligibleOnly for r in excluded))
        return PolicyMatch(policy=row, effect='excluded' if wins else 'included', included=included, excluded=excluded)
    return None


def _ancestor_chains(db: Session, oid: str) -> dict[str, list[str]]:
    """Every group the object is in -> chain of group ids from the object up to that group."""
    out = {g: [g] for g in db.scalars(select(member_groups_select(oid).subquery().c.id)) if g != oid}
    frontier = dict(out)
    while frontier:
        nxt = {}
        for parent, child in db.execute(select(gm_group.c.Group, gm_group.c.childGroup)
                                        .where(gm_group.c.childGroup.in_(list(frontier)))):
            if parent not in out and parent != oid:
                out[parent] = nxt[parent] = frontier[child] + [parent]
        frontier = nxt
    return out


def _affecting(db: Session, type: str, id: str) -> list[PolicyMatch]:
    chains = _ancestor_chains(db, id) if type in ('user', 'group') else {}
    held: dict[str, tuple[bool, int, list[str]]] = {}  # role -> (eligible only, path length, group chain)
    if type in ('user', 'group'):
        h = _holders()
        for principal, role, kind in db.execute(select(h).where(h.c.principal.in_([id, *chains]))):
            cand = (kind == 'eligible', len(chains.get(principal, [])), chains.get(principal, []))
            if role not in held or cand[:2] < held[role][:2]:  # prefer active, then the shortest path
                held[role] = cand
    refs = resolve_refs(db, {*chains, *held})
    app_ids = set()
    if type in ('servicePrincipal', 'application'):
        model = d.ServicePrincipal if type == 'servicePrincipal' else d.Application
        app_ids = set(db.scalars(select(model.appId).where(model.objectId == id)))
    # Workload identity policies only cover single-tenant SPs owned by this tenant.
    owned_sp = type == 'servicePrincipal' and bool(db.scalar(select(func.count()).where(
        d.ServicePrincipal.objectId == id, d.ServicePrincipal.appOwnerTenantId.in_(select(d.TenantDetail.objectId)))))

    def is_guest(spec) -> bool:
        return type == 'user' and bool(db.scalar(select(func.count()).where(U.objectId == id, _guest_clause(spec))))

    out = []
    for _p, det, row in _policies(db):
        cond = det.get('Conditions') or {}
        sides = {}
        for side in ('Include', 'Exclude'):
            rs = sides[side] = []
            for crit in _crits(cond, 'Users', side):
                for sub, v in crit.items():
                    vals = _vals(v)
                    if sub == 'GuestsOrExternalUsers':
                        if is_guest(v):
                            rs.append(_reason('Users', [keyword('Guests and external users')], approximate=True))
                    elif type == 'user' and (sub == 'All' or (sub == 'Users' and 'All' in vals)):
                        rs.append(_reason('Users', [keyword('All users')]))
                    elif sub == 'Users':
                        if id in vals:
                            rs.append(_reason('Users'))
                        if GUEST_WORDS & set(vals) and is_guest(None):
                            rs.append(_reason('Users', [keyword('Guests and external users')], approximate=True))
                    elif sub == 'Groups':
                        rs += [_reason('Users', [refs[x] for x in chains[g]]) if g in chains else _reason('Users')
                               for g in vals if g in chains or (type == 'group' and g == id)]
                    elif sub == 'Roles':
                        for r in vals:
                            if type == 'role' and r == id:
                                rs.append(_reason('Directory roles'))
                            elif r in held:
                                eligible, _n, chain = held[r]
                                rs.append(_reason('Directory roles', [*(refs[g] for g in chain), refs[r]], eligible=eligible))
            for crit in _crits(cond, 'ServicePrincipals', side) if type == 'servicePrincipal' else ():
                for sub, v in crit.items():
                    vals = _vals(v)
                    if id in vals:
                        rs.append(_reason('Workload identities'))
                    elif owned_sp and sub == 'ServicePrincipals' and {'All', 'ServicePrincipalsInMyTenant'} & set(vals):
                        rs.append(_reason('Workload identities', [keyword(ALL['ServicePrincipals'])]))
            for crit in _crits(cond, 'Applications', side) if app_ids else ():
                vals = _vals(crit.get('Applications') or [])
                if app_ids & set(vals):
                    rs.append(_reason('Resources'))
                elif 'All' in vals:  # ponytail: Office365 / admin portal bundles are not expanded
                    rs.append(_reason('Resources', [keyword(ALL['Applications'])]))
        if m := _match(row, sides['Include'], sides['Exclude']):
            out.append(m)
    return out


# --- Sign-in check (what if) -----------------------------------------------------------
# Three-valued: True (matches), False (rules the policy out), None (cannot tell: unset in the check, not evaluated
# from the dump, or approximate). A policy applies when every condition is True, may apply when none is False.

CLIENT_APPS = {'browser': {'browser'}, 'native': {'native'}, 'eas': {'eassupported', 'easunsupported'}}
BUNDLES = {'Office365', 'MicrosoftAdminPortals'}  # ponytail: not expanded; a Microsoft app in a bundle is undecided
USER_ACTION_PREFIX = 'urn:user:'


def _and(*xs):
    return False if False in xs else None if None in xs else True


def _side_hit(vals: list | None, hit) -> bool | None:
    """Any value of one side matches. `hit(v)` is three-valued too."""
    rs = [hit(v) for v in vals or []]
    return True if True in rs else None if None in rs else False


def _cond(cond: dict, key: str, sub: str | None, hit) -> bool | None:
    """Included and not excluded, from the values of `sub` (every key of the criteria when None)."""
    def vals(side):
        return [x for c in _crits(cond, key, side) for k, v in c.items() if sub in (None, k) for x in _vals(v)]
    inc, exc = _side_hit(vals('Include'), hit), _side_hit(vals('Exclude'), hit)
    return _and(inc, None if exc is None else not exc)


def _signin(db: Session, q: WhatIfQuery) -> dict:
    """What the check needs to know about the sign-in, resolved once for every policy."""
    s = {'q': q, 'identity': None, 'matches': {}, 'microsoft': False, 'location': None}
    if q.identity:
        s['identity'] = ref = resolve_ref(db, q.identity)
        if ref.type in ('user', 'servicePrincipal'):
            wanted = {'Users', 'Directory roles'} if ref.type == 'user' else {'Workload identities'}
            for m in _affecting(db, ref.type, q.identity):  # only the identity side: drop the Resources reasons
                inc, exc = ([r for r in rs if r.condition in wanted] for rs in (m.included, m.excluded))
                if mm := _match(m.policy, inc, exc):
                    s['matches'][m.policy.id] = mm
    if q.resource and not q.resource.startswith(USER_ACTION_PREFIX):
        s['microsoft'] = bool(db.scalar(select(func.count()).where(
            d.ServicePrincipal.appId == q.resource, d.ServicePrincipal.microsoftFirstParty.is_(True))))
    if q.location and q.location != 'other':
        for key, fields, p in _locations(db):
            if p.objectId == q.location:
                s['location'] = (key, fields['trusted'])
    return s


def _evaluate(det: dict, row: PolicyRow, s: dict) -> tuple[bool | None, list[str]]:
    """(result, labels of the undecided conditions) of one policy for the sign-in."""
    q, cond, results = s['q'], det.get('Conditions') or {}, {}
    if row.parseError:
        results['Unreadable policy'] = None
    # Identity: Users and ServicePrincipals together, from the same matches as the object Policies tabs.
    if not q.identity:
        results['User or workload identity'] = None
    else:
        m = s['matches'].get(row.id)
        if m is None or m.effect == 'excluded':
            results['User or workload identity'] = False
        else:
            certain = any(not r.approximate and not r.eligibleOnly for r in m.included)
            results['User or workload identity'] = True if certain else None
    for key in cond:
        if key in ('Users', 'ServicePrincipals'):
            continue
        label = LABELS.get(key, key)
        if key == 'Applications':
            r = q.resource
            if r is None:
                res = None
            elif r.startswith(USER_ACTION_PREFIX) or not _is_guid(r):  # user action or authentication context
                res = _cond(cond, key, None, lambda v: v == r)
            else:
                res = _cond(cond, key, 'Applications', lambda v: True if v in ('All', r) else
                            None if v in BUNDLES and s['microsoft'] else False)
        elif key == 'Locations':
            loc = s['location']
            res = _cond(cond, key, 'Locations', lambda v: True if v == 'All' else None if q.location is None else
                        bool(loc) and (v == loc[0] or (v == 'AllTrusted' and loc[1])))
        elif key in ('DevicePlatforms', 'SignInRisks', 'UserRisks', 'ClientTypes', 'AuthFlows'):
            want = {'DevicePlatforms': q.platform, 'SignInRisks': q.signInRisk, 'UserRisks': q.userRisk,
                    'ClientTypes': q.clientApp, 'AuthFlows': q.authFlow}[key]

            def hit(v, want=want, key=key):
                v = str(v).lower()
                if v == 'all':
                    return True
                if want is None:
                    return None
                if key == 'ClientTypes':  # OtherLegacy and Legacy* are the "other clients"
                    return v in CLIENT_APPS[want] if want in CLIENT_APPS else v == 'otherlegacy' or v.startswith('legacy')
                return v == want.lower()
            res = _cond(cond, key, None, hit)
        else:  # device filter rules and anything newer: shown, not evaluated
            res = _cond(cond, key, None, lambda v: True if v == 'All' else None)
        results[label] = res
    result = _and(*results.values())
    return result, [k for k, v in results.items() if v is None]


def _is_guid(s: str) -> bool:
    return len(s) == 36 and s.count('-') == 4


def what_if(db: Session, q: WhatIfQuery) -> tuple[dict, list[PolicyRow]]:
    """(sign-in facts, enabled and report-only policies that apply or may apply, each with `whatIf` set)."""
    s, out = _signin(db, q), []
    for _p, det, row in _policies(db):
        if row.state == 'disabled':
            continue
        result, depends = _evaluate(det, row, s)
        if result is not False:
            row.whatIf = WhatIfMatch(result='applies' if result else 'mayApply', dependsOn=depends)
            out.append(row)
    return s, out


def _what_if_set(q: WhatIfQuery) -> bool:
    return any(getattr(q, k) is not None for k in WhatIfQuery.model_fields)


# --- Named locations -----------------------------------------------------------------

def _location(p: d.Policy) -> tuple[str | None, dict]:
    """(id policies use to reference it, NamedLocationRow fields). Old dumps wrap it in KnownNetworkPolicies."""
    key, det, ips = p.policyIdentifier, {}, []
    try:
        for s in p.policyDetail or []:
            x = json.loads(s)
            if 'KnownNetworkPolicies' in x:
                det = x['KnownNetworkPolicies']
                key = det.get('NetworkId') or key
        det = det or json.loads(p.policyDetail[0])
        ips = det.get('CidrIpRanges') or []
        if det.get('CompressedCidrIpRanges'):
            ips = zlib.decompress(base64.b64decode(det['CompressedCidrIpRanges']), -zlib.MAX_WBITS).decode().split(',')
    except Exception:  # noqa: BLE001 - a broken location still lists, without ranges
        det = det if isinstance(det, dict) else {}
    countries = det.get('CountryIsoCodes') or []
    return key, {
        'id': p.objectId, 'displayName': det.get('NetworkName') or p.displayName or p.objectId,
        'kind': 'country' if countries else 'ip', 'trusted': 'trusted' in (det.get('Categories') or []),
        'ipRanges': [r for r in ips if r], 'countries': countries,
        'includeUnknownCountries': bool(det.get('ApplyToUnknownCountry')),
    }


def _locations(db: Session) -> list[tuple[str | None, dict, d.Policy]]:
    return [(*_location(p), p) for p in db.scalars(select(d.Policy).where(d.Policy.policyType == 6))]


def _location_matches(policies, key: str | None, trusted: bool) -> list[PolicyMatch]:
    out = []
    for _p, det, row in policies:
        sides = {}
        for side in ('Include', 'Exclude'):
            sides[side] = []
            for c in _crits(det.get('Conditions') or {}, 'Locations', side):
                vals = _vals(c.get('Locations') or [])
                if key and key in vals:
                    sides[side].append(_reason('Locations'))
                elif trusted and 'AllTrusted' in vals:
                    sides[side].append(_reason('Locations', [keyword(KEYWORDS['AllTrusted'])]))
        if m := _match(row, sides['Include'], sides['Exclude']):
            out.append(m)
    return out


def _location_row(key, fields, policies) -> tuple[NamedLocationRow, list[PolicyMatch]]:
    matches = _location_matches(policies, key, fields['trusted'])
    refs = [ObjectRef(id=m.policy.id, type='policy', displayName=m.policy.displayName) for m in matches]
    excluded = [m.policy.id for m in matches if m.effect == 'excluded']
    return NamedLocationRow(**fields, policyCount=len(refs), policies=refs, excludedBy=excluded), matches


# --- Routes ----------------------------------------------------------------------

@router.get('/policies')
def list_policies(q: Annotated[PolicyQuery, Query()], db: Db) -> Page[PolicyRow]:
    """All policies, or with any sign-in check parameter only those that apply or may apply to that sign-in."""
    rows = what_if(db, q)[1] if _what_if_set(q) else [row for _p, _d, row in _policies(db)]
    rows = [row for row in rows if (q.state is None or row.state == q.state) and (q.block is None or row.block == q.block)]
    return paginate_list(rows, q, resource='policies', text=lambda r: r.displayName, sorts={
        'displayName': lambda r: r.displayName.lower(), 'state': lambda r: r.state,
        'modifiedDateTime': lambda r: r.modifiedDateTime})


@router.get('/policies/what-if')
def policies_what_if(q: Annotated[WhatIfQuery, Query()], db: Db) -> WhatIfResult:
    """What the enabled policies enforce on a sign-in. The matching policies are `/api/policies` with the same query."""
    s, rows = what_if(db, q)
    enforced = [r for r in rows if r.state == 'enabled']
    sure, maybe = ([r for r in enforced if r.whatIf.result == want] for want in ('applies', 'mayApply'))
    resource = None
    if q.resource:
        resource = (keyword(VALUES.get(q.resource, f'Authentication context {q.resource}'))
                    if q.resource.startswith(USER_ACTION_PREFIX) or not _is_guid(q.resource)
                    else resolve_appids(db, [q.resource])[q.resource])
    return WhatIfResult(
        identity=s['identity'], resource=resource,
        block=any(r.block for r in sure), requiresMfa=any(r.requiresMfa for r in sure),
        grant=list(dict.fromkeys(g for r in sure for g in r.grant)),
        sessionControls=list(dict.fromkeys(x for r in sure for x in r.sessionControls)),
        mayBlock=any(r.block for r in maybe), mayRequireMfa=any(r.requiresMfa for r in maybe),
        dependsOn=list(dict.fromkeys(x for r in maybe for x in r.whatIf.dependsOn)),
        applies=len(sure), mayApply=len(maybe), reportOnly=len(rows) - len(enforced))


@router.get('/policies/affecting/{type}/{id}')
def policies_affecting(type: PolicyTargetType, id: str, db: Db) -> list[PolicyMatch]:
    """Policies that include or exclude the object, directly or through groups and roles."""
    if resolve_ref(db, id).type == 'unknown':
        raise not_found()
    return _affecting(db, type, id)


@router.get('/policies/{id}')
def get_policy(id: str, db: Db) -> PolicyDetail:
    p, det, row, strengths = _get(db, id)
    try:
        who, targets, conditions = _conditions(db, det)
        grants, sessions = [r for _s, r in _grants(det, strengths)], [value(long) for _s, long in _sessions(det)]
        strength_defs = _strength_defs(det, strengths)
    except Exception as e:  # noqa: BLE001 - unexpected shapes: show what the row has, flag the rest
        row.parseError = row.parseError or f'{type(e).__name__}: {e}'
        who, targets, conditions, grants, sessions, strength_defs = [], [], [], [], [], []
    counts = PolicyCounts(inScope=count_rows(db, _scope(det)), excluded=count_rows(db, _scope(det, 'excluded')))
    return PolicyDetail(**row.model_dump(), who=who, targets=targets, conditions=conditions, grantControls=grants,
                        authenticationStrengths=strength_defs, session=sessions, counts=counts, raw=p.as_dict())


@router.get('/policies/{id}/users')
def policy_users(id: str, q: Annotated[PolicyUserQuery, Query()], db: Db) -> Page[UserRow]:
    """Users in the policy scope (effect=applies, the default) or excluded from it."""
    _p, det, _row, _s = _get(db, id)
    return users.page_users(db, q, within=_scope(det, q.effect or 'applies'))


@router.get('/named-locations')
def list_named_locations(q: Annotated[PageQuery, Query()], db: Db) -> Page[NamedLocationRow]:
    policies = _policies(db)
    rows = [_location_row(key, fields, policies)[0] for key, fields, _p in _locations(db)]
    return paginate_list(rows, q, resource='named-locations', text=lambda r: r.displayName,
                         sorts={'displayName': lambda r: r.displayName.lower(), 'policyCount': lambda r: r.policyCount})


@router.get('/named-locations/{id}')
def get_named_location(id: str, db: Db) -> NamedLocationDetail:
    p = db.scalar(select(d.Policy).where(d.Policy.policyType == 6, d.Policy.objectId == id))
    if p is None:
        raise not_found('Named location')
    key, fields = _location(p)
    row, matches = _location_row(key, fields, _policies(db))
    return NamedLocationDetail(**row.model_dump(), policyMatches=matches, raw=p.as_dict())


# --- Shared with other slices (counts on object pages) ---

def count_affecting(db: Session, type: str, id: str) -> int:
    """len(policies_affecting(type, id))."""
    return len(_affecting(db, type, id))
