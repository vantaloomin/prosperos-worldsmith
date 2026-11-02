"""The world map painter: a world's hex map (Dungeon's hexes file) read, generated around the author's paint
(terrain.py) and saved back, and suggested town sites turned into stops on the travel map.

- **Where the map lives.** The travel file names its hexes file (`hexes`, else the world's id):
  world/data/hexes/<key>.json in a Dungeon checkout for a built-in world, engine/hexes/<key>.json in a world folder.
  A world with no hexes file starts blank; saving writes one and points the travel file at it.
- **What is saved.** The generated `terrain` rows (painted hexes as painted), `rivers` and `lakes` (Dungeon's hex
  crawl reads both: rivers cost time to cross off the road, and a road over one is a bridge or a ford), the author's
  `paint` rows (a space for a hex left to the generator) and the `painter` settings, so the same map comes back.
  The file's other keys (roads, regions, places, names, generate) are kept; regions and places are filled in for hexes
  and stops that have none, from the nearest stop's region and each stop's spot on the travel map.
- **Saves go through the history**, so Undo takes a map save back, with a town added from it.
"""
import json
import math
import re
import uuid

from worldsmith import terrain, towns, worlds
from worldsmith.dungeon_format.errors import require

KEY = 'world-hex-map'  # the history key a hex map save is undone by
SIZES = {'small': (48, 36), 'medium': (80, 60), 'large': (120, 90)}
MOST = 200  # columns or rows
WINDS = tuple(terrain.WINDS)
DENSITIES = tuple(terrain.RIVERS)
REGION_CODES = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
LAYOUT = ('Offset rows, flat-topped, odd columns shifted down half a hex; column c and row r are the axial hex q = c, '
          'r = r - (c - (c & 1)) / 2.')


def world_id_of(opened: worlds.Opened, found: dict) -> str:
    return found['world'].get('id') or opened.folder.name


def root_of(opened: worlds.Opened):
    return opened.data if opened.data else opened.folder / 'engine'


def travel_of(opened: worlds.Opened) -> tuple[dict, object, dict]:
    """(found, travel path, travel map)."""
    from worldsmith.wizard import travel_file
    found, _ = worlds.contents(opened)
    path = travel_file(opened, world_id_of(opened, found))
    require(path.is_file(), 'This world has no travel map yet: make its stops first (New world, or Travel map).', 404)
    return found, path, json.loads(path.read_text(encoding='utf-8'))


def hexes_path(opened: worlds.Opened, found: dict, travel: dict):
    key = travel.get('hexes') or travel.get('world') or world_id_of(opened, found)
    return root_of(opened) / 'hexes' / f'{key}.json', key


def blank(columns: int, rows: int) -> list[str]:
    return [' ' * columns for _ in range(rows)]


def size_of(columns, rows) -> tuple[int, int]:
    columns, rows = int(columns), int(rows)
    require(8 <= columns <= MOST and 8 <= rows <= MOST, f'A map is 8 to {MOST} hexes each way.', 422)
    return columns, rows


def stops(travel: dict, data: dict, columns: int, rows: int) -> list[dict]:
    """The travel map's stops, each on its hex: the hexes file's own place, else its spot on the travel map."""
    places = data.get('places') or {}
    found = []
    for node in travel.get('nodes', []):
        if node['id'] in places:
            q, r = places[node['id']]
            column, row = terrain.offset(q, r)
        elif 'x' in (node.get('map') or {}):
            column = min(columns - 1, max(0, round(node['map']['x'] * (columns - 1))))
            row = min(rows - 1, max(0, round(node['map']['y'] * (rows - 1))))
            q, r = terrain.axial(column, row)
        else:
            continue
        found.append({'id': node['id'], 'label': node.get('name') or node['id'], 'region': node.get('region'),
                      'q': q, 'r': r, 'column': column, 'row': row, 'placed': node['id'] in places})
    return found


def read(opened: worlds.Opened, size: str = 'medium') -> dict:
    """The map to paint: the saved paint (or the authored terrain, all of it counted as painted), or a blank map."""
    found, _, travel = travel_of(opened)
    path, key = hexes_path(opened, found, travel)
    data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else travel.get('hex_map') or {}
    terrain_rows = data.get('terrain') or []
    columns, rows = (len(terrain_rows[0]), len(terrain_rows)) if terrain_rows else SIZES.get(size, SIZES['medium'])
    paint = data.get('paint') or terrain_rows or blank(columns, rows)
    painter = data.get('painter') or {}
    return {
        'key': key, 'exists': path.is_file() and bool(terrain_rows), 'columns': columns, 'rows': rows,
        'miles': data.get('miles', 6), 'legend': terrain.LEGEND, 'paint': paint, 'terrain': terrain_rows,
        'rivers': data.get('rivers') or [], 'lakes': data.get('lakes') or [],
        'roads': [{'name': road.get('name', ''), 'cells': road.get('cells', [])} for road in data.get('roads') or []],
        'stops': stops(travel, data, columns, rows),
        'settings': {'seed': painter.get('seed') or key, 'wind': painter.get('wind', 'west'),
                     'rivers': painter.get('rivers', 'some')},
        'can_add_towns': road_city(opened, world_id_of(opened, found)) is not None,
        'undo': towns.undoable(opened, KEY),
    }


