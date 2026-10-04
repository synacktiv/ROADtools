"""Shared helpers for the routers: session dependency, paging, advanced filters, object refs, membership CTEs.

Every list route builds a SQLAlchemy `select`, declares its filterable fields once with `register()`,
and hands both to `paginate()` (or `paginate_list()` for small, computed collections such as policies).
"""
import datetime
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Select, and_, func, inspect, literal, not_, or_, select, true, union
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.schema import Column

from roadtools.roadlib.metadef import database as d

from .models import FilterField, FilterOption, ObjectRef, Page, PageQuery

# --- Session -----------------------------------------------------------------


def get_db(request: Request):
    with request.app.state.sessionmaker() as session:
        yield session


Db = Annotated[Session, Depends(get_db)]


def has_table(db: Session, name: str) -> bool:
    """Optional tables (PIM*, IG*, AZ*) are missing on older dumps: callers return empty results."""
    engine = db.get_bind()
    cache = engine.__dict__.setdefault('_rr_tables', set(inspect(engine).get_table_names()))
    return name in cache


def not_found(what: str = 'Object') -> HTTPException:
    return HTTPException(404, f'{what} not found')


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.isoformat() + ('Z' if value.tzinfo is None else '')
    return str(value)


# --- Advanced filters --------------------------------------------------------

OPS = {'contains', 'notContains', 'eq', 'ne', 'startsWith', 'endsWith', 'empty', 'notEmpty', 'in', 'notIn', 'gt', 'lt'}


@dataclass
class F:
    """A filterable field.

    SQL lists set `col` (a column or expression of the paginated select) or `where` (op, arg) -> clause
    for multi-valued fields. In-memory lists (`paginate_list`) set `get` (row -> value or list of values).
    Enum options: `options(db)` if set, else the distinct values of `col` when it is a table column,
    else the keys of `labels`.
    """
    label: str
    type: str  # text | enum | bool | date | number
    col: Any = None
    where: Callable[[str, str], ColumnElement] | None = None
    get: Callable[[Any], Any] | None = None
    labels: dict[str, str] | None = None
    options: Callable[[Session], Iterable[str]] | None = None


FIELDS: dict[str, dict[str, F]] = {}


def register(resource: str, fields: dict[str, F]) -> dict[str, F]:
    """Declare the filter catalogue of a resource; served by `/api/filters/{resource}`."""
    FIELDS[resource] = fields
    return fields


def catalog(db: Session, resource: str) -> list[FilterField]:
    out = []
    for key, f in FIELDS[resource].items():
        options = None
        if f.type == 'enum':
            if f.options:
                values = f.options(db)
            elif isinstance(f.col, Column) or (f.col is not None and isinstance(getattr(f.col, 'expression', None), Column)):
                values = db.scalars(select(f.col).distinct().where(f.col.isnot(None), f.col != '').limit(200))
            else:
                values = (f.labels or {}).keys()
            values = sorted({str(v) for v in values if v not in (None, '')})[:200]
            options = [FilterOption(value=v, label=(f.labels or {}).get(v, v)) for v in values]
        out.append(FilterField(key=key, label=f.label, type=f.type, options=options))
    return out


def parse_filters(raw: list[str], fields: dict[str, F]) -> list[tuple[F, str, str]]:
    out = []
    for item in raw:
        key, _, rest = item.partition(':')
        op, _, arg = rest.partition(':')
        if key not in fields:
            raise HTTPException(422, f'Unknown filter field: {key}')
        if op not in OPS:
            raise HTTPException(422, f'Unknown filter operator: {op}')
        out.append((fields[key], op, arg))
    return out


def _like_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _date_arg(arg: str) -> str:
    # SQLite stores datetimes as 'YYYY-MM-DD HH:MM:SS.ffffff'.
    return arg.replace('T', ' ').rstrip('Z')


def sql_clause(f: F, op: str, arg: str) -> ColumnElement:
    if f.where:
        return f.where(op, arg)
    c = f.col
    if op == 'empty':
        return or_(c.is_(None), c == '') if f.type in ('text', 'enum') else c.is_(None)
    if op == 'notEmpty':
        return and_(c.isnot(None), c != '') if f.type in ('text', 'enum') else c.isnot(None)
    if f.type == 'bool':
        want = arg == 'true'
        if op == 'ne':
            want = not want
        return c.is_(True) if want else or_(c.is_(False), c.is_(None))
    if op in ('in', 'notIn'):
        items = [unquote(a) for a in arg.split(',')]
        return c.in_(items) if op == 'in' else or_(c.is_(None), c.not_in(items))
    if f.type == 'number':
        n = float(arg)
        return {'eq': c == n, 'ne': c != n, 'gt': c > n, 'lt': c < n}.get(op, true())
    if f.type == 'date' and op in ('gt', 'lt'):
        return c > _date_arg(arg) if op == 'gt' else c < _date_arg(arg)
    e = _like_escape(arg)
    like = {'contains': f'%{e}%', 'notContains': f'%{e}%', 'startsWith': f'{e}%', 'endsWith': f'%{e}', 'eq': e, 'ne': e}
    if op in like:
        clause = c.ilike(like[op], escape='\\')
        return or_(c.is_(None), not_(clause)) if op in ('notContains', 'ne') else clause
    if op in ('gt', 'lt'):
        return c > arg if op == 'gt' else c < arg
    raise HTTPException(422, f'Operator {op} does not apply to {f.label}')


