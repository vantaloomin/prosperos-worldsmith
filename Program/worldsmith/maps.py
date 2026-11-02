"""Maps you can draw: a world's travel map and a town's neighborhoods, as graphs the visual editor and the Mermaid
text view both edit, saved back into Dungeon's own files.

- **Travel map** (the world's travel file): stops are nodes, roads are links labelled "8h · the forest road · low",
  regions are groups. A stop's position is its `map` x/y on the world map (0..1), so dragging it moves it there.
  A new stop must be a town of this world not yet on the map, or a place on the world's road (a roadside stop).
- **Interior** (engine/interiors/<id>.json, Dungeon's requirements "### Interiors"): rooms are nodes, levels are
  groups and passages are links labelled by their kind and flags, like "stairs · locked" or "secret · hidden ·
  trapped". A room's position is its `map` x/y (0..1); rooms never placed are laid out in rows by level.
- **Town** (the city file): neighborhoods are groups, placed by their lat/lon around the town's centre, so moving
  one moves it on Dungeon's street map too. Places and employers are nodes inside them; moving one into another
  neighborhood moves it there. A new place or neighborhood copies the details of one like it, to fill in after.

Positions are on a 1000 by 1000 canvas. Saves go through the same history as forms, so Undo takes a map save back.
"""
import copy
import datetime
import json
import math
import re

from pydantic import ValidationError

from worldsmith import mermaid, towns, worlds
from worldsmith.dungeon_format import packages, schema
from worldsmith.dungeon_format.errors import DomainError, require

SIZE = 1000
TRAVEL_KEY = 'world-travel-map'  # the history key a travel map save is undone by
DANGERS = ('none', 'low', 'medium', 'high')
ROUTE = re.compile(r'^\s*(?P<hours>\d+(?:\.\d+)?)\s*h(?:ours?)?\s*(?:·\s*(?P<terrain>.*?)\s*)?(?:·\s*(?P<danger>none|low|medium|high))?\s*$')
KM_PER_DEGREE = 111.0


# Travel map -------------------------------------------------------------------------------------------------------

def travel_path(opened: worlds.Opened, found: dict):
    from worldsmith.wizard import travel_file
    return travel_file(opened, found['world'].get('id') or opened.folder.name)


def cities_of(found: dict) -> dict[str, dict]:
    return {key: city for (kind, key), city in found['engine'].items() if kind == 'cities' and isinstance(city, dict)}


def road_label(route: dict) -> str:
    return f'{route.get("hours", 8):g}h · {route.get("terrain", "the road")} · {route.get("danger", "low")}'


def route_from(label: str, old: dict | None) -> dict:
    old = old or {'hours': 8, 'terrain': 'the road', 'danger': 'low'}
    found = ROUTE.match(label or '')
    if not found:
        require(not (label or '').strip(), f'A road is labelled like "8h · the forest road · low", not "{label}".', 422)
        return {key: old[key] for key in ('hours', 'terrain', 'danger') if key in old}
    hours = float(found['hours'])
    return {'hours': int(hours) if hours.is_integer() else hours, 'terrain': found['terrain'] or old.get('terrain', 'the road'),
            'danger': found['danger'] or old.get('danger', 'low')}


def stop_name(node: dict, cities: dict[str, dict]) -> str:
    city = cities.get(node.get('city'), {})
    if node.get('name'):
        return node['name']
    if city.get('town_map', {}).get('style') == 'none':  # a roadside stop is named after its place
        place = next((item for item in city.get('places', []) if item.get('id') == node.get('place')), {})
        return place.get('name') or node['id']
    return city.get('name') or node['id']


