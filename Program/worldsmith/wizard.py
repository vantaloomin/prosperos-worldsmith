"""The new town wizard: a pitch becomes a whole draft town, reviewed and approved like any other draft.

The model writes the town's own content (summary, neighborhoods, places, notables, employers, prices, customs,
events, transit, climate). What a town shares with its world is copied from a sibling town instead of guessed:
currency, era, setting, calendar, name banks, intensity, speeds, rent period and the like, with the map position
near the sibling. Every record cites one Worldsmith source. Employers may only hire for careers Dungeon offers the
town: the shared catalogue for its era (careers.json), its own, or a sibling town's own career, which is copied
into the new town, since Dungeon refuses any other.

Approving writes the city file and puts the town on the world's travel map, either as a new stop joined to a
neighbor by a road, or in place of an existing roadside stop (a village on the road becomes a full town).
"""
import copy
import json
import re
import uuid
from datetime import date
from pathlib import Path

from worldsmith import drafts, models, settings, towns, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError, require
from worldsmith.dungeon_format.schema import City

SOURCE = 'worldsmith'
SHARED = ('setting', 'era', 'category', 'region', 'country', 'timezone', 'intensity', 'currency', 'rent_period',
          'speeds', 'names', 'calendar', 'work_by_gender', 'kinds')
WRITTEN = ('id', 'name', 'summary', 'aliases', 'basis', 'neighborhoods', 'places', 'notables', 'employers', 'careers',
           'career_hubs', 'transit', 'climate', 'annual_events', 'local_color', 'prices', 'water', 'town_map')
RECORD_LISTS = ('neighborhoods', 'places', 'colleges', 'employers', 'career_hubs', 'transit', 'annual_events',
                'local_color', 'prices', 'notables')
DANGERS = ('none', 'low', 'medium', 'high')
SYSTEM = drafts.SYSTEM.replace('Answer with only a JSON array of the new entries: no commentary, no code fences.',
                               'Answer with only one JSON object, the town: no commentary, no code fences.')


def sibling_of(found: dict, near: str | None) -> dict:
    """The town whose shared settings the new one copies: the one it is near, else the world's first real town."""
    cities = {key: city for (kind, key), city in found['engine'].items() if kind == 'cities' and isinstance(city, dict)}
    real = [key for key, city in sorted(cities.items()) if (city.get('town_map') or {}).get('style') != 'none']
    require(bool(real), 'This world has no town to copy shared settings from yet.', 409)
    return cities[near] if near in real else cities[real[0]]


def shared_careers(opened: worlds.Opened, era: str | None) -> set[str]:
    """Dungeon's shared careers for an era, from the checkout this world lives in (or the one in Settings)."""
    places = [opened.data / 'careers.json']
    checkout = settings.load().get('dungeon_checkout')
    if checkout:
        places.append(Path(checkout) / worlds.DATA / 'careers.json')
    for path in places:
        if path.is_file():
            catalogue = json.loads(path.read_text(encoding='utf-8')).get('careers') or []
            return {career['id'] for career in catalogue if era in career.get('eras', ['modern'])}
    return set()


def borrowable_careers(found: dict) -> dict[str, dict]:
    """The world's towns' own careers, by id, so a new town can take one on."""
    own: dict[str, dict] = {}
    for (kind, _), city in found['engine'].items():
        if kind == 'cities' and isinstance(city, dict):
            own |= {career['id']: career for career in city.get('careers') or [] if isinstance(career, dict)}
    return own


def source() -> dict:
    return {'kind': 'curated', 'title': "Written with Prospero's Worldsmith", 'license': 'All rights reserved',
            'retrieved': date.today().isoformat()}


def town_schema() -> dict:
    full = City.model_json_schema()
    return {**full, 'properties': {key: value for key, value in full['properties'].items() if key in WRITTEN},
            'required': [key for key in full['required'] if key in WRITTEN]}


def assembled(written: dict, sibling: dict, shared: set[str], borrowable: dict[str, dict]) -> dict:
    """The model's town joined to the shared settings and the source, with records citing the source, employers
    hiring only for careers Dungeon will offer the town (a sibling's own career is copied in) and neighborhoods
    naming only the town's own transit lines."""
    city = {key: sibling[key] for key in SHARED if key in sibling}
    city |= {key: value for key, value in written.items() if key in WRITTEN}
    city['schema_version'] = 1
    city['sources'] = {SOURCE: source()}
    city.setdefault('lat', sibling.get('lat', 0) + 0.05)
    city.setdefault('lon', sibling.get('lon', 0) + 0.05)
    for key in RECORD_LISTS:
        city[key] = [dict(item, source=SOURCE) for item in city.get(key) or [] if isinstance(item, dict)]
    if isinstance(city.get('climate'), dict):
        city['climate'] = dict(city['climate'], source=SOURCE)
    city['careers'] = [item for item in city.get('careers') or [] if isinstance(item, dict)]
    own = {career.get('id') for career in city['careers']}
    for employer in city['employers']:
        kept = []
        for career in employer.get('careers') or []:
            if career not in shared and career not in own and career in borrowable:
                city['careers'].append(copy.deepcopy(borrowable[career]))
                own.add(career)
            if career in shared or career in own:
                kept.append(career)
        employer['careers'] = kept
    city['employers'] = [employer for employer in city['employers'] if employer['careers']]
    lines = {line.get('id') for line in city['transit']}
    for hood in city['neighborhoods']:
        hood['transit'] = [line for line in hood.get('transit') or [] if line in lines]
    return city


