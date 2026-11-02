"""The local server: the API under /api, and the built screen (Program/dist) for everything else."""
import json
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from worldsmith import NAME, VERSION, drafts, models, settings, towns, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError, require

HERE = Path(__file__).resolve().parent
DIST = HERE.parent / 'dist'
SOURCE = HERE / 'dungeon_format' / 'SOURCE.json'


def format_source() -> dict:
    """Which Dungeon commit the vendored world format came from, and the package format number it writes."""
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    return {'repo': source['repo'], 'commit': source['commit'], 'package_format': packages.FORMAT,
            'sections': list(packages.SECTIONS), 'engine_kinds': list(packages.ENGINE_KINDS)}


class SettingsBody(BaseModel):
    dungeon_checkout: str | None = None


class OpenBody(BaseModel):
    builtin: str | None = None
    folder: str | None = None


class TownBody(OpenBody):
    town: str


class PartBody(TownBody):
    kind: str
    data: dict


class ModelBody(BaseModel):
    provider: str
    model: str = ''
    base_url: str = ''
    key: str | None = None


class DraftBody(TownBody):
    target: str
    ask: str = ''


class DecideBody(OpenBody):
    approve: bool
    entries: list | None = None


def worlds_listing() -> dict:
    """What can be opened: the checkout's built-in worlds (or why they can't be read), and recent world folders."""
    saved = settings.load()
    builtin, problem = [], ''
    if saved['dungeon_checkout']:
        try:
            builtin = worlds.builtin_worlds(Path(saved['dungeon_checkout']))
        except DomainError as error:
            problem = error.message
    recent = []
    for folder in saved['recent_folders']:
        path = Path(folder) / 'world.json'
        if path.is_file():
            try:
                recent.append({'folder': folder, 'name': packages.read_json(path).get('name', Path(folder).name)})
            except (DomainError, AttributeError):
                continue
    return {'checkout': saved['dungeon_checkout'], 'checkout_problem': problem, 'builtin': builtin, 'recent': recent}


def opened_from(body: OpenBody) -> worlds.Opened:
    require(bool(body.builtin) != bool(body.folder), 'Open either a built-in world or a world folder.', 422)
    if body.builtin:
        checkout = settings.load()['dungeon_checkout']
        require(bool(checkout), 'Set your Dungeon checkout in Settings first.', 409)
        return worlds.builtin(Path(checkout), body.builtin)
    opened = worlds.folder(Path(body.folder))
    settings.remember_folder(opened.folder)
    return opened


def api() -> APIRouter:
    router = APIRouter(prefix='/api')

    @router.get('/health')
    def health():
        return {'ok': True, 'name': NAME, 'version': VERSION}

    @router.get('/format')
    def dungeon_format():
        return format_source()

    @router.get('/settings')
    def read_settings():
        return settings.load()

    @router.put('/settings')
    def write_settings(body: SettingsBody):
        checkout = (body.dungeon_checkout or '').strip() or None
        if checkout:
            worlds.checkout_folders(Path(checkout))
        return settings.save({'dungeon_checkout': checkout})

    @router.get('/worlds')
    def list_worlds():
        return worlds_listing()

    @router.post('/worlds/open')
    def open_world(body: OpenBody):
        return worlds.overview(opened_from(body))

    router.include_router(town_api())
    router.include_router(draft_api())
    return router


def draft_api() -> APIRouter:
    router = APIRouter()

    @router.get('/models')
    def read_models():
        return models.config()

    @router.put('/models')
    def write_models(body: ModelBody):
        return models.configure(body.provider, body.model, body.base_url, body.key)

    @router.post('/drafts')
    def make_draft(body: DraftBody):
        return drafts.draft(opened_from(body), body.town, body.target, body.ask)

    @router.post('/drafts/pending')
    def pending_drafts(body: OpenBody):
        return drafts.pending(opened_from(body))

    @router.post('/drafts/{draft_id}/decide')
    def decide_draft(draft_id: int, body: DecideBody):
        return drafts.decide(opened_from(body), draft_id, body.approve, body.entries)

    return router


def town_api() -> APIRouter:
    router = APIRouter()

    @router.get('/schema/city')
    def city_schema():
        return towns.city_schema()

    @router.post('/towns/read')
    def read_town(body: TownBody):
        return towns.read(opened_from(body), body.town)

    @router.put('/towns/part')
    def save_part(body: PartBody):
        return towns.save(opened_from(body), body.town, body.kind, body.data)

    @router.post('/towns/undo')
    def undo_town(body: TownBody):
        return towns.undo(opened_from(body), body.town)

    return router


def create_app(dist: Path = DIST) -> FastAPI:
    app = FastAPI(title=NAME, version=VERSION)

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, error: DomainError):
        return JSONResponse({'error': error.message, 'code': error.code}, status_code=error.status)

    app.include_router(api())
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
