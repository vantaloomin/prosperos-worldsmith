"""Maps you can draw: Mermaid both ways, the travel map and a town's neighborhoods saved back into Dungeon's files."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout, write_files
from worldsmith import maps, mermaid, settings, towns, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


@pytest.fixture
def opened(tmp_path):
    root = make_checkout(tmp_path / 'dungeon')
    data = root / 'Program/dungeon/world/data'
    road = json.loads((data / 'cities/testland-road.json').read_text())
    travel = {'about': 'Testland roads.', 'regions': {'the-vale': {'name': 'The Vale', 'danger': 'low'}},
              'nodes': [{'id': 'kingswood', 'city': 'kingswood', 'place': road['places'][0]['id'], 'region': 'the-vale',
                         'safe': True, 'map': {'x': 0.3, 'y': 0.6}},
                        {'id': 'mile-post', 'city': 'testland-road', 'place': road['places'][1]['id'], 'region': 'the-vale'}],
              'routes': [{'from': 'kingswood', 'to': 'mile-post', 'hours': 4, 'terrain': 'the old road', 'danger': 'low'}]}
    write_files(data, {'travel/testland.json': travel})
    settings.save({'dungeon_checkout': str(root)})
    return worlds.builtin(root, 'testland')


def travel_file(opened) -> dict:
    return json.loads((opened.data / 'travel/testland.json').read_text())


GRAPH = {'nodes': [{'id': 'a', 'label': 'Ash "Ford"', 'group': 'vale', 'kind': 'stop', 'x': 10, 'y': 20},
                   {'id': 'b', 'label': 'Brill', 'group': None, 'kind': 'place'}],
         'groups': [{'id': 'vale', 'label': 'The Vale'}], 'links': [{'from': 'a', 'to': 'b', 'label': '8h · the road · low'}]}


def test_mermaid_text_round_trips_and_keeps_positions():
    text = mermaid.text(GRAPH)
    assert 'subgraph vale["The Vale"]' in text and 'a("Ash #quot;Ford#quot;")' in text and 'b(["Brill"])' in text
    assert 'a ---|"8h · the road · low"| b' in text
    assert mermaid.parse(text, GRAPH) == GRAPH


def test_mermaid_reads_the_common_ways_of_writing_a_flowchart():
    graph = mermaid.parse('graph TD\n  a[A plain] --> b;\n  a -- "a label" --- c(["C"])\n'
                          '  subgraph s [Bare]\n    d\n  end\n  %% a comment\n  classDef x fill:#fff\n')
    assert [node['label'] for node in graph['nodes']] == ['A plain', 'b', 'C', 'd']
    assert graph['links'][1] == {'from': 'a', 'to': 'c', 'label': 'a label'}
    assert graph['nodes'][3]['group'] == 's' and graph['groups'] == [{'id': 's', 'label': 'Bare'}]


def test_mermaid_says_which_lines_it_cannot_read():
    with pytest.raises(DomainError) as refused:
        mermaid.parse('flowchart LR\n  ?? what is this\n  subgraph x\n  x --- y')
    assert 'line 2' in refused.value.message and 'never closed' in refused.value.message
    assert 'both a node and a subgraph' in refused.value.message


def test_the_travel_map_reads_stops_roads_and_regions(opened):
    graph = maps.read(opened, 'travel')
    kingswood = next(node for node in graph['nodes'] if node['id'] == 'kingswood')
    assert kingswood['label'] == 'Kingswood' and (kingswood['x'], kingswood['y']) == (300, 600) and kingswood['placed']
    assert graph['links'] == [{'from': 'kingswood', 'to': 'mile-post', 'label': '4h · the old road · low'}]
    assert graph['groups'] == [{'id': 'the-vale', 'label': 'The Vale'}]
    road = towns.read(opened, 'testland-road')['parts']['cities']
    assert {item['id'] for item in graph['addable']} == {place['id'] for place in road['places']} - {road['places'][1]['id']}
    assert 'elsewhere' not in {item['id'] for item in graph['addable']}  # another world's town
    assert 'kingswood ---|"4h · the old road · low"| mile-post' in graph['mermaid']


def test_dragging_a_stop_and_drawing_a_road_save_to_the_travel_file_and_undo(opened):
    before = (opened.data / 'travel/testland.json').read_text()
    graph = maps.read(opened, 'travel')
    for node in graph['nodes']:
        if node['id'] == 'kingswood':
            node['x'], node['y'] = 400, 500
    stop = graph['addable'][0]
    graph['nodes'].append({'id': stop['id'], 'label': stop['label'], 'group': 'the-vale', 'x': 700, 'y': 700, 'placed': True})
    graph['links'][0]['label'] = '5h · the old road · medium'
    graph['links'].append({'from': stop['id'], 'to': 'kingswood', 'label': ''})
    done = maps.save(opened, 'travel', graph)
    saved = travel_file(opened)
    stops = {node['id']: node for node in saved['nodes']}
    assert stops['kingswood']['map'] == {'x': 0.4, 'y': 0.5} and 'map' not in stops['mile-post']
    assert stops[stop['id']]['city'] == 'testland-road' and stops[stop['id']]['place'] == stop['id']
    assert stops[stop['id']]['map'] == {'x': 0.7, 'y': 0.7} and stops[stop['id']]['safe'] is False
    assert saved['routes'][0] == {'from': 'kingswood', 'to': 'mile-post', 'hours': 5, 'terrain': 'the old road', 'danger': 'medium'}
    assert saved['routes'][1] == {'from': stop['id'], 'to': 'kingswood', 'hours': 8, 'terrain': 'the road', 'danger': 'low'}
    assert saved['about'] == 'Testland roads.' and done['undo']
    maps.undo(opened, 'travel')
    assert (opened.data / 'travel/testland.json').read_text() == before


def test_the_travel_map_refuses_stops_that_are_not_towns_and_bad_road_labels(opened):
    graph = maps.read(opened, 'travel')
    for stranger in ('atlantis', 'elsewhere'):
        with pytest.raises(DomainError, match='not a town of this world'):
            maps.save(opened, 'travel', {**graph, 'nodes': graph['nodes'] + [{'id': stranger, 'label': 'A', 'x': 1, 'y': 1}]})
    graph['links'][0]['label'] = 'a long way'
    with pytest.raises(DomainError, match='labelled like'):
        maps.save(opened, 'travel', graph)


def test_a_town_map_moves_places_and_neighborhoods_into_the_city_file(opened):
    graph = maps.read(opened, 'town', 'kingswood')
    city = towns.read(opened, 'kingswood')['parts']['cities']
    first, second = graph['groups'][0], graph['groups'][1]
    place = next(node for node in graph['nodes'] if node['kind'] == 'place' and node['group'] == first['id'])
    place['group'], place['label'] = second['id'], 'The Moved Inn'
    first['x'] += 50
    graph['groups'].append({'id': 'tanners-row', 'label': "Tanners' Row", 'x': 520, 'y': 480})
    graph['nodes'].append({'id': 'the-tan-pits', 'label': 'The Tan Pits', 'group': 'tanners-row', 'kind': 'place',
                           'type': city['places'][0]['kind']})
    maps.save(opened, 'town', graph, 'kingswood')
    saved = towns.read(opened, 'kingswood')['parts']['cities']
    moved = next(item for item in saved['places'] if item['id'] == place['id'])
    assert moved['neighborhood'] == second['id'] and moved['name'] == 'The Moved Inn'
    hood = next(item for item in saved['neighborhoods'] if item['id'] == first['id'])
    old = next(item for item in city['neighborhoods'] if item['id'] == first['id'])
    assert hood['lon'] > old['lon'] and hood['lat'] == pytest.approx(old['lat'], abs=1e-4)
    untouched = next(item for item in saved['neighborhoods'] if item['id'] == second['id'])
    assert untouched == next(item for item in city['neighborhoods'] if item['id'] == second['id'])
    new_hood = next(item for item in saved['neighborhoods'] if item['id'] == 'tanners-row')
    assert new_hood['summary'] == 'To describe.' and new_hood['transit'] == []
    assert next(item for item in saved['places'] if item['id'] == 'the-tan-pits')['neighborhood'] == 'tanners-row'


def test_a_town_map_refuses_roads_and_orphans(opened):
    graph = maps.read(opened, 'town', 'kingswood')
    with pytest.raises(DomainError, match='travel map'):
        maps.save(opened, 'town', {**graph, 'links': [{'from': 'a', 'to': 'b', 'label': ''}]}, 'kingswood')
    emptied = {**graph, 'groups': graph['groups'][1:]}
    with pytest.raises(DomainError, match='refuse'):
        maps.save(opened, 'town', emptied, 'kingswood')


def test_the_map_api_reads_turns_text_into_a_graph_and_saves(opened):
    client = TestClient(create_app())
    graph = client.post('/api/maps/read', json={'builtin': 'testland', 'map': 'travel'}).json()
    text = client.post('/api/maps/text', json={'graph': graph}).json()['mermaid']
    parsed = client.post('/api/maps/parse', json={'text': text.replace('4h · the old road', '6h · the old road'),
                                                  'graph': graph}).json()
    assert parsed['links'][0]['label'] == '6h · the old road · low'
    saved = client.put('/api/maps/save', json={'builtin': 'testland', 'map': 'travel', 'graph': parsed}).json()
    assert saved['links'][0]['label'] == '6h · the old road · low'
    assert client.post('/api/maps/parse', json={'text': 'nonsense here', 'graph': graph}).status_code == 422
    town = client.post('/api/maps/read', json={'builtin': 'testland', 'map': 'town', 'town': 'kingswood'}).json()
    assert town['groups'] and town['nodes'] and town['mermaid'].startswith('flowchart TB')