def problems_of(city: dict, found: dict) -> list[str]:
    problems = towns.problems_in('cities', city)
    if ('cities', city.get('id')) in found['engine']:
        problems.append(f"There is already a town with the id {city.get('id')}; pick another.")
    return problems


def prompt_for(found: dict, sibling: dict, careers: list[str], pitch: str, name: str, problems: list[str]) -> str:
    world = found['world']
    others = [f"{item['name']} ({item['id']})" for item in worlds.towns(found)]
    lines = [f"World: {world.get('name')} ({world.get('genre', '')}). {world.get('pitch', '')}",
             f"Era: {sibling.get('era')}. Money: {(sibling.get('currency') or {}).get('name', '')}. "
             f"Near: {sibling.get('name')}, {sibling.get('summary', '')}",
             f"Other towns: {', '.join(others)}",
             f"Careers employers may hire for (or add the town's own under \"careers\"): {', '.join(careers)}",
             '\nWrite a whole new town as one JSON object matching this schema (Dungeon refuses anything else; leave '
             'out "source" fields, they are filled in for you):', json.dumps(town_schema()),
             f'\nThe author\'s pitch: {pitch.strip()}']
    if name.strip():
        lines.append(f'Call the town {name.strip()}.')
    lines.append('Give it 3 to 6 neighborhoods, 12 to 20 places across them (somewhere to eat or drink in each), 4 to 8 '
                 'notables with wants and secrets, a few employers, prices in the local money, local color, one or two '
                 'yearly events, a climate with 12 months, and how people get around.')
    if problems:
        lines += ['\nYour last answer was refused for these problems; fix them:', *problems[:25]]
    return '\n'.join(lines)


def parsed_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(value, dict) and value.get('places'):
            return value
    raise DomainError('The model did not answer with a town as JSON.', 502)


def draft_town(opened: worlds.Opened, pitch: str, name: str = '', near: str | None = None,
               replaces: str | None = None, hours: float = 8, terrain: str = 'the road', danger: str = 'low') -> dict:
    require(bool(pitch.strip()), 'Give the town a pitch: what it is, who runs it, what is wrong there.', 422)
    require(danger in DANGERS, f'Danger is one of {", ".join(DANGERS)}.', 422)
    found, _ = worlds.contents(opened)
    sibling = sibling_of(found, near)
    shared, borrowable = shared_careers(opened, sibling.get('era')), borrowable_careers(found)
    careers = sorted(shared | borrowable.keys())
    problems: list[str] = []
    for _ in range(2):
        city = assembled(parsed_object(models.complete(SYSTEM, prompt_for(found, sibling, careers, pitch, name,
                                                                         problems))), sibling, shared, borrowable)
        problems = problems_of(city, found)
        if not problems:
            break
    else:
        raise DomainError('The model\'s town still had problems after a retry: ' + '; '.join(problems[:6]), 422)
    hookup = {'near': near, 'replaces': replaces, 'hours': hours, 'terrain': terrain, 'danger': danger}
    return drafts.queue(opened, city['id'], 'town', pitch, [city | {'_travel': hookup}])


def travel_file(opened: worlds.Opened, world_id: str):
    root = opened.data if opened.data else opened.folder / 'engine'
    return root / 'travel' / f'{world_id}.json'


def first_place(city: dict) -> str:
    places = city['places']
    central = [place for place in places if place.get('kind') in ('square', 'market', 'green', 'gate')]
    return (central or places)[0]['id']


def place_on_map(opened: worlds.Opened, city: dict, hookup: dict, batch: str | None = None):
    """Put the town on the world's travel map (nothing to do for a world without one)."""
    found, _ = worlds.contents(opened)
    path = travel_file(opened, found['world'].get('id') or opened.folder.name)
    if not path.is_file():
        return
    before = path.read_text(encoding='utf-8')
    travel = json.loads(before)
    nodes = travel.setdefault('nodes', [])
    replaced = next((node for node in nodes if node.get('id') == hookup.get('replaces')), None)
    if replaced:
        replaced.update(city=city['id'], place=first_place(city), name=city['name'])
    else:
        near = next((node for node in nodes if node.get('city') == hookup.get('near') or node.get('id') == hookup.get('near')),
                    nodes[0] if nodes else None)
        node = {'id': city['id'], 'name': city['name'], 'city': city['id'], 'place': first_place(city), 'safe': True}
        if near:
            node['region'] = near.get('region')
            if near.get('map'):
                node['map'] = {'x': round(min(1, near['map']['x'] + 0.04), 3), 'y': round(min(1, near['map']['y'] + 0.03), 3)}
            travel.setdefault('routes', []).append({'from': near['id'], 'to': city['id'], 'hours': hookup.get('hours', 8),
                                                    'terrain': hookup.get('terrain', 'the road'),
                                                    'danger': hookup.get('danger', 'low')})
        nodes.append(node)
    towns.write_tracked(path, towns.dumped(travel, towns.indent_of(before)), before, city['id'], batch)


def approve_town(opened: worlds.Opened, entry: dict) -> dict:
    city = {key: value for key, value in entry.items() if key != '_travel'}
    found, _ = worlds.contents(opened)
    problems = problems_of(city, found)
    if problems:
        raise DomainError('Dungeon would refuse this town now: ' + '; '.join(problems[:6]), 409)
    require(bool(packages.ID.match(city['id'])), 'The town id must be lowercase words joined by hyphens.', 422)
    batch = uuid.uuid4().hex
    towns.save(opened, city['id'], 'cities', city, batch)
    place_on_map(opened, city, entry.get('_travel') or {}, batch)
    return towns.read(opened, city['id'])
