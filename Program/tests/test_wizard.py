"""The new town wizard: a pitch becomes a whole checked town, approved onto the travel map, undone in one step."""
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import kingswood, make_checkout
from worldsmith import drafts, models, towns, wizard, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


def written_town(town_id: str = 'oakhollow') -> dict:
    city = kingswood()
    keep = {key: city[key] for key in wizard.WRITTEN if key in city}
    keep |= {'id': town_id, 'name': 'Oakhollow', 'summary': 'A charcoal-burners\' village gone sour on debt.'}
    for item in keep['places'] + keep['neighborhoods'] + keep['notables']:
        item.pop('source', None)
    keep['employers'][0]['careers'] = ['dragon-tamer']  # not a career Dungeon knows here: pruned
    keep['neighborhoods'][0]['transit'] = ['ghost-ferry']  # a line the town never defines: pruned
    keep['careers'] = []  # the employers' careers are Kingswood's own: copied into the new town
    return keep


@pytest.fixture
def checkout(tmp_path):
    return make_checkout(tmp_path / 'dungeon')


def test_a_pitch_becomes_a_checked_town_draft_that_shares_the_worlds_settings(checkout, monkeypatch):
    opened = worlds.builtin(checkout, 'testland')
    asked = []
    monkeypatch.setattr(models, 'complete', lambda system, prompt: asked.append(prompt) or
                        'Here it is:\n' + json.dumps(written_town()))
    draft = wizard.draft_town(opened, 'charcoal burners in debt', near='kingswood', hours=5, terrain='a cart track')
    city = draft['entries'][0]
    assert draft['target'] == 'town' and draft['town'] == 'oakhollow'
    assert city['currency'] == kingswood()['currency'] and city['sources'].keys() == {'worldsmith'}
    assert all(place['source'] == 'worldsmith' for place in city['places'])
    assert all('dragon-tamer' not in employer['careers'] for employer in city['employers'])
    assert 'ghost-ferry' not in city['neighborhoods'][0]['transit']
    hired = {career for employer in city['employers'] for career in employer['careers']}
    assert hired and hired <= {career['id'] for career in city['careers']}
    assert 'charcoal burners in debt' in asked[0] and '"neighborhoods"' in asked[0]
    assert not (checkout / worlds.DATA / 'cities' / 'oakhollow.json').exists()


def test_approving_writes_the_town_and_its_road_and_one_undo_takes_both_back(checkout, monkeypatch):
    opened = worlds.builtin(checkout, 'testland')
    monkeypatch.setattr(models, 'complete', lambda system, prompt: json.dumps(written_town()))
    draft = wizard.draft_town(opened, 'charcoal burners', near='kingswood', hours=5, terrain='a cart track')
    travel_path = checkout / worlds.DATA / 'travel' / 'testland.json'
    before = travel_path.read_text(encoding='utf-8')
    drafts.decide(opened, draft['id'], True)
    travel = json.loads(travel_path.read_text(encoding='utf-8'))
    assert {'from': 'kingswood', 'to': 'oakhollow', 'hours': 5, 'terrain': 'a cart track', 'danger': 'low'} in travel['routes']
    assert any(node['city'] == 'oakhollow' for node in travel['nodes'])
    assert 'oakhollow' in {town['id'] for town in worlds.overview(opened)['towns']}
    assert towns.undo(opened, 'oakhollow')['gone']
    assert travel_path.read_text(encoding='utf-8') == before
    assert not (checkout / worlds.DATA / 'cities' / 'oakhollow.json').exists()


def test_a_roadside_stop_can_become_the_new_town(checkout, monkeypatch):
    opened = worlds.builtin(checkout, 'testland')
    monkeypatch.setattr(models, 'complete', lambda system, prompt: json.dumps(written_town()))
    draft = wizard.draft_town(opened, 'the mile post grows into a village', replaces='mile-post')
    drafts.decide(opened, draft['id'], True)
    nodes = json.loads((checkout / worlds.DATA / 'travel' / 'testland.json').read_text(encoding='utf-8'))['nodes']
    # The town keeps the stop's id, so whatever names the stop (factions' holds, a starting place) still finds it.
    assert next(node for node in nodes if node['id'] == 'mile-post')['city'] == 'mile-post'
    assert (checkout / worlds.DATA / 'cities' / 'mile-post.json').is_file()


def test_a_town_id_that_is_taken_is_retried_then_refused(checkout, monkeypatch):
    opened = worlds.builtin(checkout, 'testland')
    monkeypatch.setattr(models, 'complete', lambda system, prompt: json.dumps(written_town('kingswood')))
    with pytest.raises(DomainError, match='already a town'):
        wizard.draft_town(opened, 'another kingswood')


def test_a_pitch_is_needed(checkout):
    with pytest.raises(DomainError):
        wizard.draft_town(worlds.builtin(checkout, 'testland'), '  ')


def test_the_overview_lists_travel_stops_and_the_api_drafts_a_town(checkout, monkeypatch):
    monkeypatch.setattr(models, 'complete', lambda system, prompt: json.dumps(written_town()))
    client = TestClient(create_app())
    client.put('/api/settings', json={'dungeon_checkout': str(checkout)})
    overview = client.post('/api/worlds/open', json={'builtin': 'testland'}).json()
    assert {'id': 'mile-post', 'name': None, 'city': 'testland-road', 'road': True} in overview['stops']
    made = client.post('/api/towns/new', json={'builtin': 'testland', 'pitch': 'charcoal burners'}).json()
    assert made['target'] == 'town'