def addable_stops(travel: dict, cities: dict[str, dict]) -> list[dict]:
    """What can be put on the travel map: towns not on it yet, and road places that are not stops yet."""
    on_map = {node.get('city') for node in travel.get('nodes', [])}
    stops = {(node.get('city'), node.get('place')) for node in travel.get('nodes', [])}
    found = [{'id': key, 'label': city.get('name', key), 'kind': 'town'} for key, city in cities.items()
             if key not in on_map and (city.get('town_map') or {}).get('style') != 'none']
    for key, city in cities.items():
        if (city.get('town_map') or {}).get('style') == 'none' and key in on_map:
            found += [{'id': place['id'], 'label': place.get('name', place['id']), 'kind': 'roadside', 'road': key}
                      for place in city.get('places', []) if (key, place['id']) not in stops]
    return found


def travel_graph(opened: worlds.Opened) -> dict:
    found, _ = worlds.contents(opened)
    path = travel_path(opened, found)
    require(path.is_file(), 'This world has no travel map yet.', 404)
    travel = json.loads(path.read_text(encoding='utf-8'))
    cities = cities_of(found)
    nodes, count = [], max(1, len(travel.get('nodes', [])))
    for index, node in enumerate(travel.get('nodes', [])):
        at = node.get('map') or {}
        placed = 'x' in at and 'y' in at
        angle = 2 * math.pi * index / count
        nodes.append({'id': node['id'], 'label': stop_name(node, cities), 'group': node.get('region'), 'kind': 'stop',
                      'x': round(at['x'] * SIZE, 1) if placed else round(SIZE / 2 + 300 * math.cos(angle), 1),
                      'y': round(at['y'] * SIZE, 1) if placed else round(SIZE / 2 + 300 * math.sin(angle), 1),
                      'placed': placed, 'safe': node.get('safe', False)})
    used = {node.get('region') for node in travel.get('nodes', [])}
    regions = travel.get('regions') or {}
    groups = [{'id': key, 'label': (regions.get(key) or {}).get('name') or key} for key in regions if key in used]
    groups += [{'id': key, 'label': key} for key in sorted(used - set(regions) - {None})]
    links = [{'from': route['from'], 'to': route['to'], 'label': road_label(route)} for route in travel.get('routes', [])]
    return {'map': 'travel', 'nodes': nodes, 'groups': groups, 'links': links,
            'regions': [{'id': key, 'label': (value or {}).get('name') or key} for key, value in regions.items()],
            'addable': addable_stops(travel, cities)}


def moved(node: dict, old_at: dict | None) -> bool:
    if not old_at or 'x' not in old_at:
        return bool(node.get('placed'))
    return abs(node['x'] - old_at['x'] * SIZE) > 0.5 or abs(node['y'] - old_at['y'] * SIZE) > 0.5


def save_travel(opened: worlds.Opened, graph: dict) -> dict:
    found, _ = worlds.contents(opened)
    path = travel_path(opened, found)
    require(path.is_file(), 'This world has no travel map yet.', 404)
    before = path.read_text(encoding='utf-8')
    travel = json.loads(before)
    cities = cities_of(found)
    old = {node['id']: node for node in travel.get('nodes', [])}
    addable = {item['id']: item for item in addable_stops(travel, cities)}
    nodes = []
    for node in graph['nodes']:
        was = old.get(node['id'])
        if was is None:
            item = addable.get(node['id'])
            require(item is not None, f'{node["id"]} is not a town of this world or a place on its road, so it cannot '
                                      'be a stop. Make the town first (New town).', 422)
            city = cities[item.get('road', node['id'])]
            from worldsmith.wizard import first_place
            place = node['id'] if item['kind'] == 'roadside' else first_place(city)
            was = {'id': node['id'], 'name': item['label'], 'city': item.get('road', node['id']), 'place': place,
                   'safe': item['kind'] == 'town'}
        else:
            was = copy.deepcopy(was)
        if node.get('label') and node['label'] != stop_name(was, cities):
            was['name'] = node['label']
        if node.get('group'):
            was['region'] = node['group']
        else:
            was.pop('region', None)
        if moved(node, old.get(node['id'], {}).get('map')):
            was['map'] = {'x': round(min(1, max(0, node['x'] / SIZE)), 3), 'y': round(min(1, max(0, node['y'] / SIZE)), 3)}
        nodes.append(was)
    ids = {node['id'] for node in nodes}
    roads = {frozenset((route['from'], route['to'])): route for route in travel.get('routes', [])}
    routes, seen = [], set()
    for link in graph['links']:
        pair = frozenset((link['from'], link['to']))
        require(link['from'] != link['to'], 'A road needs two different stops.', 422)
        require(pair <= ids, f'A road joins {link["from"]} and {link["to"]}, which are not both stops.', 422)
        if pair in seen:
            continue
        seen.add(pair)
        old_route = roads.get(pair)
        route = {'from': old_route['from'], 'to': old_route['to']} if old_route else {'from': link['from'], 'to': link['to']}
        routes.append({**(old_route or {}), **route, **route_from(link.get('label', ''), old_route)})
    travel['nodes'], travel['routes'] = nodes, routes
    towns.write_tracked(path, towns.dumped(travel, towns.indent_of(before), before), before, TRAVEL_KEY)
    return travel_graph(opened)