def py_match(f: F, row: Any, op: str, arg: str) -> bool:
    raw = f.get(row)
    vals = [v for v in (raw if isinstance(raw, list) else [raw]) if v not in (None, '')]
    s = [str(v).lower() for v in vals]
    a = arg.lower()
    if op == 'empty':
        return not vals
    if op == 'notEmpty':
        return bool(vals)
    if f.type == 'bool':
        return (bool(raw) == (arg == 'true')) == (op != 'ne')
    if op in ('in', 'notIn'):
        hit = any(str(v) in {unquote(x) for x in arg.split(',')} for v in vals)
        return hit if op == 'in' else not hit
    if f.type == 'number':
        n, x = float(arg), float(raw or 0)
        return {'eq': x == n, 'ne': x != n, 'gt': x > n, 'lt': x < n}.get(op, True)
    return {
        'contains': lambda: any(a in v for v in s),
        'notContains': lambda: not any(a in v for v in s),
        'startsWith': lambda: any(v.startswith(a) for v in s),
        'endsWith': lambda: any(v.endswith(a) for v in s),
        'eq': lambda: a in s,
        'ne': lambda: a not in s,
        'gt': lambda: any(str(v) > arg for v in vals),
        'lt': lambda: any(str(v) < arg for v in vals),
    }[op]()


# --- Paging ------------------------------------------------------------------


def _bad_sort(sort: str) -> HTTPException:
    return HTTPException(422, f'Unknown sort key: {sort}')


def paginate(db: Session, stmt: Select, q: PageQuery, *, resource: str | None = None, search: Iterable = (),
             sorts: dict[str, Any] | None = None, build: Callable[[list], list] = lambda rows: rows) -> Page:
    """Filter, search, count, sort and slice `stmt`, then turn the page of rows into items with `build`.

    `search`: columns matched by `q` (case-insensitive substring, OR-ed).
    `sorts`: sort key -> column; the first entry is the default order.
    Single-entity selects give `build` ORM objects, otherwise Row tuples.
    """
    if resource:
        clauses = [sql_clause(f, op, arg) for f, op, arg in parse_filters(q.filter, FIELDS[resource])]
        if clauses:
            stmt = stmt.where(or_(*clauses) if q.match == 'any' else and_(*clauses))
    search = list(search)
    if q.q and search:
        pattern = f'%{_like_escape(q.q)}%'
        stmt = stmt.where(or_(*(c.ilike(pattern, escape='\\') for c in search)))
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    sorts = sorts or {}
    if q.sort and q.sort not in sorts:
        raise _bad_sort(q.sort)
    key = q.sort or next(iter(sorts), None)
    if key:
        col = sorts[key]
        stmt = stmt.order_by(col.desc() if q.order == 'desc' else col.asc())
    stmt = stmt.limit(q.page_size).offset((q.page - 1) * q.page_size)
    res = db.execute(stmt)
    rows = res.scalars().all() if len(stmt.column_descriptions) == 1 else res.all()
    return Page(items=build(list(rows)), total=total, page=q.page, page_size=q.page_size)


def paginate_list(items: list, q: PageQuery, *, resource: str | None = None,
                  text: Callable[[Any], str] = lambda r: '', sorts: dict[str, Callable[[Any], Any]] | None = None) -> Page:
    """`paginate` for in-memory items (policies, named locations, computed rows). Fields use `F.get`."""
    if resource:
        fs = parse_filters(q.filter, FIELDS[resource])
        if fs:
            test = any if q.match == 'any' else all
            items = [r for r in items if test(py_match(f, r, op, arg) for f, op, arg in fs)]
    if q.q:
        needle = q.q.lower()
        items = [r for r in items if needle in text(r).lower()]
    sorts = sorts or {}
    if q.sort and q.sort not in sorts:
        raise _bad_sort(q.sort)
    key = q.sort or next(iter(sorts), None)
    if key:
        items = sorted(items, key=lambda r: (sorts[key](r) is None, sorts[key](r) or 0), reverse=q.order == 'desc')
    start = (q.page - 1) * q.page_size
    return Page(items=items[start:start + q.page_size], total=len(items), page=q.page, page_size=q.page_size)


