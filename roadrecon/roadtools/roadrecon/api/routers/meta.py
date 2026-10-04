"""S9 meta: stats, tenant, global search, filter catalogues."""
from typing import Annotated

from fastapi import APIRouter, Query

from ..common import Db, catalog
from ..models import FilterField, FilterResource, SearchResult, Stats, Tenant

router = APIRouter(prefix='/api', tags=['meta'])


@router.get('/filters/{resource}')
def get_filters(resource: FilterResource, db: Db) -> list[FilterField]:
    return catalog(db, resource)


@router.get('/stats')
def get_stats(db: Db) -> Stats:
    raise NotImplementedError


@router.get('/tenant')
def get_tenant(db: Db) -> Tenant:
    raise NotImplementedError


@router.get('/search')
def search(q: Annotated[str, Query(min_length=1)], db: Db, limit: Annotated[int, Query(ge=1, le=50)] = 5) -> SearchResult:
    """Objects of every type matching `q`, grouped by type, `limit` per type."""
    raise NotImplementedError