# Town -------------------------------------------------------------------------------------------------------------

def frame_of(city: dict) -> dict:
    """How lat/lon map onto the canvas: the town's centre in the middle, its farthest neighborhood 380 from it."""
    lat0, lon0 = city.get('lat', 0), city.get('lon', 0)
    shrink = math.cos(math.radians(lat0)) or 1
    far = max([math.hypot((hood['lon'] - lon0) * shrink, hood['lat'] - lat0) * KM_PER_DEGREE
               for hood in city.get('neighborhoods', [])] + [0.5])
    return {'lat': lat0, 'lon': lon0, 'shrink': shrink, 'scale': 380 / far}


def to_canvas(frame: dict, lat: float, lon: float) -> tuple[float, float]:
    return (round(SIZE / 2 + (lon - frame['lon']) * frame['shrink'] * KM_PER_DEGREE * frame['scale'], 1),
            round(SIZE / 2 - (lat - frame['lat']) * KM_PER_DEGREE * frame['scale'], 1))


def from_canvas(frame: dict, x: float, y: float) -> tuple[float, float]:
    return (round(frame['lat'] - (y - SIZE / 2) / (KM_PER_DEGREE * frame['scale']), 5),
            round(frame['lon'] + (x - SIZE / 2) / (KM_PER_DEGREE * frame['scale'] * frame['shrink']), 5))


def town_graph(opened: worlds.Opened, town: str) -> dict:
    city = towns.read(opened, town)['parts']['cities']
    frame = frame_of(city)
    groups = []
    for hood in city.get('neighborhoods', []):
        x, y = to_canvas(frame, hood['lat'], hood['lon'])
        groups.append({'id': hood['id'], 'label': hood['name'], 'x': x, 'y': y})
    nodes = [{'id': place['id'], 'label': place['name'], 'group': place.get('neighborhood'), 'kind': 'place',
              'type': place.get('kind')} for place in city.get('places', [])]
    nodes += [{'id': employer['id'], 'label': employer['name'], 'group': employer.get('neighborhood'),
               'kind': 'employer', 'type': employer.get('sector')} for employer in city.get('employers', [])]
    found, _ = worlds.contents(opened)
    kinds = sorted({place.get('kind') for other in cities_of(found).values() for place in other.get('places', [])} - {None})
    return {'map': 'town', 'town': town, 'nodes': nodes, 'groups': groups, 'links': [], 'kinds': kinds}


def blank_from(template: dict, **changes) -> dict:
    record = copy.deepcopy(template)
    record.update(changes)
    return record


