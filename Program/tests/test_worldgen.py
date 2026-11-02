"""The new world wizard: a pitch becomes a whole world (outline, people, factions, story) drafted for approval, written
as Dungeon's own files, and its town stops grown into towns by the town wizard."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FIXTURES
from tests.test_wizard import written_town
from worldsmith import drafts, models, package_files, wizard, worldgen, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app

PARTS = {'Write the outline': 'outline', 'Write the people': 'people', 'Write the factions': 'play',
         'Write the story': 'story'}


def answers() -> dict:
    return json.loads((FIXTURES / 'new_world.json').read_text(encoding='utf-8'))


def fake_model(monkeypatch, parts: dict | None = None, asked: list | None = None):
    parts = parts or answers()

    def complete(system, prompt):
        if asked is not None:
            asked.append(prompt)
        part = next(part for words, part in PARTS.items() if words in prompt)
        answer = parts[part]
        return 'Here it is:\n' + json.dumps(answer.pop(0) if isinstance(answer, list) else answer)
    monkeypatch.setattr(models, 'complete', complete)


def test_a_pitch_becomes_one_world_draft_and_nothing_is_written_until_it_is_approved(monkeypatch):
    opened = worldgen.new_world('Saltmarch', 'Salt pans owned by a water guild.')
    asked = []
    fake_model(monkeypatch, asked=asked)
    draft = worldgen.draft_world(opened)
    assert [next(part for words, part in PARTS.items() if words in prompt) for prompt in asked] == list(worldgen.PARTS)
    assert 'Salt pans owned by a water guild.' in asked[0] and 'Brinemouth' in asked[3] and 'brine-guild' in asked[3]
    world = draft['entries'][0]
    assert draft['target'] == 'world' and world['towns'] == ['Brinemouth', 'Crake Hollow'] and draft['hidden'] == 1
    assert sorted(world['files']) == sorted([
        'world.json', 'regions.json', 'settlements.json', 'factions.json', 'hidden-truths.json', 'lore.json',
        'beats.json', 'engine/cities/saltmarch-road.json', 'engine/travel/saltmarch.json',
        'engine/tiers/saltmarch.json', 'engine/factions/saltmarch.json', 'engine/arcs/saltmarch.json'])
    assert not (opened.folder / 'engine').exists()


def test_approving_writes_a_world_dungeon_would_load_and_play(monkeypatch):
    opened = worldgen.new_world('Saltmarch', 'Salt pans owned by a water guild.')
    fake_model(monkeypatch)
    drafts.decide(opened, worldgen.draft_world(opened)['id'], True)
    overview = worlds.overview(opened)
    assert overview['problems'] == []
    assert overview['world']['name'] == 'Saltmarch' and overview['engine'] == {
        'cities': 1, 'travel': 1, 'tiers': 1, 'factions': 1, 'arcs': 1}
    travel = json.loads((opened.folder / 'engine/travel/saltmarch.json').read_text(encoding='utf-8'))
    assert travel['travel'] == 'hex' and travel['wild']['city'] == 'saltmarch-road'
    assert {node['city'] for node in travel['nodes']} == {'saltmarch-road'}
    assert set(travel['camp']) == set(travel['regions']) == {'the-pans', 'the-scarp', 'wilds'}
    scarp = travel['encounters']['the-scarp'][0]['threat']['foe']
    assert scarp == {'name': 'Scarp man', 'count': 2, 'vitality': 10, 'resolve': 10, 'weapon': 1, 'wants': 'kill'}
    assert 20 <= travel['hex_map']['generate']['span'] <= 200
    road = json.loads((opened.folder / 'engine/cities/saltmarch-road.json').read_text(encoding='utf-8'))
    assert {place['id'] for place in road['places']} == {'brinemouth', 'crake-hollow', 'the-gibbet-stone', 'the-wilds'}
    assert road['careers'][0]['id'] == 'pan-raker' and road['names']['year'] == 412
    tiers = json.loads((opened.folder / 'engine/tiers/saltmarch.json').read_text(encoding='utf-8'))
    assert tiers['start'] == '0412-03-02T08:00:00'
    world = json.loads((opened.folder / 'world.json').read_text(encoding='utf-8'))
    assert world['starting_place'] == {'settlement': 'brinemouth'}
    settlements = json.loads((opened.folder / 'settlements.json').read_text(encoding='utf-8'))['settlements']
    assert next(item for item in settlements if item['id'] == 'brinemouth')['faction'] == 'brine-guild'
    # Dungeon's own package reader takes the folder as it is.
    contents = package_files.contents_of(opened)
    assert ('travel', 'saltmarch') in contents['engine'] and packages.validate(contents) == []


def test_a_part_the_format_refuses_is_asked_for_again_with_its_problems(monkeypatch):
    parts = answers()
    broken = copy.deepcopy(parts['outline'])
    broken['routes'] = broken['routes'][:1]  # the Gibbet Stone has no road
    parts['outline'] = [broken, parts['outline']]
    asked = []
    fake_model(monkeypatch, parts, asked)
    worldgen.draft_world(worldgen.new_world('Saltmarch', 'Salt pans.'))
    assert 'These stops have no road to the rest: the-gibbet-stone' in asked[1]


def test_a_text_too_long_for_dungeon_is_refused_in_its_part_and_asked_for_again(monkeypatch):
    parts = answers()
    wordy = copy.deepcopy(parts['people'])
    wordy['climate']['summary'] = 'Cold winds off the peaks. ' * 20  # over Dungeon's 400 characters
    parts['people'] = [wordy, parts['people']]
    asked = []
    fake_model(monkeypatch, parts, asked)
    opened = worldgen.new_world('Saltmarch', 'Salt pans.')
    drafts.decide(opened, worldgen.draft_world(opened)['id'], True)
    refused = asked[2].split('Your last answer was refused')[1]
    assert 'climate' in refused and '400 characters' in refused
    assert worlds.overview(opened)['problems'] == []


def test_factions_must_hold_the_worlds_own_stops(monkeypatch):
    parts = answers()
    stray = copy.deepcopy(parts['play'])
    stray['factions'][0]['holds'] = ['atlantis']
    parts['play'] = [stray, copy.deepcopy(stray)]
    fake_model(monkeypatch, parts)
    with pytest.raises(DomainError, match='holds unknown stops'):
        worldgen.draft_world(worldgen.new_world('Saltmarch', 'Salt pans.'))


def test_town_stops_grow_into_towns_that_copy_the_road_and_keep_the_stops_id(monkeypatch):
    opened = worldgen.new_world('Saltmarch', 'Salt pans owned by a water guild.')
    fake_model(monkeypatch)
    drafts.decide(opened, worldgen.draft_world(opened)['id'], True)
    waiting = worldgen.town_stops(opened)
    assert [stop['id'] for stop in waiting] == ['brinemouth', 'crake-hollow']
    town = written_town('some-other-id')
    town['employers'][0]['careers'] = ['pan-raker']
    monkeypatch.setattr(models, 'complete', lambda system, prompt: json.dumps(town))
    draft = wizard.draft_town(opened, waiting[0]['pitch'], 'Brinemouth', replaces='brinemouth')
    city = draft['entries'][0]
    assert city['id'] == 'brinemouth' and city['era'] == 'medieval' and city['currency']['code'] == 'groat'
    assert {career['id'] for career in city['careers']} >= {'pan-raker'}
    drafts.decide(opened, draft['id'], True)
    travel = json.loads((opened.folder / 'engine/travel/saltmarch.json').read_text(encoding='utf-8'))
    assert next(node for node in travel['nodes'] if node['id'] == 'brinemouth')['city'] == 'brinemouth'
    assert [stop['id'] for stop in worldgen.town_stops(opened)] == ['crake-hollow']
    assert worlds.overview(opened)['problems'] == []


def test_the_screen_makes_a_world_folder_and_drafts_it(monkeypatch, tmp_path):
    client = TestClient(create_app(tmp_path / 'no-dist'))
    made = client.post('/api/worlds/new', json={'name': 'Saltmarch', 'pitch': 'Salt pans.', 'parent': str(tmp_path)})
    assert made.status_code == 200, made.text
    folder = made.json()['folder']
    assert made.json()['overview']['world']['name'] == 'Saltmarch'
    assert client.post('/api/worlds/new', json={'name': 'Saltmarch', 'parent': str(tmp_path)}).status_code == 409
    fake_model(monkeypatch)
    drafted = client.post('/api/worlds/draft', json={'folder': folder, 'size': 'small'})
    assert drafted.status_code == 200, drafted.text
    assert client.post(f"/api/drafts/{drafted.json()['id']}/decide", json={'folder': folder, 'approve': True}).status_code == 200
    stops = client.post('/api/worlds/town-stops', json={'folder': folder}).json()
    assert [stop['name'] for stop in stops] == ['Brinemouth', 'Crake Hollow']
    assert client.post('/api/worlds/draft', json={'folder': folder, 'size': 'huge'}).status_code == 422
