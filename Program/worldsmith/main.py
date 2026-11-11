"""The local server: the API under /api, and the built screen (Program/dist) for everything else."""
import json
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from worldsmith import (
    NAME,
    VERSION,
    cast_import,
    chat,
    drafts,
    dungeon_run,
    hexmap,
    maps,
    mermaid,
    models,
    names,
    package_files,
    progress,
    settings,
    towns,
    wizard,
    worldgen,
    worlds,
)
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


class ProgressBody(OpenBody):
    job: str = 'world'


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


class ChatBody(OpenBody):
    message: str
    town: str | None = None


class NewTownBody(OpenBody):
    pitch: str
    name: str = ''
    near: str | None = None
    replaces: str | None = None
    hours: float = 8
    terrain: str = 'the road'
    danger: str = 'low'


class NamesBody(BaseModel):
    era: str = 'modern'
    names: dict | None = None
    kinds: dict | None = None
    seed: str = 'worldsmith'


class NewWorldBody(BaseModel):
    name: str
    pitch: str = ''
    parent: str | None = None


class WorldDraftBody(OpenBody):
    pitch: str = ''
    size: str = 'medium'


class CheckBody(TownBody):
    map: bool = False
    seed: str = 'worldsmith'


class ExportBody(OpenBody):
    to: str | None = None


class ImportBody(BaseModel):
    package: str
    folder: str


class MapBody(OpenBody):
    map: str
    town: str | None = None


class MapSaveBody(MapBody):
    graph: dict


class NewInteriorBody(OpenBody):
    name: str
    id: str | None = None
    style: str = 'other'
    summary: str = ''
    node: str | None = None
    city: str | None = None
    place: str | None = None


class HexReadBody(OpenBody):
    size: str = 'medium'


class HexPaintBody(OpenBody):
    columns: int
    rows: int
    paint: list[str]
    seed: str = 'worldsmith'
    wind: str = 'west'
    rivers: str = 'some'


class HexTownBody(OpenBody):
    q: int
    r: int
    name: str
    summary: str = ''


class MapTextBody(BaseModel):
    graph: dict
    direction: str = 'LR'


class MapParseBody(BaseModel):
    text: str
    graph: dict


class CastImportBody(OpenBody):
    cast: dict  # a Dramatis `prospero-cast` file, read by cast_import.read
    town: str = Field(default='', max_length=80)  # where the cast's people live, as notables; '' leaves them out


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
    router.include_router(package_api())
    router.include_router(map_api())
    router.include_router(hex_api())
    router.include_router(draft_api())
    router.include_router(world_api())
    router.include_router(cast_api())
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

    @router.post('/towns/new')
    def new_town(body: NewTownBody):
        return wizard.draft_town(opened_from(body), body.pitch, body.name, body.near, body.replaces, body.hours,
                                 body.terrain, body.danger)

    @router.post('/chat')
    def read_chat(body: OpenBody):
        return chat.history(opened_from(body))

    @router.post('/chat/say')
    def say(body: ChatBody):
        return chat.say(opened_from(body), body.message, body.town)

    @router.post('/chat/clear')
    def clear_chat(body: OpenBody):
        return chat.clear(opened_from(body))

    @router.post('/drafts/{draft_id}/decide')
    def decide_draft(draft_id: int, body: DecideBody):
        return drafts.decide(opened_from(body), draft_id, body.approve, body.entries)

    return router