def save_town(opened: worlds.Opened, town: str, graph: dict) -> dict:
    city = copy.deepcopy(towns.read(opened, town)['parts']['cities'])
    require(not graph.get('links'), 'A town map has no roads between its places: draw roads on the travel map.', 422)
    frame = frame_of(city)
    hoods = {hood['id']: hood for hood in city.get('neighborhoods', [])}
    require(bool(hoods), 'This town has no neighborhoods to copy a new one from.', 422)
    template_hood = next(iter(hoods.values()))
    kept_hoods = []
    for group in graph['groups']:
        hood = hoods.get(group['id'])
        if hood is None:
            require(bool(packages.ID.match(group['id'])), f'"{group["id"]}" is not an id: use lowercase words joined by hyphens.', 422)
            hood = blank_from(template_hood, id=group['id'], name=group.get('label') or group['id'],
                              summary='To describe.', transit=[])
            hood['lat'], hood['lon'] = from_canvas(frame, group.get('x', SIZE / 2), group.get('y', SIZE / 2))
        else:
            hood = copy.deepcopy(hood)
            hood['name'] = group.get('label') or hood['name']
            x, y = to_canvas(frame, hood['lat'], hood['lon'])
            if 'x' in group and (abs(group['x'] - x) > 0.5 or abs(group['y'] - y) > 0.5):
                hood['lat'], hood['lon'] = from_canvas(frame, group['x'], group['y'])
        kept_hoods.append(hood)
    city['neighborhoods'] = kept_hoods
    places = {place['id']: place for place in city.get('places', [])}
    employers = {employer['id']: employer for employer in city.get('employers', [])}
    new_places, new_employers = [], []
    for node in graph['nodes']:
        require(bool(node.get('group')), f'{node.get("label") or node["id"]} needs to be in a neighborhood.', 422)
        if node['id'] in employers or node.get('kind') == 'employer':
            employer = employers.get(node['id'])
            require(employer is not None, 'New employers are added on the Employers tab, where their careers are chosen.', 422)
            new_employers.append({**employer, 'name': node.get('label') or employer['name'], 'neighborhood': node['group']})
            continue
        place = places.get(node['id'])
        if place is None:
            require(bool(packages.ID.match(node['id'])), f'"{node["id"]}" is not an id: use lowercase words joined by hyphens.', 422)
            kind = node.get('type') or 'shop'
            template = next((item for item in city.get('places', []) if item.get('kind') == kind),
                            (city.get('places') or [None])[0])
            require(template is not None, 'This town has no places to copy a new one from: add one on the Places tab.', 422)
            place = blank_from(template, id=node['id'], name=node.get('label') or node['id'], kind=kind,
                               summary='To describe.', tags=[], spots=[])
        new_places.append({**place, 'name': node.get('label') or place['name'], 'neighborhood': node['group']})
    city['places'], city['employers'] = new_places, new_employers
    towns.save(opened, town, 'cities', city)
    return town_graph(opened, town)


# Interior ---------------------------------------------------------------------------------------------------------

PASSAGE_KINDS = ('open', 'door', 'stairs', 'ladder', 'shaft', 'crawl', 'water', 'secret')
FLAGS = {'locked': 'lock', 'hidden': 'hidden', 'one way': 'one_way', 'trapped': 'trap'}
STYLES = ('cave', 'keep', 'crypt', 'mine', 'tower', 'sewer', 'ruin', 'building', 'other')


def interior_key(interior: str) -> str:
    return f'interior-{interior}'  # a history key is id-shaped, like TRAVEL_KEY


def interior_path(opened: worlds.Opened, interior: str):
    require(bool(packages.ID.match(interior or '')), f'"{interior}" is not an interior id.', 404)
    root = opened.data if opened.data else opened.folder / 'engine'
    return root / 'interiors' / f'{interior}.json'


def interiors(opened: worlds.Opened) -> list[dict]:
    """The world's interiors, with where each is entered from."""
    found, _ = worlds.contents(opened)
    return [{'id': key, 'name': item.get('name', key), 'style': item.get('style'), 'summary': item.get('summary', ''),
             'rooms': len(item.get('rooms') or []), 'at': item.get('at') or {}}
            for (kind, key), item in sorted(found['engine'].items()) if kind == 'interiors' and isinstance(item, dict)]


