"""World package export and import, and checks run by a Dungeon checkout's own code."""
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import kingswood, make_checkout, make_world
from worldsmith import dungeon_run, package_files, settings, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app

# A stand-in for Dungeon's loader and street map engine: refuses a town with no places, maps the rest.
STUB_CATALOG = '''
def prepare(raw):
    if not raw.get('places'):
        raise ValueError('A town needs places.')
    return raw
'''
STUB_TOWNMAP = '''
import os
def has_map(city):
    return (city.get('town_map') or {}).get('style') != 'none'
def build(city, seed):
    return {'town': city['id'], 'seed': seed, 'data_dir': os.environ['DUNGEON_DATA_DIR'], 'lots': []}
'''


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    root = make_checkout(tmp_path / 'dungeon')
    (root / 'Program/dungeon/world/__init__.py').write_text('', encoding='utf-8')
    (root / 'Program/dungeon/__init__.py').write_text('', encoding='utf-8')
    (root / 'Program/dungeon/world/catalog.py').write_text(STUB_CATALOG, encoding='utf-8')
    (root / 'Program/dungeon/townmap.py').write_text(STUB_TOWNMAP, encoding='utf-8')
    settings.save({'dungeon_checkout': str(root)})
    monkeypatch.setenv('WORLDSMITH_DUNGEON_PYTHON', sys.executable)
    return root


def test_a_folder_world_exports_to_a_package_and_imports_back(tmp_path):
    folder = make_world(tmp_path / 'testland')
    (folder / 'assets').mkdir()
    (folder / 'assets' / 'map.png').write_bytes(b'\x89PNG')
    done = package_files.export_world(worlds.folder(folder), str(tmp_path / 'out'))
    assert done['path'].endswith('testland.sqlite') and done['id'] == 'testland' and done['assets'] == 1
    back = package_files.import_package(done['path'], str(tmp_path / 'again'))
    assert packages.folder_contents(back.folder) == packages.folder_contents(folder)
    assert settings.load()['recent_folders'][0] == str(tmp_path / 'again')
    with pytest.raises(DomainError, match='empty folder'):
        package_files.import_package(done['path'], str(tmp_path / 'again'))


def test_a_built_in_world_exports_with_its_town_engine_data(tmp_path):
    root = make_checkout(tmp_path / 'dungeon')
    done = package_files.export_world(worlds.builtin(root, 'testland'))
    assert Path(done['path']) == package_files.default_path('testland')
    engine = packages.read(Path(done['path']))['engine']
    assert ('cities', 'kingswood') in engine and ('travel', 'testland') in engine
    assert ('cities', 'elsewhere') not in engine


def test_a_broken_world_is_not_exported(tmp_path):
    folder = make_world(tmp_path / 'testland')
    (folder / 'cast.json').write_text(json.dumps({'cast': [{'id': 'x', 'name': 'X', 'faction': 'nobody'}]}))
    with pytest.raises(DomainError, match='problems'):
        package_files.export_world(worlds.folder(folder))


def test_the_checkouts_own_code_checks_a_town_and_draws_its_map(checkout):
    done = dungeon_run.check_city(kingswood(), with_map=True, seed='abc')
    assert done['ok'] and done['problems'] == []
    assert done['map']['town'] == 'kingswood' and done['map']['seed'] == 'abc'
    assert done['map']['name'] == kingswood()['name']
    assert not done['map']['data_dir'].startswith(str(settings.home()))  # a scratch folder, never real data
    refused = dungeon_run.check_city(kingswood() | {'places': []}, with_map=True)
    assert not refused['ok'] and refused['problems'] == ['A town needs places.'] and 'map' not in refused
    roadside = dungeon_run.check_city(kingswood() | {'town_map': {'style': 'none'}}, with_map=True)
    assert roadside['ok'] and 'no street map' in roadside['map_problem']


def test_the_api_checks_an_open_town_and_exports_the_world(checkout):
    client = TestClient(create_app())
    done = client.post('/api/towns/check', json={'builtin': 'testland', 'town': 'kingswood', 'map': True}).json()
    assert done['ok'] and done['map']['town'] == 'kingswood'
    exported = client.post('/api/worlds/export', json={'builtin': 'testland'}).json()
    assert Path(exported['path']).is_file()
    imported = client.post('/api/worlds/import', json={'package': exported['path'],
                                                       'folder': str(checkout.parent / 'mine')}).json()
    assert imported['world']['world']['id'] == 'testland' and imported['world']['towns']


def test_without_a_checkout_or_its_python_the_check_says_what_to_do(tmp_path, monkeypatch):
    with pytest.raises(DomainError, match='Dungeon checkout'):
        dungeon_run.check_city(kingswood())
    monkeypatch.delenv('WORLDSMITH_DUNGEON_PYTHON', raising=False)
    settings.save({'dungeon_checkout': str(make_checkout(tmp_path / 'dungeon'))})
    with pytest.raises(DomainError, match='install.bat'):
        dungeon_run.check_city(kingswood())


@pytest.mark.skipif(not os.environ.get('DUNGEON_CHECKOUT'), reason='set DUNGEON_CHECKOUT to an installed Dungeon checkout')
def test_a_real_dungeon_checks_and_maps_kingswood(monkeypatch):
    settings.save({'dungeon_checkout': os.environ['DUNGEON_CHECKOUT']})
    done = dungeon_run.check_city(kingswood(), with_map=True)
    assert done['ok'], done['problems']
    assert done['map']['lots'] and done['map']['districts']


def test_an_own_world_installs_into_dungeons_data_folder_but_a_built_in_one_does_not(tmp_path):
    root = make_checkout(tmp_path / 'dungeon')
    settings.save({'dungeon_checkout': str(root), 'dungeon_data': str(tmp_path / 'dungeon-data')})
    mine = make_world(tmp_path / 'mine')
    (mine / 'world.json').write_text(json.dumps({'id': 'hollowmere', 'name': 'Hollowmere'}), encoding='utf-8')
    done = TestClient(create_app()).post('/api/worlds/install', json={'folder': str(mine)}).json()
    assert Path(done['path']) == tmp_path / 'dungeon-data' / 'packages' / 'hollowmere.sqlite'
    assert packages.read(Path(done['path']))['world']['id'] == 'hollowmere'
    with pytest.raises(DomainError, match='built-in world'):
        package_files.install_world(worlds.folder(make_world(tmp_path / 'copy')))  # its id is testland
    with pytest.raises(DomainError, match='already in your Dungeon checkout'):
        package_files.install_world(worlds.builtin(root, 'testland'))


def test_dungeons_data_folder_is_found_like_dungeon_finds_it(tmp_path, monkeypatch):
    root = make_checkout(tmp_path / 'dungeon')
    settings.save({'dungeon_checkout': str(root)})
    monkeypatch.setattr(sys, 'platform', 'linux')
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg'))
    assert package_files.dungeon_data() == tmp_path / 'xdg' / 'prospero-dungeon'
    (root / 'Data').mkdir()
    assert package_files.dungeon_data() == root / 'Data'