# --- Object references -------------------------------------------------------

DIRECTORY = ObjectRef(id=None, type='keyword', displayName='Directory')


def keyword(name: str) -> ObjectRef:
    return ObjectRef(id=None, type='keyword', displayName=name)


def value(name: str) -> ObjectRef:
    return ObjectRef(id=None, type='value', displayName=name)


def unresolved(oid: str) -> ObjectRef:
    return ObjectRef(id=oid, type='unknown', displayName=oid)


# (model, ref type, id column, secondary identifier column). Roles are keyed by template id.
REF_SOURCES = [
    (d.User, 'user', d.User.objectId, d.User.userPrincipalName),
    (d.Group, 'group', d.Group.objectId, None),
    (d.ServicePrincipal, 'servicePrincipal', d.ServicePrincipal.objectId, d.ServicePrincipal.appId),
    (d.Device, 'device', d.Device.objectId, None),
    (d.Application, 'application', d.Application.objectId, d.Application.appId),
    (d.AdministrativeUnit, 'administrativeUnit', d.AdministrativeUnit.objectId, None),
    (d.RoleDefinition, 'role', d.RoleDefinition.templateId, None),
    (d.DirectoryRole, 'role', d.DirectoryRole.roleTemplateId, None),
]


def resolve_refs(db: Session, ids: Iterable[str | None]) -> dict[str, ObjectRef]:
    """Batch-resolve object ids (any type) to refs. Ids that match nothing map to an `unknown` ref.

    Directory roles resolve by template id, and also by DirectoryRoles.objectId (the id used in the
    lnk_role_member_* tables); either way the ref id is the template id.
    """
    todo = {i for i in ids if i}
    out: dict[str, ObjectRef] = {}
    chunks = lambda s: (list(s)[i:i + 500] for i in range(0, len(s), 500))  # noqa: E731
    for model, typ, idcol, subcol in REF_SOURCES:
        if not todo:
            break
        cols = [idcol, model.displayName] + ([subcol] if subcol is not None else [])
        for chunk in chunks(todo):
            for row in db.execute(select(*cols).where(idcol.in_(chunk))):
                out[row[0]] = ObjectRef(id=row[0], type=typ, displayName=row[1] or row[0],
                                        sub=row[2] if subcol is not None else None)
        todo -= out.keys()
    if todo:
        for chunk in chunks(todo):
            for oid, tid, name in db.execute(select(d.DirectoryRole.objectId, d.DirectoryRole.roleTemplateId,
                                                    d.DirectoryRole.displayName).where(d.DirectoryRole.objectId.in_(chunk))):
                out[oid] = ObjectRef(id=tid, type='role', displayName=name or tid)
        for chunk in chunks(todo - out.keys()):
            for oid, name, ptype in db.execute(select(d.Policy.objectId, d.Policy.displayName, d.Policy.policyType)
                                               .where(d.Policy.objectId.in_(chunk))):
                out[oid] = ObjectRef(id=oid, type='namedLocation' if ptype == 6 else 'policy', displayName=name or oid)
    for oid in ids:
        if oid and oid not in out:
            out[oid] = unresolved(oid)
    return out


def resolve_ref(db: Session, oid: str) -> ObjectRef:
    return resolve_refs(db, [oid])[oid]


def resolve_appids(db: Session, app_ids: Iterable[str]) -> dict[str, ObjectRef]:
    """appId -> service principal ref (application ref when the tenant has no SP for it)."""
    todo = {a for a in app_ids if a}
    out = {}
    for model, typ in ((d.ServicePrincipal, 'servicePrincipal'), (d.Application, 'application')):
        if not todo:
            break
        for oid, name, app_id in db.execute(select(model.objectId, model.displayName, model.appId).where(model.appId.in_(todo))):
            out[app_id] = ObjectRef(id=oid, type=typ, displayName=name or app_id, sub=app_id)
        todo -= out.keys()
    for app_id in todo:
        out[app_id] = ObjectRef(id=None, type='unknown', displayName=app_id, sub=app_id)
    return out


# --- Membership CTEs ---------------------------------------------------------

gm_user, gm_group = d.lnk_group_member_user, d.lnk_group_member_group


def descendant_groups(group_id: str):
    """CTE (column `id`): the group and every group nested under it, at any depth. Cycle-safe (UNION)."""
    cte = select(literal(group_id).label('id')).cte('descendants', recursive=True)
    return cte.union(select(gm_group.c.childGroup).join(cte, gm_group.c.Group == cte.c.id))