def checked_paint(paint: list, columns: int, rows: int) -> list[str]:
    require(isinstance(paint, list) and len(paint) == rows, f'The paint needs {rows} rows.', 422)
    lines = []
    for line in paint:
        require(isinstance(line, str) and len(line) == columns, f'Each paint row is {columns} hexes.', 422)
        lines.append(''.join(code if code in terrain.LEGEND else ' ' for code in line))
    return lines


def settings_of(body: dict) -> dict:
    wind, rivers = body.get('wind', 'west'), body.get('rivers', 'some')
    require(wind in WINDS, f'The wind blows from {", ".join(WINDS)}.', 422)
    require(rivers in DENSITIES, f'Rivers are {", ".join(DENSITIES)}.', 422)
    return {'seed': str(body.get('seed') or 'worldsmith')[:60], 'wind': wind, 'rivers': rivers}


def generate(opened: worlds.Opened, body: dict) -> dict:
    """The map worked out from the paint, not saved: terrain, rivers, lakes and suggested town sites."""
    found, _, travel = travel_of(opened)
    path, _ = hexes_path(opened, found, travel)
    data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    columns, rows = size_of(body.get('columns', 80), body.get('rows', 60))
    paint = checked_paint(body.get('paint') or blank(columns, rows), columns, rows)
    settings = settings_of(body)
    on_map = stops(travel, data, columns, rows)
    made = terrain.generate(columns, rows, paint, places=[(stop['q'], stop['r']) for stop in on_map], **settings)
    made['rivers'] = named(made['rivers'], data.get('rivers') or [])
    made.pop('height', None)
    return {**made, 'paint': paint, 'settings': settings, 'stops': on_map}


def named(rivers: list[dict], old: list[dict]) -> list[dict]:
    """Keep the names the author gave rivers: a new river takes the name of the old one it shares most hexes with."""
    if not old:
        return rivers
    old_cells = [({tuple(cell) for cell in river.get('cells', [])}, river) for river in old if river.get('name')]
    for river in rivers:
        cells = {tuple(cell) for cell in river['cells']}
        best = max(old_cells, key=lambda item: len(item[0] & cells), default=None)
        if best and len(best[0] & cells) * 2 >= min(len(cells), len(best[0])):
            river['name'] = best[1]['name']
    return rivers


def regions_for(made: dict, data: dict, on_map: list[dict]) -> tuple[list[str], dict]:
    """The file's region rows, kept when they fit the map; else each hex in the region of the nearest stop."""
    rows, columns = made['rows'], made['columns']
    old_rows, old_legend = data.get('regions') or [], data.get('region_legend') or {}
    if len(old_rows) == rows and all(len(line) == columns for line in old_rows):
        return old_rows, old_legend
    regions = sorted({stop['region'] for stop in on_map if stop.get('region')})
    legend = {REGION_CODES[index]: region for index, region in enumerate(regions[:len(REGION_CODES)])}
    code_of = {region: code for code, region in legend.items()}
    sources = [(stop['column'], stop['row'], code_of[stop['region']]) for stop in on_map if stop.get('region') in code_of]
    if not sources:
        return [' ' * columns for _ in range(rows)], {}
    lines = []
    for row in range(rows):
        line = []
        for column in range(columns):
            nearest = min(sources, key=lambda source: terrain.hex_distance((column, row), source[:2]))
            line.append(nearest[2])
        lines.append(''.join(line))
    return lines, legend


def save(opened: worlds.Opened, body: dict) -> dict:
    found, travel_path, travel = travel_of(opened)
    path, key = hexes_path(opened, found, travel)
    before = path.read_text(encoding='utf-8') if path.is_file() else None
    data = json.loads(before) if before else dict(travel.get('hex_map') or {})
    made = generate(opened, body)
    on_map = made['stops']
    regions, region_legend = regions_for(made, data, on_map)
    places = dict(data.get('places') or {})
    for stop in on_map:
        places.setdefault(stop['id'], [stop['q'], stop['r']])
    name = found['world'].get('name') or key
    data = {
        'about': data.get('about') or f"{name}'s hexes, painted in Prospero's Worldsmith: the land, its rivers and lakes "
                                      'worked out from the paint (Dungeon requirements "### Hex crawl").',
        'miles': data.get('miles', 6), 'layout': LAYOUT, **data,
        'legend': terrain.LEGEND, 'terrain': made['terrain'], 'region_legend': region_legend, 'regions': regions,
        'places': places, 'rivers': made['rivers'], 'lakes': made['lakes'], 'paint': made['paint'],
        'painter': made['settings'],
    }
    batch = uuid.uuid4().hex
    towns.write_tracked(path, towns.dumped(data, towns.indent_of(before) if before else 1, before), before, KEY, batch)
    if travel.get('hexes') != key:
        travel_before = travel_path.read_text(encoding='utf-8')
        travel['hexes'] = key
        towns.write_tracked(travel_path, towns.dumped(travel, towns.indent_of(travel_before), travel_before),
                            travel_before, KEY, batch)
    return read(opened)


