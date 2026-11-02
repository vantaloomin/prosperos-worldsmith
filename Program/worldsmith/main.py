"""The local server: the API under /api, and the built screen (Program/dist) for everything else."""
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from worldsmith import NAME, VERSION
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError

HERE = Path(__file__).resolve().parent
DIST = HERE.parent / 'dist'
SOURCE = HERE / 'dungeon_format' / 'SOURCE.json'


def format_source() -> dict:
    """Which Dungeon commit the vendored world format came from, and the package format number it writes."""
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    return {'repo': source['repo'], 'commit': source['commit'], 'package_format': packages.FORMAT,
            'sections': list(packages.SECTIONS), 'engine_kinds': list(packages.ENGINE_KINDS)}


def create_app(dist: Path = DIST) -> FastAPI:
    app = FastAPI(title=NAME, version=VERSION)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, error: DomainError):
        return JSONResponse({'error': error.message, 'code': error.code}, status_code=error.status)

    @app.get('/api/health')
    def health():
        return {'ok': True, 'name': NAME, 'version': VERSION}

    @app.get('/api/format')
    def dungeon_format():
        return format_source()

    if (dist / 'index.html').is_file():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

        @app.get('/{path:path}', include_in_schema=False)
        def screen(path: str):
            wanted = (dist / path).resolve()
            if path and wanted.is_file() and wanted.is_relative_to(dist.resolve()):
                return FileResponse(wanted)
            return FileResponse(dist / 'index.html')

    return app


app = create_app()