def passage_label(passage: dict) -> str:
    flags = [flag for flag, field in FLAGS.items() if passage.get(field)]
    return ' · '.join([passage.get('kind', 'open'), *flags])


def passage_from(label: str, old: dict | None) -> dict:
    """A passage's kind and flags from its label. A lock or trap keeps its details; a new lock is a normal one to pick
    or force, and a trap has to be written on the interior's form, since it needs an action and a threat."""
    parts = [part.strip().lower() for part in (label or '').split('·') if part.strip()]
    old = old or {}
    kind = parts.pop(0) if parts and parts[0] in PASSAGE_KINDS else old.get('kind', 'open')
    unknown = [part for part in parts if part not in FLAGS]
    require(not unknown, f'A passage is labelled like "door" or "stairs · locked · hidden" (kinds: '
                         f'{", ".join(PASSAGE_KINDS)}; flags: {", ".join(FLAGS)}), not "{label}".', 422)
    passage = {key: value for key, value in old.items() if key != 'between'}  # keeps the file's key order
    passage['kind'] = kind
    for flag, field in FLAGS.items():
        if flag not in parts:
            passage.pop(field, None)
    if 'locked' in parts:
        passage['lock'] = old.get('lock') or {'difficulty': 'normal'}
    if 'hidden' in parts:
        passage['hidden'] = True
    if 'one way' in parts:
        passage['one_way'] = True
    if 'trapped' in parts:
        require(bool(old.get('trap')), 'A new trap needs what the character tries and what goes wrong: write it in the '
                                       "interior's file, and the map keeps it.", 422)
        passage['trap'] = old['trap']
    return passage


def laid_out(rooms: list[dict], levels: list[dict]) -> dict[str, tuple[float, float, bool]]:
    """Each room's place on the canvas: where it was drawn, or (never drawn) in a row for its level."""
    rows = [level['id'] for level in levels] + [None]
    counts: dict[str | None, int] = {}
    placed = {}
    for room in rooms:
        at = room.get('map') or {}
        if 'x' in at and 'y' in at:
            placed[room['id']] = (round(at['x'] * SIZE, 1), round(at['y'] * SIZE, 1), True)
            continue
        row = rows.index(room.get('level')) if room.get('level') in rows else len(rows) - 1
        column = counts.get(room.get('level'), 0)
        counts[room.get('level')] = column + 1
        placed[room['id']] = (120 + 190 * column, 120 + (760 / max(1, len(rows) - 1)) * row, False)
    return placed


def interior_graph(opened: worlds.Opened, interior: str) -> dict:
    path = interior_path(opened, interior)
    require(path.is_file(), f'{interior} is not an interior of this world.', 404)
    data = json.loads(path.read_text(encoding='utf-8'))
    rooms, levels = data.get('rooms') or [], data.get('levels') or []
    where = laid_out(rooms, levels)
    nodes = [{'id': room['id'], 'label': room.get('name', room['id']), 'group': room.get('level'), 'kind': 'room',
              'type': room.get('kind'), 'x': where[room['id']][0], 'y': where[room['id']][1], 'placed': where[room['id']][2],
              'hidden': bool(room.get('hidden')), 'entrance': room['id'] == data.get('entrance'),
              'danger': bool(room.get('foes') or room.get('hazard'))} for room in rooms]
    groups = [{'id': level['id'], 'label': level.get('name') or level['id']} for level in levels]
    links = [{'from': passage['between'][0], 'to': passage['between'][1], 'label': passage_label(passage)}
             for passage in data.get('passages') or []]
    found, _ = worlds.contents(opened)
    kinds = sorted({room.get('kind') for (kind, _), item in found['engine'].items() if kind == 'interiors'
                    and isinstance(item, dict) for room in item.get('rooms') or []} - {None})
    return {'map': 'interior', 'interior': interior, 'name': data.get('name', interior), 'entrance': data.get('entrance'),
            'nodes': nodes, 'groups': groups, 'links': links, 'regions': groups, 'kinds': kinds,
            'passage_kinds': list(PASSAGE_KINDS)}


