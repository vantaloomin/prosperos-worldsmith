"""Opening built-in worlds from a Dungeon checkout and world folders from anywhere."""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout, make_world
from worldsmith import worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


def test_a_checkout_lists_its_built_in_worlds(tmp_path):
    listed = worlds.builtin_worlds(make_checkout(tmp_path / 'dungeon'))
    assert [world['id'] for world in listed] == ['testland']


def test_a_folder_that_is_not_a_checkout_is_refused(tmp_path):
    with pytest.raises(DomainError, match='checkout'):
        worlds.builtin_worlds(tmp_path)


def test_a_built_in_world_gathers_its_towns_from_the_data_folder(tmp_path):
    overview = worlds.overview(worlds.builtin(make_checkout(tmp_path / 'dungeon'), 'testland'))
    assert overview['kind'] == 'builtin' and overview['problems'] == []
    towns = {town['id']: town for town in overview['towns']}
    assert set(towns) == {'kingswood', 'testland-road'}  # elsewhere is not on Testland's travel map
    assert towns['kingswood']['parts'] == ['cities', 'items'] and not towns['kingswood']['road']
    assert towns['testland-road']['road']
    assert overview['sections']['cast'] == {'entries': 1, 'hidden': 1}
    assert overview['engine'] == {'arcs': 1, 'cities': 2, 'items': 1, 'travel': 1}


def test_engine_gathering_matches_dungeons_own(tmp_path, monkeypatch):
    data = make_checkout(tmp_path / 'dungeon') / worlds.DATA
    monkeypatch.setattr(packages, 'DATA', data)
    assert worlds.engine_for(data, 'testland') == packages.engine_for('testland')


def test_a_world_with_problems_still_opens_and_lists_them(tmp_path):
    folder = make_world(tmp_path / 'testland')
    (folder / 'cast.json').write_text(json.dumps({'cast': [{'id': 'Bad Id', 'faction': 'nobody'}]}), encoding='utf-8')
    problems = worlds.overview(worlds.folder(folder))['problems']
    assert any('kebab-case' in problem for problem in problems)


def test_an_unknown_world_id_is_refused(tmp_path):
    with pytest.raises(DomainError):
        worlds.builtin(make_checkout(tmp_path / 'dungeon'), '../testland')


def test_the_api_sets_the_checkout_lists_and_opens_worlds(tmp_path):
    client = TestClient(create_app())
    assert client.put('/api/settings', json={'dungeon_checkout': str(tmp_path)}).status_code == 404
    checkout = make_checkout(tmp_path / 'dungeon')
    assert client.put('/api/settings', json={'dungeon_checkout': str(checkout)}).json()['dungeon_checkout']
    assert [world['id'] for world in client.get('/api/worlds').json()['builtin']] == ['testland']
    opened = client.post('/api/worlds/open', json={'builtin': 'testland'}).json()
    assert opened['world']['name'] == 'Testland' and len(opened['towns']) == 2


def test_an_opened_folder_is_remembered(tmp_path):
    client = TestClient(create_app())
    folder = make_world(tmp_path / 'mine')
    assert client.post('/api/worlds/open', json={'folder': str(folder)}).json()['kind'] == 'folder'
    assert client.get('/api/worlds').json()['recent'] == [{'folder': str(folder), 'name': 'Testland'}]
    assert client.post('/api/worlds/open', json={}).status_code == 422


@pytest.mark.skipif(not os.environ.get('DUNGEON_CHECKOUT'), reason='set DUNGEON_CHECKOUT to a real Dungeon checkout')
def test_the_real_built_in_worlds_open_cleanly():
    checkout = Path(os.environ['DUNGEON_CHECKOUT'])
    for world in worlds.builtin_worlds(checkout):
        overview = worlds.overview(worlds.builtin(checkout, world['id']))
        assert overview['problems'] == [], world['id']
        assert overview['towns'], world['id']
