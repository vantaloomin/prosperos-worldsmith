"""The new world wizard: a pitch becomes a whole world, drafted for the author to approve.

A new world starts as a folder holding only its name and pitch (`new_world`). The wizard then asks the model for
the world in four parts, each a JSON object checked here before the next is asked for:

1. The outline: the world's genre, era, money, voice, tier track and campaign start; its regions; its stops (towns,
   villages, ruins and landmarks, placed on a unit map); and the roads between them, with hours, terrain and danger.
2. The people: a name bank and heritage mix from Dungeon's own tables (worldsmith/names.py; a group of its own only
   for a people no bank fits, and a wide one), the careers the world's towns hire for, everyday prices and the climate.
3. The factions in play: goals, the stops they hold, rivals and allies, clocks, and the jobs they offer.
4. The story: the director's arcs, road and camp encounters by region, the wild sites a hex crawl rolls, hidden
   truths and lore.

The four become one draft. Approving it writes Dungeon's own files into the folder: world.json and the package
sections (regions, settlements, factions, hidden truths, lore, beats) and the engine data (the world's Road city,
its travel map, tiers, factions and arcs). The travel map is a hex crawl whose land is all generated around the
stops. Every stop starts as a place on the Road city; the town wizard then grows each town stop into a whole town
(`worldsmith.wizard`, `replaces`), taking the Road city's shared settings (money, era, names, careers).
"""
import json
import math
import re
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from worldsmith import drafts, models, names, settings, towns, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError, require
from worldsmith.dungeon_format.schema import Career, CityNames, Currency, Era, Month, Price

SOURCE = 'worldsmith'
Id = Annotated[str, Field(pattern=r'^[a-z0-9]+(-[a-z0-9]+)*$', max_length=80)]
Text = Annotated[str, Field(min_length=1, max_length=600)]
Danger = Literal['none', 'low', 'medium', 'high']
Difficulty = Literal['easy', 'normal', 'hard', 'very_hard', 'extreme']
STOP_KINDS = ('town', 'village', 'ruin', 'landmark')
SITE_KINDS = ('ruin', 'shrine', 'lair', 'camp', 'hamlet', 'cave', 'battlefield', 'grave', 'tower')
OWN_GIVEN, OWN_FAMILY = 30, 20
SIZES = {'small': (3, 5), 'medium': (5, 8), 'large': (8, 12)}
SYSTEM = drafts.SYSTEM.replace(
    'You write new entries for one town, in the\nexact JSON shape asked for, fitting the world\'s tone, era and '
    'existing people and places.',
    'You are building a whole new world with them, one part at a\ntime, in the exact JSON shape asked for, fitting '
    'the pitch and the parts already written.').replace(
    'Answer with only a JSON array of the new entries: no commentary, no code fences.',
    'Answer with only one JSON object: no commentary, no code fences.')


class Shape(BaseModel):
    model_config = ConfigDict(extra='ignore', populate_by_name=True)


# 1. The outline ---------------------------------------------------------------------------------------------------

class Region(Shape):
    id: Id
    name: Text
    summary: Text
    danger: Danger
    tier: int = Field(ge=1, le=5)


class Stop(Shape):
    id: Id
    name: Text
    region: Id
    kind: Literal['town', 'village', 'ruin', 'landmark']
    summary: Text
    spots: list[Text] = Field(min_length=1, max_length=4)
    safe: bool
    famous: bool = False
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Route(Shape):
    start: Id = Field(alias='from')
    to: Id
    hours: float = Field(gt=0, le=120)
    terrain: Text
    danger: Danger


class Track(Shape):
    track: Id
    name: Text
    words: list[Text] = Field(min_length=5, max_length=5)


