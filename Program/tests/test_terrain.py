"""The world map painter: land, rain, rivers, lakes and town sites worked out from paint (terrain.py), and the hex map
read, saved, undone and given new towns (hexmap.py)."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout, write_files
from worldsmith import hexmap, settings, terrain, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app

SEA_AND_RANGE = ['~~~~~' + ' ' * 15 + 'm' + ' ' * 19 for _ in range(30)]


def cells_of(rows: list[str]) -> dict:
    return {(column, row): code for row, line in enumerate(rows) for column, code in enumerate(line)}


def test_the_same_paint_and_seed_give_the_same_map_and_another_seed_another():
    one, two = terrain.generate(40, 30, seed='a'), terrain.generate(40, 30, seed='a')
    assert one == two
    assert terrain.generate(40, 30, seed='b')['terrain'] != one['terrain']


def test_a_map_with_nothing_painted_is_a_continent_ringed_by_sea():
    made = terrain.generate(60, 45, seed='continent')
    grid = cells_of(made['terrain'])
    assert all(code == '~' for (column, row), code in grid.items() if column in (0, 59) or row in (0, 44))
    land = sum(code != '~' for code in grid.values()) / len(grid)
    assert 0.3 < land < 0.6
    assert {'m', 'h', 'f', '.'} <= set(grid.values())


def test_painted_hexes_are_kept_as_painted():
    made = terrain.generate(40, 30, SEA_AND_RANGE, seed='p')
    for row, line in enumerate(made['terrain']):
        assert line[:5] == '~~~~~' and line[20] == 'm', row


def test_the_lee_of_a_range_is_drier_than_the_windward_side():
    def dry_share(wind: str, side: slice) -> float:
        made = terrain.generate(40, 30, SEA_AND_RANGE, seed='shadow', wind=wind)
        codes = ''.join(line[side] for line in made['terrain'][2:-2])
        land = [code for code in codes if code != '~']
        return sum(code in 'w.' for code in land) / len(land)
    # The wind off the western sea rains on the slopes before the range and leaves the land behind it dry.
    assert dry_share('west', slice(22, 38)) > dry_share('west', slice(10, 19)) + 0.2


def test_rivers_run_downhill_to_the_sea_or_a_lake_and_lakes_sit_in_basins():
    made = terrain.generate(80, 60, seed='rivers', rivers='many')
    assert len(made['rivers']) >= 5
    grid = cells_of(made['terrain'])
    height = {(column, row): value for row, line in enumerate(made['height']) for column, value in enumerate(line)}
    lakes = {tuple(cell) for cell in made['lakes']}
    courses = {tuple(cell) for river in made['rivers'] for cell in river['cells']}
    for river in made['rivers']:
        cells = [terrain.offset(*cell) for cell in river['cells']]
        for here, there in zip(cells, cells[1:]):
            assert terrain.hex_distance(here, there) == 1  # one hex at a time
        mouth = cells[-1]
        # A river ends where it meets the sea, a lake, another river, or runs off the map's edge.
        assert grid[mouth] == '~' or tuple(river['cells'][-1]) in lakes or tuple(river['cells'][-1]) in courses \
            or mouth[0] in (0, 79) or mouth[1] in (0, 59)
        assert river['flow'][-1] >= river['flow'][0]  # rivers grow as they go
        assert height[cells[0]] >= height[cells[-2]] - 0.05
    for q, r in lakes:
        assert grid[terrain.offset(q, r)] == '~'


def test_more_rivers_with_many_than_with_few():
    count = {density: sum(len(river['cells']) for river in terrain.generate(80, 60, seed='d', rivers=density)['rivers'])
             for density in terrain.RIVERS}
    assert count['many'] > count['some'] > count['few']


def test_town_sites_are_on_dry_land_apart_and_say_why():
    made = terrain.generate(80, 60, seed='towns', towns=8)
    grid = cells_of(made['terrain'])
    assert 4 <= len(made['towns']) <= 8
    for site in made['towns']:
        assert grid[(site['column'], site['row'])] not in '~m' and site['why'] and site['kind']
        assert (site['q'], site['r']) == terrain.axial(site['column'], site['row'])
    for index, site in enumerate(made['towns']):
        for other in made['towns'][index + 1:]:
            assert terrain.hex_distance((site['column'], site['row']), (other['column'], other['row'])) >= terrain.TOWN_SPACING
    assert sum(site['kind'] == 'port' for site in made['towns']) <= 4
    # Existing places push suggestions away.
    first = made['towns'][0]
    again = terrain.generate(80, 60, seed='towns', towns=8, places=[(first['q'], first['r'])])
    assert all(terrain.hex_distance((site['column'], site['row']), (first['column'], first['row'])) >= terrain.TOWN_SPACING
               for site in again['towns'])


# The world's hex map ------------------------------------------------------------------------------------------------

@pytest.fixture
def opened(tmp_path):
    root = make_checkout(tmp_path / 'dungeon')
    data = root / 'Program/dungeon/world/data'
    travel = {'world': 'testland', 'regions': {'the-vale': {'name': 'The Vale', 'danger': 'low'}},
              'nodes': [{'id': 'kingswood', 'city': 'kingswood', 'place': 'x', 'region': 'the-vale', 'safe': True,
                         'map': {'x': 0.5, 'y': 0.5}}],
              'routes': []}
    write_files(data, {'travel/testland.json': travel})
    settings.save({'dungeon_checkout': str(root)})
    return worlds.builtin(root, 'testland')


def painted_body(columns=40, rows=30) -> dict:
    paint = [' ' * columns for _ in range(rows)]
    paint = ['~~~~' + line[4:] for line in paint]
    return {'columns': columns, 'rows': rows, 'paint': paint, 'seed': 'test', 'wind': 'west', 'rivers': 'many'}


def test_a_world_with_no_hexes_file_starts_blank(opened):
    read = hexmap.read(opened, 'small')
    assert not read['exists'] and (read['columns'], read['rows']) == hexmap.SIZES['small']
    assert read['paint'][0].strip() == '' and read['terrain'] == []
    assert read['stops'][0]['id'] == 'kingswood' and not read['stops'][0]['placed']


def test_saving_writes_the_hexes_file_dungeon_reads_and_undo_takes_it_back(opened):
    path = opened.data / 'hexes/testland.json'
    saved = hexmap.save(opened, painted_body())
    data = json.loads(path.read_text())
    assert saved['exists'] and len(data['terrain']) == 30 and all(len(line) == 40 for line in data['terrain'])
    assert all(line.startswith('~~~~') for line in data['terrain'])
    assert len(data['regions']) == 30 and data['region_legend'] == {'a': 'the-vale'}
    assert data['legend']['~'] == 'water' and data['painter'] == {'seed': 'test', 'wind': 'west', 'rivers': 'many'}
    assert data['places']['kingswood'] == [saved['stops'][0]['q'], saved['stops'][0]['r']]
    assert data['rivers'] and all({'id', 'name', 'cells', 'flow'} <= set(river) for river in data['rivers'])
    travel = json.loads((opened.data / 'travel/testland.json').read_text())
    assert travel['hexes'] == 'testland'
    assert saved['paint'] == painted_body()['paint']  # the paint comes back for the next session
    hexmap.undo(opened)
    assert not path.exists() and 'hexes' not in json.loads((opened.data / 'travel/testland.json').read_text())


def test_river_names_and_the_files_other_keys_survive_a_new_save(opened):
    hexmap.save(opened, painted_body())
    path = opened.data / 'hexes/testland.json'
    data = json.loads(path.read_text())
    data['rivers'][0]['name'] = 'the Wend'
    data['roads'] = [{'name': 'the old road', 'danger': 'low', 'cells': [[5, 5], [6, 5]]}]
    path.write_text(json.dumps(data))
    body = painted_body()
    body['paint'][10] = body['paint'][10][:30] + 'f' + body['paint'][10][31:]
    hexmap.save(opened, body)
    again = json.loads(path.read_text())
    assert 'the Wend' in [river['name'] for river in again['rivers']]
    assert again['roads'] == data['roads'] and again['terrain'][10][30] == 'f'


def test_generating_does_not_save_and_refuses_bad_paint(opened):
    made = hexmap.generate(opened, painted_body())
    assert made['terrain'] and 'towns' in made and not (opened.data / 'hexes/testland.json').exists()
    with pytest.raises(DomainError):
        hexmap.generate(opened, painted_body() | {'paint': ['~~']})
    with pytest.raises(DomainError):
        hexmap.generate(opened, painted_body() | {'wind': 'up'})


def test_a_suggested_site_becomes_a_stop_on_the_road_city_and_undoes_together(opened):
    saved = hexmap.save(opened, painted_body())
    assert saved['can_add_towns']
    made = hexmap.generate(opened, painted_body())
    site = made['towns'][0]
    with pytest.raises(DomainError):
        hexmap.add_town(opened, {'q': 0, 'r': 0, 'name': 'Wet Feet'})  # in the sea
    after = hexmap.add_town(opened, {'q': site['q'], 'r': site['r'], 'name': 'Ashford', 'summary': 'Where two rivers meet.'})
    assert 'ashford' in {stop['id'] for stop in after['stops']}
    travel = json.loads((opened.data / 'travel/testland.json').read_text())
    node = next(node for node in travel['nodes'] if node['id'] == 'ashford')
    assert node['city'] == 'testland-road' and node['region'] == 'the-vale'
    assert travel['routes'][-1]['to'] == 'ashford'
    road = json.loads((opened.data / 'cities/testland-road.json').read_text())
    assert road['places'][-1]['id'] == 'ashford'
    hexes = json.loads((opened.data / 'hexes/testland.json').read_text())
    assert hexes['places']['ashford'] == [site['q'], site['r']]
    settlements = json.loads((opened.folder / 'settlements.json').read_text())
    assert settlements['settlements'][-1] == {'id': 'ashford', 'name': 'Ashford', 'region': 'the-vale', 'kind': 'town',
                                              'summary': 'Where two rivers meet.'}
    with pytest.raises(DomainError):
        hexmap.add_town(opened, {'q': site['q'], 'r': site['r'], 'name': 'Ashford'})
    hexmap.undo(opened)
    assert 'ashford' not in json.loads((opened.data / 'hexes/testland.json').read_text())['places']
    assert 'ashford' not in (opened.data / 'travel/testland.json').read_text()
    assert 'ashford' not in (opened.folder / 'settlements.json').read_text()


def test_the_api_paints_and_saves(opened):
    client = TestClient(create_app())
    body = {'builtin': 'testland', **painted_body()}
    assert client.post('/api/hexes/read', json={'builtin': 'testland'}).json()['exists'] is False
    assert client.post('/api/hexes/generate', json=body).json()['terrain']
    assert client.put('/api/hexes/save', json=body).json()['exists'] is True
    assert client.post('/api/hexes/undo', json={'builtin': 'testland'}).json()['exists'] is False


def test_a_stop_on_water_is_moved_to_the_nearest_land_and_saved_there(opened):
    # Kingswood's travel spot is mid-map; paint everything but a western strip as sea.
    body = painted_body() | {'paint': ['.' * 10 + '~' * 30 for _ in range(30)]}
    made = hexmap.generate(opened, body)
    grid = cells_of(made['terrain'])
    stop = made['stops'][0]
    assert stop['moved'] and grid[(stop['column'], stop['row'])] != '~'
    assert stop['column'] <= 10 and (stop['q'], stop['r']) == terrain.axial(stop['column'], stop['row'])
    saved = hexmap.save(opened, body)
    data = json.loads((opened.data / 'hexes/testland.json').read_text())
    assert data['places']['kingswood'] == [stop['q'], stop['r']] and not saved['stops'][0].get('moved')
    # A town saved on land that is later painted over with sea moves off it too, on read and on the next save.
    sunk = painted_body() | {'paint': ['~' * 40 for _ in range(15)] + ['.' * 40 for _ in range(15)]}
    data['terrain'] = sunk['paint']
    (opened.data / 'hexes/testland.json').write_text(json.dumps(data))
    shown = hexmap.read(opened)['stops'][0]
    assert shown['moved'] and shown['row'] >= 15
    hexmap.save(opened, sunk)
    q, r = json.loads((opened.data / 'hexes/testland.json').read_text())['places']['kingswood']
    assert terrain.offset(q, r)[1] >= 15


def test_a_stop_on_land_stays_put(opened):
    body = painted_body() | {'paint': ['.' * 40 for _ in range(30)]}
    stop = hexmap.generate(opened, body)['stops'][0]
    assert 'moved' not in stop and (stop['column'], stop['row']) == (20, 14)