def ancestor_groups(seed: Select):
    """CTE (column `id`): groups listed by `seed` (a one-column select of group ids) and all their parents."""
    cte = seed.cte('ancestors', recursive=True)
    return cte.union(select(gm_group.c.Group).join(cte, gm_group.c.childGroup == cte.c[0]))


def member_groups_select(member_id: str) -> Select:
    """Groups an object of any type is a direct member of (one column)."""
    links = [(d.lnk_group_member_user, 'User'), (d.lnk_group_member_group, 'childGroup'),
             (d.lnk_group_member_device, 'Device'), (d.lnk_group_member_serviceprincipal, 'ServicePrincipal'),
             (d.lnk_group_member_contact, 'Contact')]
    return union(*(select(t.c.Group.label('id')).where(t.c[col] == member_id) for t, col in links))


def transitive_groups_of(member_id: str):
    """CTE (column `id`): every group the object belongs to, directly or through nesting."""
    return ancestor_groups(select(member_groups_select(member_id).subquery().c.id))


# --- Domain helpers shared by several slices --------------------------------

def mfa_summary(user: d.User) -> dict:
    """MfaSummary from strongAuthenticationDetail and searchableDeviceKey (FIDO / NGC = Windows Hello)."""
    detail = user.strongAuthenticationDetail or {}
    methods = detail.get('methods') or []
    requirements = detail.get('requirements') or []
    keys = user.searchableDeviceKey or []
    usage = [k.get('usage') for k in keys if isinstance(k, dict)]
    return {
        'methods': [m['methodType'] for m in methods if m.get('methodType')],
        'defaultMethod': next((m['methodType'] for m in methods if m.get('isDefault')), None),
        'perUserMfa': requirements[0].get('state') if requirements else None,
        'fido': usage.count('FIDO'),
        'windowsHello': usage.count('NGC'),
    }


# Tier-0 directory roles, by template id.
PRIVILEGED_ROLES = frozenset({
    '62e90394-69f5-4237-9190-012177145e10',  # Global Administrator
    'e8611ab8-c189-46e8-94e1-60213ab1f814',  # Privileged Role Administrator
    '7be44c8a-adaf-4e2a-84d6-ab2649e08a13',  # Privileged Authentication Administrator
    '9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3',  # Application Administrator
    '158c047a-c907-4556-b7ef-446551a6b5f7',  # Cloud Application Administrator
    'b1be1c3e-b65d-4f19-8427-f6fa0d97feb9',  # Conditional Access Administrator
    '194ae4cb-b126-40b2-bd5b-6091b380977d',  # Security Administrator
    '29232cdf-9323-42fd-ade2-1d097af3e4de',  # Exchange Administrator
    'fe930be7-5e62-47db-91af-98c3a49a38b1',  # User Administrator
    'c4e39bd9-1100-46d3-8c65-fb160da0071f',  # Authentication Administrator
    '3a2c62db-5318-420d-8d74-23affee5d9d5',  # Intune Administrator
    'd29b2b05-8046-44ba-8758-1e26182fcf32',  # Directory Synchronization Accounts
    '8ac3fc64-6eca-42ea-9e69-59f4c7b60eb2',  # Hybrid Identity Administrator
    '966707d0-3269-4727-9be2-8c3a10f19b9d',  # Password Administrator
    '7698a772-787b-4ac8-901f-60d6b08affd2',  # Cloud Device Administrator
})

# ponytail: name pattern, not a permission model. Replace with a curated per-permission list if it misfires.
_PRIVILEGED_PERMISSION = re.compile(
    r'\.ReadWrite\.All$|^(RoleManagement|AppRoleAssignment|Directory|Policy\.ReadWrite|Mail)\.|FullControl'
    r'|^full_access_as_app$|^EWS\.AccessAsUser\.All$|^user_impersonation$', re.I)


def is_privileged_permission(value: str | None) -> bool:
    """High-impact app role or OAuth2 scope value, e.g. RoleManagement.ReadWrite.Directory."""
    return bool(value and _PRIVILEGED_PERMISSION.search(value))


__all__ = [
    'Db', 'F', 'FIELDS', 'register', 'catalog', 'paginate', 'paginate_list', 'has_table', 'not_found', 'iso',
    'DIRECTORY', 'keyword', 'value', 'unresolved', 'resolve_refs', 'resolve_ref', 'resolve_appids',
    'descendant_groups', 'ancestor_groups', 'member_groups_select', 'transitive_groups_of',
    'mfa_summary', 'PRIVILEGED_ROLES', 'is_privileged_permission',
]
