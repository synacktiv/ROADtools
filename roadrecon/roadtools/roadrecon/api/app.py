"""FastAPI application: the API routers plus the built frontend (dist_gui) with an SPA fallback."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .db import ensure_indexes, make_engine, make_sessionmaker
from .routers import apps, compliance, devices, governance, grants, groups, meta, policies, roles, sql, users

DIST = Path(__file__).resolve().parent.parent / 'dist_gui'


def create_app(dburl: str | None = None, read_only: bool | None = None) -> FastAPI:
    """`dburl` defaults to $ROADRECON_DB, then roadrecon.db. No DB access happens until startup."""
    dburl = dburl or os.environ.get('ROADRECON_DB', 'roadrecon.db')
    if read_only is None:
        read_only = os.environ.get('ROADRECON_READ_ONLY') == '1'
    engine = make_engine(dburl, read_only)

    @asynccontextmanager
    async def lifespan(_app):
        if not read_only:
            ensure_indexes(engine)
        yield
        engine.dispose()

    app = FastAPI(title='ROADrecon', version='2.0.0', lifespan=lifespan, separate_input_output_schemas=False)
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    for module in (meta, users, groups, devices, apps, roles, grants, governance, policies, compliance, sql):
        app.include_router(module.router)

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(_req: Request, _exc: NotImplementedError):
        return JSONResponse({'detail': 'Not implemented yet'}, status_code=501)

    if (DIST / 'index.html').is_file():
        if (DIST / 'assets').is_dir():
            app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

        @app.get('/{path:path}', include_in_schema=False)
        def spa(path: str):
            if path.startswith('api/'):
                return JSONResponse({'detail': 'Not Found'}, status_code=404)
            f = (DIST / path).resolve()
            if path and f.is_file() and f.is_relative_to(DIST):
                return FileResponse(f)
            return FileResponse(DIST / 'index.html')
    return app