def checked(data: dict) -> dict:
    """The interior as Dungeon's own schema reads it, or the reasons it would refuse it."""
    try:
        schema.Interior.model_validate(data)
    except ValidationError as error:
        reasons = [problem['msg'].removeprefix('Value error, ') + (f' ({".".join(map(str, problem["loc"]))})'
                   if problem['loc'] else '') for problem in error.errors()[:6]]
        raise DomainError('Dungeon would refuse this interior: ' + '; '.join(reasons), 422) from error
    return data


def save_interior(opened: worlds.Opened, interior: str, graph: dict) -> dict:
    path = interior_path(opened, interior)
    require(path.is_file(), f'{interior} is not an interior of this world.', 404)
    before = path.read_text(encoding='utf-8')
    data = json.loads(before)
    old_rooms = {room['id']: room for room in data.get('rooms') or []}
    old_levels = {level['id']: level for level in data.get('levels') or []}
    source = next(iter(data.get('sources') or {}), None)
    where = laid_out(data.get('rooms') or [], data.get('levels') or [])
    levels = []
    for group in graph['groups']:
        require(bool(packages.ID.match(group['id'])), f'"{group["id"]}" is not an id: use lowercase words joined by hyphens.', 422)
        levels.append({**old_levels.get(group['id'], {'id': group['id']}), 'name': group.get('label') or group['id']})
    rooms = []
    for node in graph['nodes']:
        room = copy.deepcopy(old_rooms.get(node['id']))
        if room is None:
            require(bool(packages.ID.match(node['id'])), f'"{node["id"]}" is not an id: use lowercase words joined by hyphens.', 422)
            room = {'id': node['id'], 'name': node.get('label') or node['id'], 'kind': node.get('type') or 'room',
                    'summary': 'To describe.', 'source': source}
        room['name'] = node.get('label') or room['name']
        room['kind'] = node.get('type') or room['kind']
        if node.get('group'):
            room['level'] = node['group']
        else:
            room.pop('level', None)
        if node.get('hidden'):
            room['hidden'] = True
        else:
            room.pop('hidden', None)
        drawn = where.get(node['id'])
        if 'x' in node and (drawn is None or abs(node['x'] - drawn[0]) > 0.5 or abs(node['y'] - drawn[1]) > 0.5):
            room['map'] = {'x': round(min(1, max(0, node['x'] / SIZE)), 3), 'y': round(min(1, max(0, node['y'] / SIZE)), 3)}
        rooms.append({key: room[key] for key in ordered(room)})
    old_ways = {frozenset(passage['between']): passage for passage in data.get('passages') or []}
    passages, seen = [], set()
    for link in graph['links']:
        pair = frozenset((link['from'], link['to']))
        if pair in seen or len(pair) < 2:
            require(len(pair) == 2, 'A passage joins two different rooms.', 422)
            continue
        seen.add(pair)
        old = old_ways.get(pair)
        between = [link['from'], link['to']]
        passages.append({'between': between, **passage_from(link.get('label', ''), old)})
    entrance = graph.get('entrance') or data.get('entrance')
    data.update(levels=levels, rooms=rooms, passages=passages, entrance=entrance)
    if not levels:
        data.pop('levels', None)
    text = towns.dumped(checked(data), towns.indent_of(before), before)
    towns.write_tracked(path, text, before, interior_key(interior))
    return interior_graph(opened, interior)


ROOM_ORDER = ('id', 'name', 'level', 'kind', 'size', 'light', 'summary', 'features', 'hidden', 'foes', 'hazard', 'loot',
              'lore', 'map', 'source')