class Outline(Shape):
    id: Id
    name: Text
    genre: Text
    pitch: Annotated[str, Field(min_length=1, max_length=2000)]
    era: Era
    timezone: Text
    start: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$')
    currency: Currency
    rent_period: Literal['month', 'week']
    speeds: dict[Id, float] = Field(min_length=1)
    preset: Literal['restrained', 'mature', 'unflinching']
    voice: Annotated[str, Field(max_length=300)]
    drama: Literal['quiet', 'uneasy', 'eventful', 'merciless']
    tiers: Track
    regions: list[Region] = Field(min_length=1, max_length=8)
    stops: list[Stop] = Field(min_length=2, max_length=16)
    routes: list[Route] = Field(min_length=1, max_length=40)
    starting_stop: Id

    @model_validator(mode='after')
    def check(self):
        regions = {region.id for region in self.regions}
        stops = {stop.id for stop in self.stops}
        problems = []
        if len(regions) != len(self.regions) or len(stops) != len(self.stops):
            problems.append('Region and stop ids must each be unique.')
        if regions & stops:
            problems.append(f'A stop and a region share an id: {sorted(regions & stops)}.')
        problems += [f'Stop {stop.id} names an unknown region {stop.region}.' for stop in self.stops
                     if stop.region not in regions]
        problems += [f'A road names an unknown stop ({route.start} to {route.to}).' for route in self.routes
                     if route.start not in stops or route.to not in stops or route.start == route.to]
        towns_ = [stop.id for stop in self.stops if stop.kind == 'town']
        if not towns_:
            problems.append('At least one stop must be a town.')
        if self.starting_stop not in towns_:
            problems.append('starting_stop must be one of the town stops.')
        if not problems and unreachable(self):
            problems.append(f'These stops have no road to the rest: {", ".join(unreachable(self))}.')
        if problems:
            raise ValueError(' '.join(problems))
        datetime.fromisoformat(self.start)
        return self


def unreachable(outline: Outline) -> list[str]:
    joined: dict[str, set[str]] = {stop.id: set() for stop in outline.stops}
    for route in outline.routes:
        joined[route.start].add(route.to)
        joined[route.to].add(route.start)
    seen, queue = {outline.stops[0].id}, deque([outline.stops[0].id])
    while queue:
        for other in joined[queue.popleft()] - seen:
            seen.add(other)
            queue.append(other)
    return sorted(set(joined) - seen)


# 2. The people ----------------------------------------------------------------------------------------------------

class Weather(Shape):
    summary: Text
    months: list[Month] = Field(min_length=12, max_length=12)


class People(Shape):
    names: CityNames
    careers: list[Career] = Field(min_length=6, max_length=20)
    prices: list[dict] = Field(min_length=4, max_length=20)
    climate: Weather
    kinds: Any = None

    @model_validator(mode='after')
    def check(self):
        ids = [career.id for career in self.careers]
        if len(ids) != len(set(ids)):
            raise ValueError('Career ids must be unique.')
        for price in self.prices:
            Price.model_validate(dict(price, source=SOURCE))
        return self


# 3. The factions ---------------------------------------------------------------------------------------------------

class Clock(Shape):
    id: Id
    name: Text
    segments: int = Field(ge=2, le=12)
    done: Text


class Tie(Shape):
    kind: Literal['npc', 'clue', 'place', 'item', 'faction']
    ref: Text


class Job(Shape):
    id: Id
    title: Text
    days: int = Field(ge=1, le=60)
    wages: int = Field(ge=1, le=60)
    standing: int = Field(ge=1, le=3)
    giver: Text
    hook: Text
    truth: Text
    missed: Text
    ties: list[Tie] = Field(default_factory=list, max_length=4)
    tier: int = Field(default=1, ge=1, le=5)


class Faction(Shape):
    id: Id
    name: Text
    kind: Id
    tier: int = Field(ge=1, le=5)
    summary: Text
    goals: list[Text] = Field(min_length=1, max_length=6)
    holds: list[Id] = Field(default_factory=list)
    rivals: list[Id] = Field(default_factory=list)
    allies: list[Id] = Field(default_factory=list)
    clocks: list[Clock] = Field(default_factory=list, max_length=4)
    jobs: list[Job] = Field(default_factory=list, max_length=5)


class Play(Shape):
    factions: list[Faction] = Field(min_length=2, max_length=8)


# 4. The story ----------------------------------------------------------------------------------------------------

class Stage(Shape):
    tier: int = Field(ge=1, le=5)
    truth: Text
    seed: Text
    word: Text


class Antagonist(Shape):
    name: Text
    agenda: Text
    where: list[Id] = Field(default_factory=list)


class Arc(Shape):
    id: Id
    name: Text
    seen: Text
    words: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(min_length=3, max_length=16)
    antagonist: Antagonist
    stages: list[Stage] = Field(min_length=2, max_length=6)


class Foe(Shape):
    name: Text
    count: int = Field(default=1, ge=1, le=8)
    vitality: int = Field(ge=4, le=30)
    resolve: int = Field(ge=4, le=30)
    weapon: int = Field(default=1, ge=0, le=4)
    wants: Literal['kill', 'rob', 'capture', 'drive-off'] = 'kill'