def undo(opened: worlds.Opened) -> dict:
    towns.undo(opened, KEY)
    return read(opened)


# A town from a suggested site -------------------------------------------------------------------------------------

def road_city(opened: worlds.Opened, world_id: str) -> str | None:
    """The world's Road city, which holds stops not yet built out as towns, if it has one."""
    key = f'{world_id}-road'
    return key if towns.path_of(opened, key, 'cities').is_file() else None


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-')


def add_town(opened: worlds.Opened, body: dict) -> dict:
    """A suggested site made a town of the world: a place on the Road city and a stop on the travel map at that hex,
    and a settlement waiting to be built out with the town wizard (Towns to build), pitched by why the site is good."""
    from worldsmith.wizard import travel_file
    found, travel_path, travel = travel_of(opened)
    world_id = world_id_of(opened, found)
    road_key = road_city(opened, world_id)
    require(road_key is not None, 'This world has no Road city to hold new stops; add the town with New town instead.', 409)
    name = ' '.join(str(body.get('name') or '').split())
    require(2 <= len(name) <= 60, 'Give the town a name.', 422)
    town_id = slug(name)
    nodes = travel.get('nodes', [])
    require(town_id and town_id not in {node['id'] for node in nodes}, f'There is already a stop called {name}.', 409)
    path, key = hexes_path(opened, found, travel)
    require(path.is_file(), 'Save the map first, so the town has a hex to stand on.', 409)
    before = path.read_text(encoding='utf-8')
    data = json.loads(before)
    columns, rows = len(data['terrain'][0]), len(data['terrain'])
    q, r = int(body['q']), int(body['r'])
    column, row = terrain.offset(q, r)
    require(0 <= column < columns and 0 <= row < rows, 'That hex is not on the map.', 422)
    require(data['terrain'][row][column] != '~', 'A town needs dry land.', 422)
    on_map = stops(travel, data, columns, rows)
    nearest = min(on_map, key=lambda stop: terrain.hex_distance((column, row), (stop['column'], stop['row'])), default={})
    region = nearest.get('region') or 'wilds'
    summary = ' '.join(str(body.get('summary') or '').split()) or 'A town to build.'
    batch = uuid.uuid4().hex

    city_path = towns.path_of(opened, road_key, 'cities')
    city_before = city_path.read_text(encoding='utf-8')
    city = json.loads(city_before)
    hood = next((hood['id'] for hood in city.get('neighborhoods', []) if hood['id'] == region),
                city['neighborhoods'][0]['id'])
    template = next((place for place in city.get('places', []) if place.get('kind') == 'landmark'), None) or {}
    city['places'].append({**{field: value for field, value in template.items() if field not in ('id', 'name', 'summary')},
                           'id': town_id, 'name': name, 'kind': 'landmark', 'neighborhood': hood, 'summary': summary})
    towns.write_tracked(city_path, towns.dumped(city, towns.indent_of(city_before), city_before), city_before, KEY, batch)

    travel_before = travel_path.read_text(encoding='utf-8')
    nodes.append({'id': town_id, 'name': name, 'region': region, 'city': road_key, 'place': town_id, 'safe': True,
                  'map': {'x': round(column / max(1, columns - 1), 3), 'y': round(row / max(1, rows - 1), 3)}})
    if nearest:  # A road to the nearest stop, about an hour a hex.
        apart = math.ceil(terrain.hex_distance((column, row), (nearest['column'], nearest['row'])) * data.get('miles', 6) / 3)
        travel.setdefault('routes', []).append({'from': nearest['id'], 'to': town_id, 'hours': max(1, apart),
                                                'terrain': 'the road', 'danger': 'low'})
    towns.write_tracked(travel_file(opened, world_id), towns.dumped(travel, towns.indent_of(travel_before), travel_before),
                        travel_before, KEY, batch)

    data.setdefault('places', {})[town_id] = [q, r]
    towns.write_tracked(path, towns.dumped(data, towns.indent_of(before), before), before, KEY, batch)

    settlements_path = opened.folder / 'settlements.json'
    if settlements_path.is_file():
        settled_before = settlements_path.read_text(encoding='utf-8')
        settled = json.loads(settled_before)
        settled['settlements'].append({'id': town_id, 'name': name, 'region': region, 'kind': 'town', 'summary': summary})
        towns.write_tracked(settlements_path, towns.dumped(settled, towns.indent_of(settled_before), settled_before),
                            settled_before, KEY, batch)
    return read(opened)
