"""Opening a world: a built-in world in a Dungeon checkout, or a world folder anywhere.

A world folder is Dungeon's package folder (worldsmith.dungeon_format.packages). A built-in world keeps its towns'
engine data outside that folder, in the checkout's `Program/dungeon/world/data/<kind>/`, gathered the same way
Dungeon's packages.engine_for does. Worldsmith opens a world even when it has problems, and lists them, so a world
can be mended here; Dungeon's own reader refuses it until it is.
"""
from dataclasses import dataclass
from pathlib import Path

from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import require

PACKAGES = Path('Program/dungeon/world/packages')
DATA = Path('Program/dungeon/world/data')
WORLD_KINDS = ('travel', 'arcs', 'factions', 'tiers')
TOWN_KINDS = ('cities', 'adventures', 'items', 'finds', 'premades')


@dataclass(frozen=True)
class Opened:
    """Where an open world lives: its package folder, and for a built-in world the checkout's data folder."""
    folder: Path
    data: Path | None = None

    @property
    def kind(self) -> str:
        return 'builtin' if self.data else 'folder'


def checkout_folders(checkout: Path) -> tuple[Path, Path]:
    root = Path(checkout)
    require((root / PACKAGES).is_dir() and (root / DATA).is_dir(),
            f'{root} does not look like a prosperos-dungeon checkout (no {PACKAGES.as_posix()}).', 404)
    return root / PACKAGES, root / DATA


def builtin_worlds(checkout: Path) -> list[dict]:
    folder, _ = checkout_folders(checkout)
    found = []
    for path in sorted(folder.iterdir()):
        if (path / 'world.json').is_file():
            world = packages.read_json(path / 'world.json')
            found.append({'id': path.name, 'name': world.get('name', path.name), 'genre': world.get('genre', ''),
                          'pitch': world.get('pitch', '')})
    return found


def builtin(checkout: Path, world_id: str) -> Opened:
    folder, data = checkout_folders(checkout)
    require(bool(packages.ID.match(world_id)) and (folder / world_id / 'world.json').is_file(),
            f'{world_id} is not a world in this Dungeon checkout.', 404)
    return Opened(folder / world_id, data)


def folder(path: Path) -> Opened:
    path = Path(path)
    require(path.is_dir(), f'{path} is not a folder.', 404)
    require((path / 'world.json').is_file(), f'{path} has no world.json, so it is not a world folder.', 422)
    return Opened(path)


def engine_for(data: Path, world_id: str) -> dict:
    """A built-in world's engine data from a checkout's data folder; mirrors Dungeon's packages.engine_for."""
    found = {}
    for kind in WORLD_KINDS:
        path = data / kind / f'{world_id}.json'
        if path.is_file():
            found[(kind, world_id)] = packages.read_json(path)
    towns = {node['city'] for node in (found.get(('travel', world_id)) or {}).get('nodes', []) if node.get('city')}
    for town in sorted(towns):
        for kind in ('adventures', 'items', 'finds', 'premades', 'cities'):
            path = data / kind / f'{town}.json'
            if path.is_file():
                found[(kind, town)] = packages.read_json(path)
    return found


def contents(opened: Opened) -> tuple[dict, list[str]]:
    """Everything the world holds, as Dungeon's package keeps it, and what is wrong with it."""
    root, problems = opened.folder, []
    world = packages.read_json(root / 'world.json')
    if not (isinstance(world, dict) and world.get('id') and world.get('name')):
        problems.append('world.json needs an id and a name')
        world = world if isinstance(world, dict) else {}
    sections = {}
    for name, key in packages.SECTIONS.items():
        path = root / f'{name}.json'
        if path.is_file():
            data = packages.read_json(path)
            if isinstance(data, dict) and isinstance(data.get(key), list):
                sections[name] = data
            else:
                problems.append(f'{name}.json needs a list under "{key}"')
    documents = {path.relative_to(root).as_posix(): path.read_text(encoding='utf-8')
                 for path in sorted(root.rglob('*.md')) if 'engine' not in path.relative_to(root).parts}
    engine = engine_for(opened.data, world.get('id') or root.name) if opened.data else {}
    for kind in packages.ENGINE_KINDS:
        for path in sorted((root / 'engine' / kind).glob('*.json')):
            engine[(kind, path.stem)] = packages.read_json(path)
    found = {'world': world, 'sections': sections, 'documents': documents, 'engine': engine, 'assets': {}}
    return found, problems + packages.validate(found)


def towns(found: dict) -> list[dict]:
    """The world's towns: every city file, with which of a town's engine parts it has. Roads and wilds (a city with
    no street map, like vallarith-road) are listed as such."""
    engine = found['engine']
    listed = []
    for (kind, key), city in sorted(engine.items()):
        if kind != 'cities' or not isinstance(city, dict):
            continue
        listed.append({'id': key, 'name': city.get('name', key), 'summary': city.get('summary', ''),
                       'road': (city.get('town_map') or {}).get('style') == 'none',
                       'places': len(city.get('places') or []), 'notables': len(city.get('notables') or []),
                       'parts': [part for part in TOWN_KINDS if (part, key) in engine]})
    return listed


def overview(opened: Opened) -> dict:
    found, problems = contents(opened)
    world = found['world']
    sections = {}
    for name, data in found['sections'].items():
        entries = [entry for entry in data[packages.SECTIONS[name]] if isinstance(entry, dict)]
        sections[name] = {'entries': len(entries),
                          'hidden': sum(1 for entry in entries if packages.hidden(name, entry))}
    engine = {}
    for kind, _ in found['engine']:
        engine[kind] = engine.get(kind, 0) + 1
    travel = found['engine'].get(('travel', world.get('id'))) or {}
    stops = [{'id': node.get('id'), 'name': node.get('name'), 'city': node.get('city'),
              'road': ((found['engine'].get(('cities', node.get('city'))) or {}).get('town_map') or {}).get('style') == 'none'}
             for node in travel.get('nodes') or [] if isinstance(node, dict)]
    return {'world': {key: world.get(key) for key in ('id', 'name', 'genre', 'pitch', 'default_ruleset', 'status')},
            'stops': stops,
            'kind': opened.kind, 'folder': str(opened.folder), 'towns': towns(found), 'sections': sections,
            'documents': len(found['documents']), 'engine': engine, 'problems': problems}