class Threat(Shape):
    text: Text
    foe: Foe


class Encounter(Shape):
    where: Literal['road', 'wild'] = 'road'
    weight: int = Field(default=1, ge=1, le=5)
    text: Text | None = None
    action: Text | None = None
    difficulty: Difficulty | None = None
    threat: Text | Threat | None = None

    @model_validator(mode='after')
    def check(self):
        rolled = (self.action, self.difficulty, self.threat)
        if all(part is None for part in rolled) == (self.text is None) or (None in rolled and any(rolled)):
            raise ValueError('An encounter is either just "text", or "action" with "difficulty" and "threat".')
        return self


class Site(Shape):
    weight: int = Field(default=1, ge=1, le=5)
    kind: Literal['ruin', 'shrine', 'lair', 'camp', 'hamlet', 'cave', 'battlefield', 'grave', 'tower']
    visible: bool
    names: list[Text] = Field(min_length=1, max_length=4)
    text: Text


class Truth(Shape):
    id: Id
    truth: Text
    believed: Text
    surfaces: list[Text] = Field(min_length=1, max_length=5)
    stakes: Text


class Lore(Shape):
    id: Id
    title: Text
    category: Literal['place', 'history', 'people', 'faith', 'custom', 'magic', 'thing']
    keywords: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(min_length=1, max_length=8)
    text: Annotated[str, Field(min_length=1, max_length=1500)]


class Story(Shape):
    default_spine: Id
    arcs: list[Arc] = Field(min_length=1, max_length=4)
    encounters: dict[Id, list[Encounter]]
    camp: dict[Id, list[Encounter]]
    owners: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(min_length=4, max_length=20)
    sites: list[Site] = Field(min_length=3, max_length=12)
    truths: list[Truth] = Field(min_length=1, max_length=8)
    lore: list[Lore] = Field(min_length=2, max_length=16)

    @model_validator(mode='after')
    def check(self):
        if self.default_spine not in {arc.id for arc in self.arcs}:
            raise ValueError('default_spine must be one of the arcs\' ids.')
        if not any(site.kind == 'hamlet' for site in self.sites):
            raise ValueError('Give the sites at least one hamlet.')
        return self


PARTS = {'outline': Outline, 'people': People, 'play': Play, 'story': Story}


# Asking ----------------------------------------------------------------------------------------------------------