def world_api() -> APIRouter:
    """The new world wizard (worldsmith/worldgen.py)."""
    router = APIRouter()

    @router.post('/worlds/new')
    def new_world(body: NewWorldBody):
        opened = worldgen.new_world(body.name, body.pitch, body.parent)
        return {'folder': str(opened.folder), 'overview': worlds.overview(opened)}

    @router.post('/worlds/draft')
    def draft_world(body: WorldDraftBody):
        return worldgen.draft_world(opened_from(body), body.pitch, body.size)

    @router.post('/worlds/draft/progress')
    def draft_progress(body: OpenBody):
        return worldgen.draft_progress(opened_from(body))

    @router.post('/progress')
    def job_progress(body: ProgressBody):
        """How far a world, town or list draft has got (worldsmith/progress.py)."""
        return progress.of(opened_from(body), body.job)

    @router.post('/worlds/town-stops')
    def town_stops(body: OpenBody):
        return worldgen.town_stops(opened_from(body))

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

    @router.post('/names/view')
    def names_view(body: NamesBody):
        return names.view({'era': body.era, 'names': body.names, 'kinds': body.kinds}, body.seed)

    @router.post('/towns/undo')
    def undo_town(body: TownBody):
        return towns.undo(opened_from(body), body.town)

    @router.post('/towns/check')
    def check_town(body: CheckBody):
        city = towns.read(opened_from(body), body.town)['parts']['cities']
        return dungeon_run.check_city(city, body.map, body.seed)

    return router


def map_api() -> APIRouter:
    router = APIRouter()

    @router.post('/maps/read')
    def read_map(body: MapBody):
        return maps.read(opened_from(body), body.map, body.town)

    @router.put('/maps/save')
    def save_map(body: MapSaveBody):
        return maps.save(opened_from(body), body.map, body.graph, body.town)

    @router.post('/maps/undo')
    def undo_map(body: MapBody):
        return maps.undo(opened_from(body), body.map, body.town)

    @router.post('/interiors/list')
    def list_interiors(body: OpenBody):
        return {'interiors': maps.interiors(opened_from(body)), 'styles': list(maps.STYLES)}

    @router.post('/interiors/new')
    def new_interior(body: NewInteriorBody):
        return maps.new_interior(opened_from(body), body.model_dump(exclude={'builtin', 'folder'}))

    @router.post('/maps/text')
    def map_text(body: MapTextBody):
        return {'mermaid': mermaid.text(body.graph, 'TB' if body.direction == 'TB' else 'LR')}

    @router.post('/maps/parse')
    def map_parse(body: MapParseBody):
        return mermaid.parse(body.text, body.graph)

    return router


def hex_api() -> APIRouter:
    """The world map painter (hexmap.py)."""
    router = APIRouter()

    @router.post('/hexes/read')
    def read_hexes(body: HexReadBody):
        return hexmap.read(opened_from(body), body.size)

    @router.post('/hexes/generate')
    def generate_hexes(body: HexPaintBody):
        return hexmap.generate(opened_from(body), body.model_dump(exclude={'builtin', 'folder'}))

    @router.put('/hexes/save')
    def save_hexes(body: HexPaintBody):
        return hexmap.save(opened_from(body), body.model_dump(exclude={'builtin', 'folder'}))

    @router.post('/hexes/undo')
    def undo_hexes(body: OpenBody):
        return hexmap.undo(opened_from(body))

    @router.post('/hexes/town')
    def town_from_site(body: HexTownBody):
        return hexmap.add_town(opened_from(body), body.model_dump(exclude={'builtin', 'folder'}))

    return router


def cast_api() -> APIRouter:
    """A Dramatis cast's sides brought in as the world's factions (worldsmith/cast_import.py)."""
    router = APIRouter()

    @router.post('/factions/import')
    def import_cast(body: CastImportBody):
        return cast_import.draft(opened_from(body), body.cast, body.town)

    @router.post('/factions/imports')
    def cast_imports(body: OpenBody):
        return cast_import.imports(opened_from(body))

    @router.post('/factions/undo')
    def undo_cast(body: OpenBody):
        return cast_import.undo(opened_from(body))

    return router


def package_api() -> APIRouter:
    router = APIRouter()

    @router.post('/worlds/export')
    def export_world(body: ExportBody):
        return package_files.export_world(opened_from(body), body.to)

    @router.post('/worlds/install')
    def install_world(body: OpenBody):
        return package_files.install_world(opened_from(body))

    @router.post('/worlds/import')
    def import_world(body: ImportBody):
        opened = package_files.import_package(body.package, body.folder)
        return {'folder': str(opened.folder), 'world': worlds.overview(opened)}

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
