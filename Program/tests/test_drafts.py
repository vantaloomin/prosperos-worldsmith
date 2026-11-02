"""AI drafts: checked like Dungeon would, retried once with the problems, queued, approved or rejected."""
import json

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend

from tests.conftest import make_checkout
from worldsmith import drafts, models, towns, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.saved = {}

    def get_password(self, service, username):
        return self.saved.get((service, username))

    def set_password(self, service, username, password):
        self.saved[(service, username)] = password

    def delete_password(self, service, username):
        self.saved.pop((service, username), None)


@pytest.fixture(autouse=True)
def memory_keyring():
    before = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield
    keyring.set_keyring(before)


@pytest.fixture
def opened(tmp_path):
    return worlds.builtin(make_checkout(tmp_path / 'dungeon'), 'testland')


def place(place_id: str, neighborhood: str = 'the-crossroads') -> dict:
    return {'id': place_id, 'name': 'The Split Barrel', 'kind': 'tavern', 'neighborhood': neighborhood,
            'summary': 'A cooper\'s tavern where the casks leak and nobody minds.', 'cost': '$', 'setting': 'indoor',
            'good_for': ['friends'], 'day_parts': ['evening']}


def answering(monkeypatch, *answers):
    asked = []

    def complete(system, prompt):
        asked.append(prompt)
        return answers[len(asked) - 1]
    monkeypatch.setattr(models, 'complete', complete)
    return asked


def test_a_draft_is_checked_and_queued_without_touching_the_town(opened, monkeypatch):
    asked = answering(monkeypatch, json.dumps([place('split-barrel')]))
    draft = drafts.draft(opened, 'kingswood', 'places', 'a tavern for coopers')
    assert draft['status'] == 'pending' and draft['entries'][0]['id'] == 'split-barrel'
    assert 'a tavern for coopers' in asked[0] and '"Place"' in asked[0]
    city = towns.read(opened, 'kingswood')['parts']['cities']
    assert 'split-barrel' not in {item['id'] for item in city['places']}
    assert [item['id'] for item in drafts.pending(opened)] == [draft['id']]


def test_a_refused_draft_is_retried_once_with_its_problems(opened, monkeypatch):
    asked = answering(monkeypatch, '```json\n' + json.dumps([place('split-barrel', 'nowhere')]) + '\n```',
                      json.dumps([place('split-barrel')]))
    drafts.draft(opened, 'kingswood', 'places', '')
    assert len(asked) == 2 and 'nowhere' in asked[1]


def test_a_draft_that_stays_wrong_is_refused(opened, monkeypatch):
    answering(monkeypatch, json.dumps([place('a', 'nowhere')]), json.dumps([place('a', 'nowhere')]))
    with pytest.raises(DomainError, match='after a retry'):
        drafts.draft(opened, 'kingswood', 'places', '')
    assert drafts.pending(opened) == []


def test_an_answer_that_is_not_json_is_refused(opened, monkeypatch):
    answering(monkeypatch, 'Here are some places you might like!')
    with pytest.raises(DomainError, match='JSON'):
        drafts.draft(opened, 'kingswood', 'places', '')


def test_approving_adds_the_entries_and_can_be_undone(opened, monkeypatch):
    answering(monkeypatch, json.dumps([place('split-barrel')]))
    draft = drafts.draft(opened, 'kingswood', 'places', '')
    edited = [place('split-barrel') | {'name': 'The Leaking Cask'}]
    result = drafts.decide(opened, draft['id'], True, edited)
    names = {item['id']: item['name'] for item in result['town']['parts']['cities']['places']}
    assert names['split-barrel'] == 'The Leaking Cask' and drafts.pending(opened) == []
    with pytest.raises(DomainError):
        drafts.decide(opened, draft['id'], True)
    towns.undo(opened, 'kingswood')
    assert 'split-barrel' not in {item['id'] for item in towns.read(opened, 'kingswood')['parts']['cities']['places']}


def test_rejecting_leaves_the_town_alone(opened, monkeypatch):
    answering(monkeypatch, json.dumps([place('split-barrel')]))
    draft = drafts.draft(opened, 'kingswood', 'places', '')
    assert drafts.decide(opened, draft['id'], False)['draft']['status'] == 'rejected'
    assert towns.read(opened, 'kingswood')['undo'] == []


def test_quests_are_drafted_in_the_shape_of_the_ones_there(opened, monkeypatch):
    towns.save(opened, 'kingswood', 'adventures', {'quests': [{'id': 'old-debt', 'title': 'An old debt'}]})
    asked = answering(monkeypatch, json.dumps([{'id': 'new-debt', 'title': 'A new debt'}]))
    draft = drafts.draft(opened, 'kingswood', 'quests', '')
    assert '"old-debt"' in asked[0] and draft['entries'][0]['id'] == 'new-debt'


def test_model_settings_keep_the_key_in_the_keyring(tmp_path):
    with pytest.raises(DomainError):
        models.configure('openai', base_url='not-a-url')
    shown = models.configure('openai', model='mistral', base_url='http://127.0.0.1:1234/v1/', key='sk-local')
    assert shown == {'provider': 'openai', 'model': 'mistral', 'base_url': 'http://127.0.0.1:1234/v1', 'has_key': True}
    assert 'sk-local' not in (tmp_path / 'home' / 'settings.json').read_text(encoding='utf-8')
    assert models.config()['has_key']


def test_the_api_drafts_lists_and_decides(tmp_path, monkeypatch):
    checkout = make_checkout(tmp_path / 'dungeon')
    answering(monkeypatch, json.dumps([place('split-barrel')]))
    client = TestClient(create_app())
    client.put('/api/settings', json={'dungeon_checkout': str(checkout)})
    made = client.post('/api/drafts', json={'builtin': 'testland', 'town': 'kingswood', 'target': 'places'}).json()
    assert [item['id'] for item in client.post('/api/drafts/pending', json={'builtin': 'testland'}).json()] == [made['id']]
    decided = client.post(f"/api/drafts/{made['id']}/decide", json={'builtin': 'testland', 'approve': True}).json()
    assert decided['draft']['status'] == 'approved'
    assert client.get('/api/models').json()['provider'] == 'anthropic'