def ordered(room: dict) -> list[str]:
    return [key for key in ROOM_ORDER if key in room] + [key for key in room if key not in ROOM_ORDER]


def new_interior(opened: worlds.Opened, body: dict) -> dict:
    """A new interior with one room (its way in), entered from a town's place or a travel-map stop."""
    found, _ = worlds.contents(opened)
    world_id = found['world'].get('id') or opened.folder.name
    name = (body.get('name') or '').strip()
    require(bool(name), 'Name the interior.', 422)
    interior = body.get('id') or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    path = interior_path(opened, interior)
    require(not path.exists() and ('interiors', interior) not in found['engine'], f'There is already an interior {interior}.', 409)
    at = {key: body[key] for key in ('node', 'city', 'place') if body.get(key)}
    travel = found['engine'].get(('travel', world_id)) or {}
    if at.get('node'):
        stop = next((node for node in travel.get('nodes', []) if node.get('id') == at['node']), None)
        require(stop is not None, f'{at["node"]} is not a stop on the travel map.', 422)
        at.setdefault('city', stop.get('city'))
        at.setdefault('place', stop.get('place'))
    if at.get('place'):
        city = cities_of(found).get(at.get('city'))
        require(city is not None and any(place.get('id') == at['place'] for place in city.get('places', [])),
                f'{at.get("place")} is not a place of {at.get("city")}.', 422)
    style = body.get('style') or 'other'
    require(style in STYLES, f'An interior is one of: {", ".join(STYLES)}.', 422)
    data = {'schema_version': 1, 'id': interior, 'name': name, 'world': world_id, 'style': style,
            'summary': (body.get('summary') or '').strip() or 'To describe.', 'at': at, 'entrance': 'way-in',
            'rooms': [{'id': 'way-in', 'name': 'The way in', 'kind': 'entrance', 'summary': 'To describe.',
                       'map': {'x': 0.5, 'y': 0.12}, 'source': 'worldsmith'}],
            'passages': [], 'wanders': [],
            'sources': {'worldsmith': {'kind': 'user', 'title': 'Drawn in Worldsmith', 'license': 'All rights reserved',
                                       'retrieved': datetime.date.today().isoformat()}}}
    text = json.dumps(checked(data), indent=1, ensure_ascii=False) + '\n'
    towns.write_tracked(path, text, None, interior_key(interior))
    return {'id': interior}


# Both -------------------------------------------------------------------------------------------------------------

KINDS = ('travel', 'town', 'interior')
DIRECTIONS = {'travel': 'LR', 'town': 'TB', 'interior': 'TB'}


def history_key(kind: str, which: str | None) -> str:
    return TRAVEL_KEY if kind == 'travel' else interior_key(which or '') if kind == 'interior' else which or ''


def read(opened: worlds.Opened, kind: str, town: str | None = None) -> dict:
    """`town` names the town of a town map, or the interior of an interior map."""
    require(kind in KINDS, 'A map is the travel map, a town or an interior.', 404)
    graph = {'travel': lambda: travel_graph(opened), 'town': lambda: town_graph(opened, town or ''),
             'interior': lambda: interior_graph(opened, town or '')}[kind]()
    return {**graph, 'mermaid': mermaid.text(graph, DIRECTIONS[kind]), 'undo': towns.undoable(opened, history_key(kind, town))}


def save(opened: worlds.Opened, kind: str, graph: dict, town: str | None = None) -> dict:
    require(kind in KINDS, 'A map is the travel map, a town or an interior.', 404)
    try:
        if kind == 'travel':
            save_travel(opened, graph)
        elif kind == 'town':
            save_town(opened, town or '', graph)
        else:
            save_interior(opened, town or '', graph)
    except KeyError as error:
        raise DomainError(f'The map is missing {error}.', 422) from error
    return read(opened, kind, town)


def undo(opened: worlds.Opened, kind: str, town: str | None = None) -> dict:
    towns.undo(opened, history_key(kind, town))
    return read(opened, kind, town)
