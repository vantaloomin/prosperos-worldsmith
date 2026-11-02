"""Interior maps: rooms, levels and passages drawn and saved into Dungeon's engine/interiors files."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout, write_files
from worldsmith import maps, mermaid, settings, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app

CRYPT = {
    'schema_version': 1, 'id': 'old-crypt', 'name': 'The Old Crypt', 'world': 'testland', 'style': 'crypt',
    'summary': 'A crypt under the chapel.', 'at': {'city': 'kingswood', 'place': None}, 'entrance': 'stair-top',
    'levels': [{'id': 'upper', 'name': 'Upper vaults'}, {'id': 'lower', 'name': 'Lower vaults'}],
    'rooms': [
        {'id': 'stair-top', 'name': 'The stair top', 'level': 'upper', 'kind': 'stair', 'summary': 'Steps down.',
         'map': {'x': 0.2, 'y': 0.1}, 'source': 'mine'},
        {'id': 'ossuary', 'name': 'The ossuary', 'level': 'upper', 'kind': 'vault', 'summary': 'Bones.',
         'foes': [{'name': 'ghoul', 'vitality': 10, 'resolve': 10}], 'source': 'mine'},
        {'id': 'tomb', 'name': 'The tomb', 'level': 'lower', 'kind': 'tomb', 'summary': 'A tomb.', 'hidden': True,
         'source': 'mine'}],
    'passages': [
        {'between': ['stair-top', 'ossuary'], 'kind': 'stairs'},
        {'between': ['ossuary', 'tomb'], 'kind': 'secret', 'hidden': True, 'lock': {'key': 'iron-key'},
         'trap': {'action': 'open it softly', 'threat': 'Darts.'}}],
    'sources': {'mine': {'kind': 'curated', 'title': 'Test', 'license': 'CC0', 'retrieved': '2026-11-02'}},
}


@pytest.fixture
def opened(tmp_path):
    root = make_checkout(tmp_path / 'dungeon')
    data = root / 'Program/dungeon/world/data'
    city = json.loads((data / 'cities/kingswood.json').read_text())
    crypt = json.loads(json.dumps(CRYPT))
    crypt['at']['place'] = city['places'][0]['id']
    write_files(data, {'interiors/old-crypt.json': crypt})
    settings.save({'dungeon_checkout': str(root)})
    return worlds.builtin(root, 'testland')


def crypt_file(opened) -> dict:
    return json.loads((opened.data / 'interiors/old-crypt.json').read_text())


def test_an_interior_reads_as_rooms_levels_and_passages(opened):
    assert [item['id'] for item in maps.interiors(opened)] == ['old-crypt']
    graph = maps.read(opened, 'interior', 'old-crypt')
    rooms = {node['id']: node for node in graph['nodes']}
    assert (rooms['stair-top']['x'], rooms['stair-top']['y'], rooms['stair-top']['placed']) == (200, 100, True)
    assert rooms['stair-top']['entrance'] and rooms['tomb']['hidden'] and rooms['ossuary']['danger']
    assert not rooms['ossuary']['placed'] and rooms['ossuary']['group'] == 'upper'
    assert graph['links'][1]['label'] == 'secret · locked · hidden · trapped'
    assert 'subgraph lower["Lower vaults"]' in graph['mermaid']
    assert 'ossuary ---|"secret · locked · hidden · trapped"| tomb' in graph['mermaid']


def test_drawing_rooms_and_passages_saves_the_interior_file_and_undoes(opened):
    before = (opened.data / 'interiors/old-crypt.json').read_text()
    graph = maps.read(opened, 'interior', 'old-crypt')
    for node in graph['nodes']:
        if node['id'] == 'ossuary':
            node['x'], node['y'] = 500, 250
    graph['groups'].append({'id': 'deep', 'label': 'The deep'})
    graph['nodes'].append({'id': 'well', 'label': 'The well', 'group': 'deep', 'type': 'cistern', 'x': 600, 'y': 900})
    graph['links'][0]['label'] = 'stairs · locked'
    graph['links'].append({'from': 'tomb', 'to': 'well', 'label': 'shaft · one way'})
    maps.save(opened, 'interior', graph, 'old-crypt')
    saved = crypt_file(opened)
    rooms = {room['id']: room for room in saved['rooms']}
    assert rooms['ossuary']['map'] == {'x': 0.5, 'y': 0.25} and rooms['ossuary']['foes']  # details kept
    assert 'map' not in rooms['tomb']
    assert rooms['well'] == {'id': 'well', 'name': 'The well', 'level': 'deep', 'kind': 'cistern', 'summary': 'To describe.',
                             'map': {'x': 0.6, 'y': 0.9}, 'source': 'mine'}
    assert saved['passages'][0] == {'between': ['stair-top', 'ossuary'], 'kind': 'stairs', 'lock': {'difficulty': 'normal'}}
    assert saved['passages'][1]['lock'] == {'key': 'iron-key'} and saved['passages'][1]['trap']['action'] == 'open it softly'
    assert saved['passages'][2] == {'between': ['tomb', 'well'], 'kind': 'shaft', 'one_way': True}
    assert saved['levels'][2] == {'id': 'deep', 'name': 'The deep'}
    maps.undo(opened, 'interior', 'old-crypt')
    assert (opened.data / 'interiors/old-crypt.json').read_text() == before


def test_an_interior_dungeon_would_refuse_is_not_saved(opened):
    graph = maps.read(opened, 'interior', 'old-crypt')
    cut = {**graph, 'links': graph['links'][:1]}  # the tomb is cut off from the entrance
    with pytest.raises(DomainError, match='No passage reaches these rooms'):
        maps.save(opened, 'interior', cut, 'old-crypt')
    graph['links'][0]['label'] = 'door · trapped'
    with pytest.raises(DomainError, match='new trap'):
        maps.save(opened, 'interior', graph, 'old-crypt')
    graph['links'][0]['label'] = 'portal'
    with pytest.raises(DomainError, match='labelled like'):
        maps.save(opened, 'interior', graph, 'old-crypt')
    assert crypt_file(opened)['passages'][0] == CRYPT['passages'][0]


def test_mermaid_text_edits_an_interior(opened):
    graph = maps.read(opened, 'interior', 'old-crypt')
    text = graph['mermaid'].replace('stair-top ---|"stairs"| ossuary', 'stair-top ---|"ladder"| ossuary')
    parsed = mermaid.parse(text, graph)
    maps.save(opened, 'interior', parsed, 'old-crypt')
    assert crypt_file(opened)['passages'][0]['kind'] == 'ladder'


def test_a_new_interior_starts_with_its_way_in_and_shows_in_the_world(opened):
    client = TestClient(create_app())
    city = json.loads((opened.data / 'cities/kingswood.json').read_text())
    made = client.post('/api/interiors/new', json={'builtin': 'testland', 'name': 'The Miller\'s Cellar', 'style': 'building',
                                                    'city': 'kingswood', 'place': city['places'][1]['id']})
    assert made.json() == {'id': 'the-miller-s-cellar'}
    listed = client.post('/api/interiors/list', json={'builtin': 'testland'}).json()
    assert {item['id'] for item in listed['interiors']} == {'old-crypt', 'the-miller-s-cellar'}
    graph = client.post('/api/maps/read', json={'builtin': 'testland', 'map': 'interior', 'town': 'the-miller-s-cellar'}).json()
    assert [node['id'] for node in graph['nodes']] == ['way-in'] and graph['nodes'][0]['entrance']
    again = client.post('/api/interiors/new', json={'builtin': 'testland', 'name': 'The Miller\'s Cellar',
                                                     'city': 'kingswood', 'place': city['places'][1]['id']})
    assert again.status_code == 409
    nowhere = client.post('/api/interiors/new', json={'builtin': 'testland', 'name': 'Nowhere', 'city': 'kingswood', 'place': 'atlantis'})
    assert nowhere.status_code == 422
