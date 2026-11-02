"""Reading, saving and undoing a town's engine files."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout, make_world
from worldsmith import towns, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


@pytest.fixture
def checkout(tmp_path):
    return make_checkout(tmp_path / 'dungeon')


def test_a_town_reads_with_its_parts_and_no_problems(checkout):
    town = towns.read(worlds.builtin(checkout, 'testland'), 'kingswood')
    assert town['parts']['cities']['name'] == 'Kingswood' and town['parts']['items'] == {'shops': []}
    assert town['parts']['adventures'] is None
    assert town['problems'] == {'cities': [], 'items': []}


def test_saving_writes_where_dungeon_keeps_it_with_the_same_indent(checkout):
    opened = worlds.builtin(checkout, 'testland')
    path = checkout / worlds.DATA / 'cities' / 'kingswood.json'
    path.write_text(json.dumps(json.loads(path.read_text(encoding='utf-8')), indent=1) + '\n', encoding='utf-8')
    city = towns.read(opened, 'kingswood')['parts']['cities']
    towns.save(opened, 'kingswood', 'cities', city | {'summary': 'A quieter town now.'})
    text = path.read_text(encoding='utf-8')
    assert json.loads(text)['summary'] == 'A quieter town now.'
    assert text.splitlines()[1].startswith(' "') and not text.splitlines()[1].startswith('  ')


def test_a_city_dungeon_would_refuse_is_not_saved(checkout):
    opened = worlds.builtin(checkout, 'testland')
    city = towns.read(opened, 'kingswood')['parts']['cities']
    stray = dict(city['places'][0], id='lost-place', neighborhood='nowhere')
    with pytest.raises(DomainError, match='nowhere'):
        towns.save(opened, 'kingswood', 'cities', city | {'places': city['places'] + [stray]})
    assert towns.read(opened, 'kingswood')['undo'] == []


def test_a_city_keeps_its_id(checkout):
    opened = worlds.builtin(checkout, 'testland')
    city = towns.read(opened, 'kingswood')['parts']['cities']
    with pytest.raises(DomainError, match='town id'):
        towns.save(opened, 'kingswood', 'cities', city | {'id': 'oakhollow'})


def test_undo_puts_back_the_last_save_and_removes_a_new_file(checkout):
    opened = worlds.builtin(checkout, 'testland')
    city = towns.read(opened, 'kingswood')['parts']['cities']
    towns.save(opened, 'kingswood', 'cities', city | {'summary': 'Changed.'})
    towns.save(opened, 'kingswood', 'adventures', {'quests': [], 'dangers': []})
    assert [item['kind'] for item in towns.read(opened, 'kingswood')['undo']] == ['adventures', 'cities']
    assert towns.undo(opened, 'kingswood')['parts']['adventures'] is None
    assert towns.undo(opened, 'kingswood')['parts']['cities']['summary'] == city['summary']
    with pytest.raises(DomainError):
        towns.undo(opened, 'kingswood')


def test_a_world_folder_keeps_town_files_in_its_engine_folder(tmp_path):
    opened = worlds.folder(make_world(tmp_path / 'mine'))
    towns.save(opened, 'kingswood', 'finds', {'containers': {}})
    assert (tmp_path / 'mine' / 'engine' / 'finds' / 'kingswood.json').is_file()


def test_a_bad_kind_or_town_id_is_refused(checkout):
    opened = worlds.builtin(checkout, 'testland')
    with pytest.raises(DomainError):
        towns.path_of(opened, 'kingswood', 'secrets')
    with pytest.raises(DomainError):
        towns.path_of(opened, '../kingswood', 'cities')


def test_the_api_reads_saves_and_undoes(checkout):
    client = TestClient(create_app())
    client.put('/api/settings', json={'dungeon_checkout': str(checkout)})
    ref = {'builtin': 'testland', 'town': 'kingswood'}
    town = client.post('/api/towns/read', json=ref).json()
    city = town['parts']['cities'] | {'name': 'Kingswood Town'}
    saved = client.put('/api/towns/part', json=ref | {'kind': 'cities', 'data': city})
    assert saved.status_code == 200 and saved.json()['parts']['cities']['name'] == 'Kingswood Town'
    refused = client.put('/api/towns/part', json=ref | {'kind': 'cities', 'data': city | {'places': []}})
    assert refused.status_code == 422 and 'places' in refused.json()['error']
    assert client.post('/api/towns/undo', json=ref).json()['parts']['cities']['name'] == 'Kingswood'
    assert 'Place' in client.get('/api/schema/city').json()['$defs']


def test_a_save_keeps_floats_the_browser_turned_into_whole_numbers(checkout):
    opened = worlds.builtin(checkout, 'testland')
    path = checkout / worlds.DATA / 'cities' / 'kingswood.json'
    city = json.loads(path.read_text(encoding='utf-8'))
    city['lon'] = -2.0
    path.write_text(json.dumps(city, indent=1) + '\n', encoding='utf-8')
    towns.save(opened, 'kingswood', 'cities', city | {'lon': -2, 'summary': 'Edited.'})
    assert '"lon": -2.0' in path.read_text(encoding='utf-8')
