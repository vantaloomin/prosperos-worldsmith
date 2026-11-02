import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture(autouse=True)
def own_home(tmp_path, monkeypatch):
    """Each test keeps its settings in its own folder, never the user's."""
    monkeypatch.setenv('WORLDSMITH_HOME', str(tmp_path / 'home'))


def kingswood() -> dict:
    return json.loads((FIXTURES / 'kingswood.json').read_text(encoding='utf-8'))


def write_files(root: Path, files: dict):
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')


def make_world(folder: Path, with_city: bool = True) -> Path:
    """A small world folder with one region, settlement, faction and person, and (by default) a town's city file."""
    files = {
        'world.json': {'schema_version': 1, 'id': 'testland', 'name': 'Testland', 'default_ruleset': 'marvel'},
        'regions.json': {'regions': [{'id': 'the-vale', 'name': 'The Vale'}]},
        'settlements.json': {'settlements': [{'id': 'kingswood', 'name': 'Kingswood', 'region': 'the-vale'}]},
        'factions.json': {'factions': [{'id': 'timber-guild', 'name': 'The Timber Guild'}]},
        'cast.json': {'cast': [{'id': 'aldous-marr', 'name': 'Aldous Marr', 'faction': 'timber-guild',
                                'settlement': 'kingswood', 'secret': 'In debt to the Guild.'}]},
    }
    if with_city:
        files['engine/cities/kingswood.json'] = kingswood()
    write_files(folder, files)
    (folder / 'canon').mkdir(exist_ok=True)
    (folder / 'canon' / 'overview.md').write_text('# Testland\n', encoding='utf-8')
    return folder


def make_checkout(root: Path) -> Path:
    """A Dungeon checkout holding the Testland world, whose town Kingswood's engine data sits in the data folder."""
    make_world(root / 'Program/dungeon/world/packages/testland', with_city=False)
    road = kingswood() | {'id': 'testland-road', 'name': 'The road', 'town_map': {'style': 'none'}}
    write_files(root / 'Program/dungeon/world/data', {
        'travel/testland.json': {'nodes': [{'id': 'kingswood', 'city': 'kingswood'},
                                           {'id': 'mile-post', 'city': 'testland-road'}]},
        'arcs/testland.json': {'arcs': []},
        'cities/kingswood.json': kingswood(),
        'cities/testland-road.json': road,
        'items/kingswood.json': {'shops': []},
        'cities/elsewhere.json': kingswood() | {'id': 'elsewhere'},
    })
    return root
