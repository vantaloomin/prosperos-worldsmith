"""Names from Dungeon's own tables (worldsmith/names.py): towns draw on its banks, the wizards pick a bank and mix and
refuse names that read as made up, and the Names tab previews a town's spread."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout
from tests.test_wizard import written_town
from tests.test_worldgen import answers, fake_model
from worldsmith import models, names, wizard, worldgen, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


def test_the_tables_are_dungeons_and_a_town_draws_on_its_eras_bank_by_default():
    assert {'modern', 'medieval', 'victorian', 'storybook'} <= set(names.banks())
    groups, mix = names.groups_for({'era': 'medieval'})
    assert set(mix) == {'english', 'norman', 'welsh'} and mix['english'] > mix['welsh']
    spread = names.spread({'era': 'medieval'})
    assert spread['bank'] == 'medieval' and spread['given'] > 300 and spread['family'] > 200
    drawn = names.sample({'era': 'medieval'}, 12, 'a')
    assert len(drawn) == 12 and len({item['name'] for item in drawn}) > 8
    known = {name for group in groups.values() for name in group['family']}
    assert all(any(item['name'].endswith(' ' + family) for family in known) for item in drawn)
    assert names.sample({'era': 'medieval'}, 12, 'a') == drawn  # the same seed, the same names


def test_a_towns_own_mix_and_groups_weigh_in_like_dungeons():
    city = {'era': 'fantasy', 'names': {'bank': 'medieval', 'mix': {'welsh': 1, 'fen-folk': 3},
                                        'groups': {'fen-folk': {'feminine': ['Agnes'], 'family': ['Reed']}}}}
    groups, mix = names.groups_for(city)
    assert mix == {'welsh': 1, 'fen-folk': 3} and 'english' in groups
    assert {group['id']: group['own'] for group in names.spread(city)['groups']} == {'welsh': False, 'fen-folk': True}


def test_made_up_names_are_flagged_and_real_ones_are_not():
    assert names.invented_in('Elara Voss', 'Kaelith Ravencrest') == ['Elara', 'Voss', 'Kaelith', 'Ravencrest']
    assert names.invented_in('Agnes Brill', 'Dunstan Coe', 'Wat Hobb') == []


def test_the_world_wizard_asks_for_a_bank_and_refuses_a_thin_or_made_up_group(monkeypatch):
    parts = answers()
    thin = copy.deepcopy(parts['people'])
    thin['names'] = {'bank': 'medieval', 'mix': {'english': 1, 'gull-folk': 1},
                     'groups': {'gull-folk': {'feminine': ['Elara', 'Brin'], 'family': ['Voss']}}}
    parts['people'] = [thin, parts['people']]
    asked = []
    fake_model(monkeypatch, parts, asked)
    opened = worldgen.new_world('Saltmarch', 'Salt pans.')
    draft = worldgen.draft_world(opened)
    people_asks = [prompt for prompt in asked if 'Write the people' in prompt]
    assert 'medieval (the era default)' in people_asks[0] and 'storybook' in people_asks[0]
    assert 'names.groups.gull-folk needs at least 30 given and 20 family names' in people_asks[1]
    assert 'read as made up: Elara, Voss' in people_asks[1]
    road = draft['entries'][0]['files']['engine/cities/saltmarch-road.json']
    assert road['names']['bank'] == 'medieval' and road['names']['mix'] == {'english': 6, 'norman': 2, 'welsh': 1}


def test_an_unknown_bank_is_refused(monkeypatch):
    parts = answers()
    parts['people']['names'] = {'bank': 'elvish', 'mix': {}}
    fake_model(monkeypatch, parts)
    with pytest.raises(DomainError, match="names.bank 'elvish' is not one of the banks"):
        worldgen.draft_world(worldgen.new_world('Saltmarch', 'Salt pans.'))


def test_the_town_wizard_shows_the_worlds_names_and_refuses_made_up_notables(tmp_path, monkeypatch):
    opened = worlds.builtin(make_checkout(tmp_path / 'dungeon'), 'testland')
    made_up = written_town()
    made_up['notables'][0]['name'] = 'Elara Duskwhisper'
    answers_, asked = [made_up, written_town()], []
    monkeypatch.setattr(models, 'complete', lambda system, prompt: asked.append(prompt) or json.dumps(answers_.pop(0)))
    wizard.draft_town(opened, 'charcoal burners', near='kingswood')
    assert 'People here are named like this' in asked[0]
    assert "notables' names read as made up by a model: Elara, Duskwhisper" in asked[1]


def test_the_names_tab_previews_a_towns_spread(tmp_path):
    client = TestClient(create_app(tmp_path / 'no-dist'))
    shown = client.post('/api/names/view', json={'era': 'victorian', 'seed': '3'})
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert body['era_bank'] == 'victorian' and 'english' in body['banks']['victorian']
    assert body['spread']['bank'] == 'victorian' and len(body['samples']) == 12
    other = client.post('/api/names/view', json={'era': 'victorian', 'names': {'bank': 'ottoman'}}).json()
    assert other['spread']['bank'] == 'ottoman' and {group['id'] for group in other['spread']['groups']} >= {'turkish'}


def test_a_towns_peoples_live_there_by_their_share_and_take_their_own_names():
    city = {'era': 'medieval', 'kinds': {'dwarf': {'share': 0.3}, 'wolf-kin': {'share': 0.2}}}
    assert names.shares(city) == {'dwarf': 0.3, 'wolf-kin': 0.2}
    drawn = names.sample(city, 40, 'p')
    kinds = {item['kind'] for item in drawn}
    assert kinds == {None, 'Dwarf', 'Wolf-kin'}
    dwarf_names = names.banks()['peoples']['dwarf']['family']
    assert all(item['name'].split(' ', 1)[1] in dwarf_names for item in drawn if item['kind'] == 'Dwarf')
    # A people listed with share 0 (Haven's hidden folk) brings nobody; with no shares anywhere, Dungeon's default.
    assert names.shares({'era': 'modern', 'kinds': {'fae': {'lifespan': 700, 'share': 0}}}) == {}
    assert names.shares({'era': 'modern', 'kinds': {'gnome': {}}}) == {'gnome': names.DEFAULT_SHARE}


def test_the_names_tab_lists_the_peoples_and_the_towns_shares(tmp_path):
    client = TestClient(create_app(tmp_path / 'no-dist'))
    body = client.post('/api/names/view', json={'era': 'fantasy', 'kinds': {'oni': {'share': 0.5}}}).json()
    ids = {item['id'] for item in body['peoples']}
    assert {'wolf-kin', 'high-elf', 'dwarf', 'orc', 'oni', 'mind-eater', 'clockwork-folk'} <= ids and len(ids) >= 75
    assert body['shares'] == {'oni': 0.5} and 'peoples' not in body['banks']
    assert {item['folk'] for item in body['peoples']} == {'Beastkin', 'Fantasy humanoids', 'Other peoples'}


def test_the_world_wizard_offers_the_peoples_and_refuses_a_bad_share(monkeypatch):
    parts = answers()
    bad = copy.deepcopy(parts['people'])
    bad['kinds'] = {'dwarf': {'share': 0.9}, 'wolf-kin': {'share': 0.4}, 'gloop': {'share': 0.1}}
    good = copy.deepcopy(parts['people'])
    good['kinds'] = {'dwarf': {'share': 0.1}, 'fox-kin': {'share': 0.05}}
    parts['people'] = [bad, good]
    asked = []
    fake_model(monkeypatch, parts, asked)
    draft = worldgen.draft_world(worldgen.new_world('Saltmarch', 'Salt pans.'))
    people_asks = [prompt for prompt in asked if 'Write the people' in prompt]
    assert 'Beastkin, Canids: wolf-kin (70y)' in people_asks[0]
    assert 'kinds.gloop is not one of the peoples' in people_asks[1] and 'add up to 1.4' in people_asks[1]
    road = draft['entries'][0]['files']['engine/cities/saltmarch-road.json']
    assert road['kinds'] == {'dwarf': {'share': 0.1}, 'fox-kin': {'share': 0.05}}
