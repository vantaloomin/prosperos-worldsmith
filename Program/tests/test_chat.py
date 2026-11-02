"""The brainstorm chat: world-aware, kept per world, and only ever proposing drafts."""
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout
from worldsmith import chat, models, towns, worlds
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


@pytest.fixture
def opened(tmp_path):
    return worlds.builtin(make_checkout(tmp_path / 'dungeon'), 'testland')


def test_the_chat_knows_the_world_and_proposes_drafts_without_changing_anything(opened, monkeypatch):
    asked = []

    def complete(system, prompt):
        asked.append((system, prompt))
        return ('A cooper who waters the ale for the Guild.\n'
                '<draft town="kingswood" target="notables">A cooper in debt to the\n Timber Guild</draft>')
    monkeypatch.setattr(models, 'complete', complete)
    before = towns.read(opened, 'kingswood')['parts']['cities']
    turns = chat.say(opened, 'Who runs the ale?', 'kingswood')
    system, prompt = asked[0]
    assert 'The Timber Guild' in prompt and 'Kingswood' in prompt and 'notables' in system
    assert [turn['role'] for turn in turns] == ['user', 'assistant']
    assert turns[1]['text'] == 'A cooper who waters the ale for the Guild.'
    assert turns[1]['proposals'] == [{'town': 'kingswood', 'target': 'notables', 'ask': 'A cooper in debt to the Timber Guild'}]
    assert towns.read(opened, 'kingswood')['parts']['cities'] == before


def test_the_conversation_carries_on_and_can_be_cleared(opened, monkeypatch):
    prompts = []
    monkeypatch.setattr(models, 'complete', lambda system, prompt: prompts.append(prompt) or 'Noted.')
    chat.say(opened, 'The mill burns in autumn.')
    chat.say(opened, 'Who set the fire?')
    assert 'The mill burns in autumn.' in prompts[1]
    assert len(chat.history(opened)) == 4
    assert chat.clear(opened) == [] and chat.history(opened) == []


def test_an_empty_message_is_refused(opened):
    with pytest.raises(DomainError):
        chat.say(opened, '   ')


def test_the_chat_api(tmp_path, monkeypatch):
    checkout = make_checkout(tmp_path / 'dungeon')
    monkeypatch.setattr(models, 'complete', lambda system, prompt: 'Hello.')
    client = TestClient(create_app())
    client.put('/api/settings', json={'dungeon_checkout': str(checkout)})
    said = client.post('/api/chat/say', json={'builtin': 'testland', 'message': 'Hi', 'town': 'kingswood'}).json()
    assert said[-1]['text'] == 'Hello.'
    assert len(client.post('/api/chat', json={'builtin': 'testland'}).json()) == 2
    assert client.post('/api/chat/clear', json={'builtin': 'testland'}).json() == []