def parsed_object(text: str, wanted: str) -> dict:
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{', text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(value, dict) and wanted in value:
            return value
    raise DomainError(f'The model did not answer with the world\'s {wanted} as JSON.', 502)


def problems_of(error: ValidationError) -> list[str]:
    return [' > '.join(str(part) for part in item['loc']) + ': ' + item['msg'] for item in error.errors()][:25]


def schema_of(part: str) -> str:
    return json.dumps(PARTS[part].model_json_schema(by_alias=True))


def outline_text(outline: dict) -> str:
    regions = '; '.join(f"{region['name']} ({region['id']}, {region['danger']} danger)" for region in outline['regions'])
    stops = '; '.join(f"{stop['name']} ({stop['id']}, a {stop['kind']} in {stop['region']}): {stop['summary']}"
                      for stop in outline['stops'])
    return (f"The world: {outline['name']} ({outline['genre']}), era {outline['era']}, money "
            f"{outline['currency']['name']}. {outline['pitch']}\nIts voice: {outline['voice']}\n"
            f"Regions: {regions}\nStops: {stops}")


def ask_for(part: str, pitch: str, done: dict, size: str, problems: list[str]) -> str:
    low, high = SIZES[size]
    lines = [f"The author's pitch for a new world: {pitch.strip()}"]
    if 'outline' in done:
        lines.append(outline_text(done['outline']))
    if part == 'outline':
        lines += ['\nWrite the outline of the world as one JSON object matching this schema:', schema_of(part),
                  f'\nGive it 2 to 5 regions and {low + 2} to {high + 3} stops, of which {low} to {high} are towns (the '
                  'rest villages, ruins and landmarks worth going to). Place stops on a unit map, x east and y south, '
                  'spread out, with neighbours near each other. Join every stop by roads, with hours on foot that fit '
                  'the distance (a day on foot is about 10 hours). "era" is the nearest of the listed eras; "timezone" '
                  'is a real IANA zone whose daylight fits the world; "start" is the moment a campaign begins, in the '
                  "world's own years. Tier track words run from a name in one's own street to a name the world knows. "
                  '"speeds" are km/h by way of getting around (walk at least).']
    elif part == 'people':
        lines += ['\nWrite the people of the world as one JSON object matching this schema:', schema_of(part),
                  '\nNames come from Dungeon\'s name banks, so towns get a wide spread: set "names.bank" to the bank '
                  'that fits best and "names.mix" to the weights of its groups (the commonest heritage heaviest). Only '
                  'for a people no bank fits (a non-human folk, an invented culture) add a group of its own under '
                  f'"names.groups", with at least {OWN_GIVEN} given and {OWN_FAMILY} family names that sound like real '
                  'names, and weigh it in the mix. The banks and their groups (a few names each):\n'
                  + names.prompt_text(done['outline']['era']) +
                  '\nAlso give 10 to 16 careers the towns hire for (common trades and the world\'s own; "eras" holds '
                  f'"{done["outline"]["era"]}"), 8 to 14 everyday prices in the world\'s money (a meal, a bed, a drink, '
                  'a weapon, a horse or the like; each with id, item, low, high, per), and the climate by month.']
    elif part == 'play':
        lines += ['\nWrite the factions in play as one JSON object matching this schema:', schema_of(part),
                  '\nGive 3 to 6 factions with clear goals that pull against each other. "holds" lists the stop ids '
                  'each one runs or leans on; "rivals" and "allies" name other faction ids. Give each 1 or 2 clocks '
                  '(what happens when they get their way) and 1 to 3 jobs: work they pay for in the towns they hold, '
                  'with the truth behind it, what happens if it is missed, and the loose ends it leaves.']
    else:
        regions = ', '.join(region['id'] for region in done['outline']['regions'])
        factions = ', '.join(f"{faction['name']} ({faction['id']})" for faction in done['play']['factions'])
        lines += [f'Factions: {factions}',
                  '\nWrite the story of the world as one JSON object matching this schema:', schema_of(part),
                  f'\nGive 1 to 3 arcs the story director can run, each with 3 to 5 stages rising in tier: what is '
                  'true at that stage, a seed the narrator can plant, and the word that reaches someone who was not '
                  f'there. "encounters" and "camp" are keyed by region id ({regions}, and "wilds" for land past the '
                  'map), 3 to 6 road encounters and 2 to 4 night-camp encounters each; an encounter is just "text" '
                  '(something that happens) or "action", "difficulty" and "threat" (something to roll against; a '
                  'threat may bring a foe with vitality and resolve around 8 to 14). "owners" are local names for '
                  'wild sites ("{owner}\'s Tower"); "sites" are what a hex crawl finds off the roads, at least one a '
                  'hamlet. Add 2 to 5 hidden truths and 4 to 10 lore entries.']
    if problems:
        lines += ['\nYour last answer was refused for these problems; fix them:', *problems]
    return '\n'.join(lines)


def written(part: str, pitch: str, done: dict, size: str) -> dict:
    problems: list[str] = []
    wanted = {'outline': 'stops', 'people': 'careers', 'play': 'factions', 'story': 'arcs'}[part]
    for _ in range(2):
        answer = parsed_object(models.complete(SYSTEM, ask_for(part, pitch, done, size, problems)), wanted)
        try:
            PARTS[part].model_validate(answer)
        except ValidationError as error:
            problems = problems_of(error)
            continue
        problems = extra_problems(part, answer, done)
        if not problems:
            return answer
    raise DomainError(f'The model\'s {part} still had problems after a retry: ' + '; '.join(problems[:6]), 422)


def name_problems(chosen: dict, era: str) -> list[str]:
    """A world's names must draw on a real bank, weigh only groups there are, and keep own groups wide and real."""
    bank = names.bank_of(chosen, era)
    if bank not in names.banks():
        return [f'names.bank {bank!r} is not one of the banks: {", ".join(sorted(names.banks()))}.']
    own = chosen.get('groups') or {}
    found = [f'names.mix weighs {key!r}, which is not a group of the {bank} bank or of names.groups.'
             for key in chosen.get('mix') or {} if key not in names.banks()[bank] and key not in own]
    for key, group in own.items():
        given = [*group.get('feminine', []), *group.get('masculine', []), *group.get('neutral', [])]
        if len(set(given)) < OWN_GIVEN or len(set(group.get('family', []))) < OWN_FAMILY:
            found.append(f'names.groups.{key} needs at least {OWN_GIVEN} given and {OWN_FAMILY} family names.')
        coined = names.invented_in(*given, *group.get('family', []))
        if coined:
            found.append(f'names.groups.{key} has names that read as made up: {", ".join(coined[:10])}. Use '
                         'plainer ones.')
    return found


def extra_problems(part: str, answer: dict, done: dict) -> list[str]:
    """What the parts must agree on between them."""
    if part == 'people':
        return name_problems(answer['names'], done['outline']['era'])
    if part == 'play':
        stops = {stop['id'] for stop in done['outline']['stops']}
        factions = {faction['id'] for faction in answer['factions']}
        found = [f"{faction['id']} holds unknown stops {sorted(set(faction.get('holds') or []) - stops)}"
                 for faction in answer['factions'] if not set(faction.get('holds') or []) <= stops]
        found += [f"{faction['id']} names unknown factions" for faction in answer['factions']
                  if not set((faction.get('rivals') or []) + (faction.get('allies') or [])) <= factions]
        return found
    if part == 'story':
        regions = {region['id'] for region in done['outline']['regions']} | {'wilds'}
        found = [f'encounters for unknown region {key}' for key in answer['encounters'] if key not in regions]
        found += [f'camp for unknown region {key}' for key in answer['camp'] if key not in regions]
        found += [f'no camp encounters for region {key}' for key in regions if not answer['camp'].get(key)]
        return found
    return []


# Making the world's files ------------------------------------------------------------------------------------------

def source() -> dict:
    return {'kind': 'curated', 'title': "Written with Prospero's Worldsmith", 'license': 'All rights reserved',
            'retrieved': date.today().isoformat()}


def road_id(world_id: str) -> str:
    return f'{world_id}-road'


def lat_lon(stop: dict) -> tuple[float, float]:
    """A stop's stand-in position on the globe (Dungeon only uses it for distances inside a town)."""
    return round(50 - stop['y'] * 4, 4), round(stop['x'] * 6 - 3, 4)


def road_city(world_id: str, outline: dict, people: dict) -> dict:
    """The world's Road city: every stop as a place in its region, the wilds, and the shared settings new towns copy
    (money, era, speeds, names, careers, prices, climate, voice)."""
    hoods = []
    for region in outline['regions'] + [{'id': 'wilds', 'name': 'the wilds', 'summary': 'Land past the maps.'}]:
        at = next((lat_lon(stop) for stop in outline['stops'] if stop['region'] == region['id']), (50.0, 0.0))
        hoods.append({'id': region['id'], 'name': region['name'], 'summary': region['summary'],
                      'vibe': ['roads'], 'lat': at[0], 'lon': at[1], 'rent_tier': 'low', 'housing': ['inn-room'],
                      'walkability': 'low', 'transit': ['on-foot'], 'source': SOURCE})
    places = [{'id': stop['id'], 'name': stop['name'], 'kind': 'landmark', 'neighborhood': stop['region'],
               'summary': stop['summary'], 'tags': ['travel', 'local'], 'cost': 'free', 'setting': 'outdoor',
               'good_for': ['solo', 'friends'], 'day_parts': ['morning', 'afternoon', 'evening', 'late'],
               'spots': stop['spots'], 'source': SOURCE} for stop in outline['stops']]
    places.append({'id': 'the-wilds', 'name': 'the wilds', 'kind': 'trail', 'neighborhood': 'wilds',
                   'summary': 'Out in the wilds, off the roads, between one place and the next.', 'tags': ['travel'],
                   'cost': 'free', 'setting': 'outdoor', 'good_for': ['solo', 'friends'],
                   'day_parts': ['morning', 'afternoon', 'evening', 'late'], 'source': SOURCE})
    first = lat_lon(outline['stops'][0])
    city = {
        'schema_version': 1, 'id': road_id(world_id), 'name': 'the Road', 'setting': 'original',
        'era': outline['era'], 'category': 'fictional', 'basis': f"The stops of {outline['name']} not yet built out "
        'as towns, and the wilds between them.', 'region': outline['name'], 'country': outline['name'],
        'timezone': outline['timezone'], 'summary': f"On the road in {outline['name']}, between towns.",
        'home': False, 'town_map': {'style': 'none'}, 'lat': first[0], 'lon': first[1],
        'intensity': {'preset': outline['preset'], 'voice': outline['voice'], 'drama': outline['drama']},
        'currency': outline['currency'], 'rent_period': outline['rent_period'], 'speeds': outline['speeds'],
        'sources': {SOURCE: source()}, 'neighborhoods': hoods, 'places': places,
        'transit': [{'id': 'on-foot', 'name': 'On foot', 'kind': 'walk', 'summary': 'Walking the roads.',
                     'source': SOURCE}],
        'careers': people['careers'], 'calendar': 'none', 'names': people['names'],
        'prices': [dict(price, source=SOURCE) for price in people['prices']],
        'climate': dict(people['climate'], source=SOURCE),
    }
    year = int(outline['start'][:4])
    if 1 <= year <= 3000:
        city['names'] = dict(city['names'], year=year)
    if people.get('kinds'):
        city['kinds'] = people['kinds']
    return city


def span_for(outline: dict) -> int:
    """Hexes across the unit map, so a road walked hex by hex (an hour a hex) takes about its stated hours."""
    stops = {stop['id']: stop for stop in outline['stops']}
    rates = []
    for route in outline['routes']:
        a, b = stops[route['from']], stops[route['to']]
        apart = math.hypot(a['x'] - b['x'], a['y'] - b['y'])
        if apart > 0.01:
            rates.append(route['hours'] / (apart * 1.15))
    rates.sort()
    return max(20, min(200, round(rates[len(rates) // 2]))) if rates else 100


def travel_map(world_id: str, outline: dict, story: dict) -> dict:
    road = road_id(world_id)
    regions = {region['id']: {'name': region['name'], 'danger': region['danger'], 'tier': region['tier']}
               for region in outline['regions']}
    regions['wilds'] = {'name': 'the wilds past the maps', 'danger': 'high', 'tier': max(
        [region['tier'] for region in outline['regions']] + [2])}
    by_danger = sorted(outline['regions'], key=lambda region: ('none', 'low', 'medium', 'high').index(region['danger']))
    frontier = [region['id'] for region in by_danger[-2:]] + ['wilds']
    sites = {'odds': 7, 'owners': story['owners'], 'any': [Site.model_validate(site).model_dump() for site in story['sites']]}
    return {
        'about': f"{outline['name']}'s travel map, made with Prospero's Worldsmith. A hex crawl whose land is all "
                 'generated around its stops; each stop is a town, or a place on the Road city until it is built out.',
        'world': world_id, 'travel': 'hex', 'hexes': world_id,
        'hex_map': {'miles': 6, 'generate': {'span': span_for(outline), 'water': 0.3, 'frontier': frontier}},
        'wild': {'id': 'the-wilds', 'name': 'the wilds', 'region': 'wilds', 'city': road, 'place': 'the-wilds',
                 'safe': False},
        'hours_a_day': 10, 'odds': {'none': 0, 'low': 15, 'medium': 30, 'high': 50}, 'food': [],
        'nodes': [{'id': stop['id'], 'name': stop['name'], 'region': stop['region'], 'city': road,
                   'place': stop['id'], 'safe': stop['safe'], **({'famous': True} if stop.get('famous') else {}),
                   'map': {'x': round(stop['x'], 3), 'y': round(stop['y'], 3)}} for stop in outline['stops']],
        'routes': [{'from': route['from'], 'to': route['to'], 'hours': route['hours'], 'terrain': route['terrain'],
                    'danger': route['danger']} for route in outline['routes']],
        'regions': regions,
        'encounters': {key: [clean(entry) for entry in entries] for key, entries in story['encounters'].items()},
        'camp': {key: [clean(entry, camp=True) for entry in entries] for key, entries in story['camp'].items()},
        'sites': sites,
    }


def clean(entry: dict, camp: bool = False) -> dict:
    """An encounter as Dungeon reads it: the parts that are set, foes with their defaults filled in."""
    found = {key: value for key, value in Encounter.model_validate(entry).model_dump(exclude_none=True).items()}
    if camp:
        found.pop('where', None)
    return found


def tiers_file(outline: dict) -> dict:
    track = outline['tiers']
    start = outline['start'] if len(outline['start']) > 16 else outline['start'] + ':00'
    return {'about': f"{outline['name']}'s tier track (dungeon/tiers.py), made with Prospero's Worldsmith.",
            'track': track['track'], 'name': track['name'], 'arc': 'classic', 'pace': 'steady', 'start': start,
            'words': track['words']}


def factions_file(world_id: str, play: dict) -> dict:
    return {'about': "Factions in play, made with Prospero's Worldsmith.", 'world': world_id, 'pace': 25,
            'factions': [Faction.model_validate(faction).model_dump() for faction in play['factions']]}


def arcs_file(world_id: str, story: dict) -> dict:
    return {'about': "Arcs for the story director (dungeon/director.py), made with Prospero's Worldsmith.",
            'world': world_id, 'default_spine': story['default_spine'],
            'arcs': [Arc.model_validate(arc).model_dump() for arc in story['arcs']]}


def package_files(world_id: str, outline: dict, play: dict, story: dict, old: dict) -> dict[str, dict]:
    """world.json and the package sections, as files by name."""
    holder = {stop: faction['id'] for faction in play['factions'] for stop in faction.get('holds') or []}
    world = {key: value for key, value in old.items() if key not in ('pitch',)} | {
        'schema_version': 1, 'id': world_id, 'name': outline['name'], 'status': old.get('status', 'draft'),
        'genre': outline['genre'], 'pitch': outline['pitch'], 'default_ruleset': old.get('default_ruleset', 'marvel'),
        'source': "Written with Prospero's Worldsmith from the author's pitch.",
        'calendar': {'note': 'The campaign starts on the date the tier file gives.', 'campaign_start': outline['start']},
        'currency': {'base': outline['currency']['code'], 'name': outline['currency']['name'],
                     'symbol': outline['currency']['symbol']},
        'tiers': {'track': outline['tiers']['track']},
        'intensity_defaults': {'preset': outline['preset']},
        'tone': {'voice': outline['voice'], 'drama': outline['drama']},
        'starting_place': {'settlement': outline['starting_stop']},
    }
    return {
        'world.json': world,
        'regions.json': {'schema_version': 1, 'regions': [
            {'id': region['id'], 'name': region['name'], 'summary': region['summary'], 'danger': region['danger'],
             'settlements': [stop['id'] for stop in outline['stops'] if stop['region'] == region['id']]}
            for region in outline['regions']]},
        'settlements.json': {'schema_version': 1, 'settlements': [
            {'id': stop['id'], 'name': stop['name'], 'region': stop['region'], 'kind': stop['kind'],
             'summary': stop['summary'], **({'faction': holder[stop['id']]} if stop['id'] in holder else {})}
            for stop in outline['stops']]},
        'factions.json': {'schema_version': 1, 'factions': [
            {'id': faction['id'], 'name': faction['name'], 'kind': faction['kind'], 'summary': faction['summary'],
             'goals': faction['goals']} for faction in play['factions']]},
        'hidden-truths.json': {'schema_version': 1, 'truths': [Truth.model_validate(truth).model_dump()
                                                               for truth in story['truths']]},
        'lore.json': {'schema_version': 1, 'entries': [Lore.model_validate(entry).model_dump()
                                                       for entry in story['lore']]},
        'beats.json': {'schema_version': 1, 'arcs': [
            {'id': arc['id'], 'name': arc['name'], 'kind': 'spine' if arc['id'] == story['default_spine'] else 'arc',
             'summary': arc['seen'], 'beats': [stage['truth'] for stage in arc['stages']]} for arc in story['arcs']]},
    }


def assembled(opened: worlds.Opened, parts: dict) -> dict:
    """Every file the world will be written as: {"files": {path in the folder: data}}, and a summary to show."""
    found, _ = worlds.contents(opened)
    world_id = found['world'].get('id') or opened.folder.name
    outline, people, play, story = (parts[key] for key in PARTS)
    files = package_files(world_id, outline, play, story, found['world'])
    files |= {
        f'engine/cities/{road_id(world_id)}.json': road_city(world_id, outline, people),
        f'engine/travel/{world_id}.json': travel_map(world_id, outline, story),
        f'engine/tiers/{world_id}.json': tiers_file(outline),
        f'engine/factions/{world_id}.json': factions_file(world_id, play),
        f'engine/arcs/{world_id}.json': arcs_file(world_id, story),
    }
    return {'id': world_id, 'name': outline['name'], 'summary': outline['pitch'], 'genre': outline['genre'],
            'regions': len(outline['regions']), 'stops': len(outline['stops']),
            'towns': [stop['name'] for stop in outline['stops'] if stop['kind'] == 'town'],
            'factions': len(play['factions']), 'arcs': len(story['arcs']), 'careers': len(people['careers']),
            'files': files}


def problems_in(files: dict) -> list[str]:
    """What Dungeon's format would refuse in the files: the package's own checks, and the Road city's."""
    contents = {'world': files['world.json'], 'documents': {}, 'assets': {}, 'engine': {},
                'sections': {name[:-5]: data for name, data in files.items()
                             if '/' not in name and name[:-5] in packages.SECTIONS}}
    found = packages.validate(contents)
    for name, data in files.items():
        if name.startswith('engine/cities/'):
            found += towns.problems_in('cities', data)
    return found


# The wizard ------------------------------------------------------------------------------------------------------

def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:60] or 'new-world'


def worlds_home() -> Path:
    return settings.home() / 'worlds'


def new_world(name: str, pitch: str, parent: str | None = None) -> worlds.Opened:
    """A new world folder holding only its name and pitch, ready for the wizard."""
    require(bool(name.strip()), 'Give the world a name.', 422)
    world_id = slug(name)
    folder = (Path(parent).expanduser() if parent else worlds_home()) / world_id
    require(not folder.exists(), f'{folder} already exists; pick another name or folder.', 409)
    folder.mkdir(parents=True)
    world = {'schema_version': 1, 'id': world_id, 'name': name.strip(), 'status': 'draft', 'genre': '',
             'pitch': pitch.strip(), 'default_ruleset': 'marvel'}
    (folder / 'world.json').write_text(json.dumps(world, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    settings.remember_folder(folder)
    return worlds.Opened(folder)


def draft_world(opened: worlds.Opened, pitch: str = '', size: str = 'medium') -> dict:
    """Ask for the world part by part, and queue it as one draft."""
    require(opened.kind == 'folder', 'The new world wizard makes a world of your own, not a built-in one.', 409)
    require(size in SIZES, f'Size is one of {", ".join(SIZES)}.', 422)
    found, _ = worlds.contents(opened)
    pitch = pitch.strip() or found['world'].get('pitch') or ''
    require(bool(pitch), 'Give the world a pitch: what it is, who holds power, what is going wrong.', 422)
    name = found['world'].get('name')
    done: dict[str, dict] = {}
    for part in PARTS:
        done[part] = written(part, pitch + (f' The world is called {name}.' if name else ''), done, size)
    world = assembled(opened, done)
    problems = problems_in(world['files'])
    if problems:
        raise DomainError('Dungeon would refuse the drafted world: ' + '; '.join(problems[:6]), 422)
    return drafts.queue(opened, world['id'], 'world', pitch, [world])


def approve_world(opened: worlds.Opened, entry: dict) -> dict:
    """Write the drafted world's files into its folder (the Road city's write can be undone from its town)."""
    files = entry['files']
    problems = problems_in(files)
    if problems:
        raise DomainError('Dungeon would refuse this world now: ' + '; '.join(problems[:6]), 409)
    road = road_id(entry['id'])
    for name, data in files.items():
        path = opened.folder / name
        require(path.resolve().is_relative_to(opened.folder.resolve()), f'{name} is outside the world folder.', 422)
        before = path.read_text(encoding='utf-8') if path.is_file() else None
        indent = 1 if name.startswith(('engine/cities/', 'engine/travel/', 'engine/factions/', 'engine/arcs/')) else 2
        towns.write_tracked(path, towns.dumped(data, indent), before, road, f'world-{entry["id"]}')
    return worlds.overview(opened)


def town_stops(opened: worlds.Opened) -> list[dict]:
    """The world's town stops still waiting on the Road city to be built out, with their pitch for the town wizard."""
    found, _ = worlds.contents(opened)
    world_id = found['world'].get('id') or opened.folder.name
    travel = found['engine'].get(('travel', world_id)) or {}
    settlements = {item.get('id'): item for item in (found['sections'].get('settlements') or {}).get('settlements', [])
                   if isinstance(item, dict)}
    road = road_id(world_id)
    waiting = []
    for node in travel.get('nodes') or []:
        settlement = settlements.get(node.get('id')) or {}
        if node.get('city') == road and settlement.get('kind') == 'town':
            waiting.append({'id': node['id'], 'name': node.get('name') or node['id'],
                            'pitch': settlement.get('summary', '')})
    return waiting
