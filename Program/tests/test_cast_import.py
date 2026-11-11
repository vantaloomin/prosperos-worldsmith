"""A Dramatis cast's outer square becomes a draft of the world's factions, approved and undone like any other draft."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_checkout, make_world
from worldsmith import cast_import, drafts, models, worldgen, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.main import create_app


def corner(key: str, label: str, stance: str, **more) -> dict:
    return {'id': key, 'label': label, 'stance': stance, 'tags': [], 'role': '', 'fields': {}, 'character_id': None,
            'note': '', 'depth': 'single', 'inner': None} | more


def cast_file(outer: list[dict], resonance: list[dict] | None = None, characters: dict | None = None) -> dict:
    """A cast as Dramatis's cast.json export writes it (dramatis/casts.py export)."""
    cast = {'title': 'The Salt War', 'theme': 'Is order worth what it costs?', 'genre': 'political-fantasy',
            'group': '', 'outer': {'axis': {'kind': 'value', 'label': 'What keeps people safe'}, 'question': '',
                                   'corners': outer},
            'resonance': resonance or [], 'relationships': [], 'focus_id': None}
    return {'format': 'prospero-cast', 'version': 1, 'cast': cast, 'characters': characters or {}}


def four_sides() -> dict:
    split = {'axis': {'kind': 'means', 'label': 'How to keep order'}, 'question': 'How hard may the law bite?',
             'corners': [corner('zealot', 'Zealot', 'by the noose', character_id='c-hale'),
                         corner('pragmatist', 'Pragmatist', 'through bribes and quiet deals', character_id='c-wren',
                                tags=['bribery']),
                         corner('reformer', 'Reformer', 'by writing fairer laws')]}
    outer = [corner('order', 'The Order', 'Order keeps people alive', note='They hold the bridges.', depth='full',
                    inner=split),
             corner('free', 'Free Towns', 'Freedom is worth the blood', character_id='c-ash', tags=['bribery']),
             corner('faith', 'The Lantern Faith', 'Only the gods judge'),
             corner('coin', 'Timber Guild', 'Money settles everything')]
    resonance = [{'a': 'pragmatist', 'b': 'free', 'on': 'bribery', 'role': 'double-agent', 'status': 'confirmed',
                  'note': ''},
                 {'a': 'reformer', 'b': 'faith', 'on': 'law', 'role': '', 'status': 'dismissed', 'note': ''}]
    characters = {'c-hale': {'name': 'Captain Hale'}, 'c-wren': {'name': 'Wren Abbot'}, 'c-ash': {'name': 'Ash'}}
    return cast_file(outer, resonance, characters)


def written(prompt: str, holds: str = 'kingswood', clocks: int = 2) -> str:
    """The model's answer: a faction for each id the prompt gives, with its own (overwritten) name and goals."""
    ids = re.findall(r'^\{"id": "([a-z0-9-]+)"', prompt, re.M)
    factions = [{'id': key, 'name': 'Renamed by the model', 'kind': 'order', 'tier': 2, 'summary': 'The model says.',
                 'goals': ['A goal of its own'], 'holds': [holds], 'rivals': [],
                 'clocks': [{'id': f'clock-{at}', 'name': f'Clock {at}', 'segments': 4, 'done': 'It happens.'}
                            for at in range(clocks)],
                 'jobs': [{'id': f'{key}-job', 'title': 'A job', 'days': 3, 'wages': 2, 'standing': 1,
                           'giver': 'someone', 'hook': 'Work.', 'truth': 'The real reason.',
                           'missed': 'It goes badly.'}]}
                for key in ids]
    return 'Here they are:\n' + json.dumps({'factions': factions})


@pytest.fixture
def checkout(tmp_path):
    return make_checkout(tmp_path / 'dungeon')


@pytest.fixture
def model(monkeypatch):
    asked = []
    monkeypatch.setattr(models, 'complete', lambda system, prompt: asked.append((system, prompt)) or written(prompt))
    return asked


def test_a_four_corner_cast_becomes_four_valid_factions_and_nothing_is_written_until_approved(checkout, model):
    opened = worlds.builtin(checkout, 'testland')
    draft = cast_import.draft(opened, four_sides())
    entry = draft['entries'][0]
    factions = {item['id']: item for item in entry['factions']}
    assert draft['target'] == 'factions' and draft['town'] == 'testland' and entry['cast'] == 'The Salt War'
    assert list(factions) == ['the-order', 'free-towns', 'the-lantern-faith', 'timber-guild-2']
    order = factions['the-order']
    assert order['name'] == 'The Order' and order['summary'] == 'Order keeps people alive. They hold the bridges.'
    assert order['goals'] == ['Order keeps people alive', 'Zealot pushes for it by the noose',
                              'Pragmatist pushes for it through bribes and quiet deals',
                              'Reformer pushes for it by writing fairer laws']
    assert order['rivals'] == ['free-towns', 'the-lantern-faith', 'timber-guild-2'] and order['allies'] == []
    assert order['jobs'][0]['truth'].startswith('Wren Abbot quietly deals with Ash. ')
    assert all('quietly' not in job['truth'] for item in entry['factions'][1:] for job in item['jobs'])
    assert all(worldgen.Faction.model_validate(item) for item in entry['factions'])
    system, prompt = model[0]
    assert system != worldgen.SYSTEM and 'Is order worth what it costs?' in prompt
    assert 'Captain Hale, Wren Abbot' in prompt and 'kingswood (kingswood); mile-post (mile-post)' in prompt
    assert 'The Timber Guild (timber-guild)' in prompt
    assert not (checkout / worlds.DATA / 'factions' / 'testland.json').exists()


def test_a_taken_id_gets_a_number_and_the_world_keeps_its_own_faction(checkout, model):
    opened = worlds.builtin(checkout, 'testland')
    entry = cast_import.draft(opened, four_sides())['entries'][0]
    # Timber Guild slugs to timber-guild, which the world's section already has.
    assert [item['id'] for item in entry['factions']][3] == 'timber-guild-2'


def test_a_single_corner_side_stays_one_faction(checkout, model):
    opened = worlds.builtin(checkout, 'testland')
    split = {'axis': {'kind': 'means'}, 'question': '', 'corners': [corner('hawk', 'Hawk', 'by force'),
                                                                   corner('dove', 'Dove', 'by talks')]}
    bundle = cast_file([corner('crown', 'The Crown', 'The throne first'),
                        corner('rebels', 'The Rebels', 'No more kings', depth='partial', inner=split)])
    factions = cast_import.draft(opened, bundle)['entries'][0]['factions']
    assert [item['name'] for item in factions] == ['The Crown', 'The Rebels']
    assert factions[0]['goals'] == ['The throne first']
    assert factions[1]['goals'] == ['No more kings', 'Hawk pushes for it by force', 'Dove pushes for it by talks']


def test_approving_adds_to_the_section_and_the_factions_in_play_and_one_undo_takes_both_back(checkout, model):
    opened = worlds.builtin(checkout, 'testland')
    section_path = opened.folder / 'factions.json'
    engine_path = checkout / worlds.DATA / 'factions' / 'testland.json'
    before = section_path.read_text(encoding='utf-8')
    draft = cast_import.draft(opened, four_sides())
    drafts.decide(opened, draft['id'], True)
    section = json.loads(section_path.read_text(encoding='utf-8'))['factions']
    assert [item['id'] for item in section] == ['timber-guild', 'the-order', 'free-towns', 'the-lantern-faith',
                                                'timber-guild-2']
    assert section[1] == {'id': 'the-order', 'name': 'The Order', 'kind': 'order',
                          'summary': 'Order keeps people alive. They hold the bridges.',
                          'goals': draft['entries'][0]['factions'][0]['goals']}
    engine = json.loads(engine_path.read_text(encoding='utf-8'))
    assert engine['world'] == 'testland' and len(engine['factions']) == 4
    assert engine['factions'][0]['holds'] == ['kingswood'] and len(engine['factions'][0]['clocks']) == 2
    found, problems = worlds.contents(opened)
    assert problems == [] and packages.validate(found) == []
    assert len(cast_import.imports(opened)) == 1
    cast_import.undo(opened)
    assert section_path.read_text(encoding='utf-8') == before and not engine_path.exists()
    assert cast_import.imports(opened) == []
    with pytest.raises(DomainError, match='no cast import to undo'):
        cast_import.undo(opened)


def test_a_world_without_a_factions_section_refuses_the_draft_plainly(tmp_path, model):
    folder = make_world(tmp_path / 'testland')
    (folder / 'factions.json').unlink()
    (folder / 'cast.json').unlink()  # its people name a faction, which is a problem of its own here
    with pytest.raises(DomainError, match=r'no factions section \(factions\.json\)'):
        cast_import.draft(worlds.folder(folder), four_sides())
    assert model == []


@pytest.mark.parametrize(('raw', 'words'), [
    ({'name': 'A character card'}, 'not a Dramatis cast file'),
    (four_sides() | {'version': 2}, 'version 2, and this Worldsmith reads version 1'),
    (four_sides() | {'cast': {'title': 'Broken', 'outer': {'corners': []}}}, 'damaged at cast > outer > corners'),
])
def test_a_file_that_is_not_a_cast_says_why(checkout, model, raw, words):
    with pytest.raises(DomainError, match=words):
        cast_import.draft(worlds.builtin(checkout, 'testland'), raw)
    assert model == []


def test_factions_that_hold_unknown_stops_or_miss_a_clock_are_asked_for_again(checkout, monkeypatch):
    answers = [lambda prompt: written(prompt, holds='atlantis', clocks=1), written]
    asked = []
    monkeypatch.setattr(models, 'complete', lambda system, prompt: asked.append(prompt) or answers.pop(0)(prompt))
    draft = cast_import.draft(worlds.builtin(checkout, 'testland'), four_sides())
    assert len(asked) == 2 and "holds unknown stops ['atlantis']" in asked[1] and 'exactly 2 clocks' in asked[1]
    assert all(item['holds'] == ['kingswood'] for item in draft['entries'][0]['factions'])
    monkeypatch.setattr(models, 'complete', lambda system, prompt: written(prompt, holds='atlantis'))
    with pytest.raises(DomainError, match='still had problems after a retry'):
        cast_import.draft(worlds.builtin(checkout, 'testland'), four_sides())


def test_a_draft_whose_ids_were_taken_meanwhile_is_refused(checkout, model):
    opened = worlds.builtin(checkout, 'testland')
    first, second = cast_import.draft(opened, four_sides()), cast_import.draft(opened, four_sides())
    drafts.decide(opened, first['id'], True)
    with pytest.raises(DomainError, match='has gained free-towns, the-lantern-faith, the-order'):
        drafts.decide(opened, second['id'], True)


def test_the_screen_imports_approves_and_undoes_a_cast(tmp_path, checkout, model, monkeypatch):
    monkeypatch.setenv('WORLDSMITH_HOME', str(tmp_path / 'home'))
    client = TestClient(create_app(tmp_path / 'no-dist'))
    client.put('/api/settings', json={'dungeon_checkout': str(checkout)})
    world = {'builtin': 'testland'}
    draft = client.post('/api/factions/import', json=world | {'cast': four_sides()}).json()
    assert draft['target'] == 'factions'
    assert client.post('/api/factions/import', json=world | {'cast': {'format': 'other'}}).status_code == 422
    client.post(f"/api/drafts/{draft['id']}/decide", json=world | {'approve': True}).raise_for_status()
    assert len(client.post('/api/factions/imports', json=world).json()) == 1
    overview = client.post('/api/factions/undo', json=world).json()
    assert overview['sections']['factions']['entries'] == 1
    assert client.post('/api/factions/imports', json=world).json() == []


def notables_for(prompt: str, drop: str = '') -> str:
    """The model's notables: one for each person the ask lists, at a Kingswood place."""
    names = [line[2:].split(';')[0] for line in prompt.splitlines() if line.startswith('- ') and '; pronouns ' in line]
    return json.dumps([{'id': re.sub(r'[^a-z]+', '-', name.lower()).strip('-'), 'name': name, 'pronouns': 'they/them',
                        'age': 40, 'place': 'felled-oak', 'role': 'regular, with the Order', 'about': 'From the cast.',
                        'source': 'curated-2026-10'} for name in names if name != drop])


def test_with_a_town_the_casts_people_become_its_notables_in_a_second_draft(checkout, monkeypatch):
    asked = []

    def answer(system, prompt):
        asked.append(prompt)
        if system == drafts.SYSTEM:
            return notables_for(prompt, drop='Ash' if len(asked) == 2 else '')
        return written(prompt)

    monkeypatch.setattr(models, 'complete', answer)
    bundle = four_sides()
    bundle['characters']['c-hale'] |= {'gender': 'man', 'age': 51, 'about': 'Hangs smugglers.', 'wants': 'A clean bridge.'}
    opened = worlds.builtin(checkout, 'testland')
    draft = cast_import.draft(opened, bundle, 'kingswood')
    assert draft['target'] == 'factions'
    people = draft['people']
    assert people['target'] == 'notables' and people['town'] == 'kingswood'
    assert [entry['name'] for entry in people['entries']] == ['Captain Hale', 'Wren Abbot', 'Ash']
    ask = asked[1]
    assert '- Captain Hale; pronouns he/him; age 51; stands with The Order, as Zealot (by the noose); about: Hangs ' \
           'smugglers.; wants: A clean bridge.' in ask
    assert '- Ash; pronouns they/them; age not given' in ask and 'stands with Free Towns (' in ask
    assert 'Ash is missing; keep their name exactly as written.' in asked[2]  # The first answer left Ash out.
    assert not (checkout / worlds.DATA / 'cities' / 'kingswood.json').read_text().count('Captain Hale')

    without = cast_import.draft(opened, four_sides())
    assert 'people' not in without
    with pytest.raises(DomainError, match='That town is not in this world.'):
        cast_import.draft(opened, four_sides(), 'atlantis')


def test_people_that_cannot_be_drafted_leave_the_factions_queued(checkout, monkeypatch):
    monkeypatch.setattr(models, 'complete', lambda system, prompt: notables_for(prompt, drop='Ash')
                        if system == drafts.SYSTEM else written(prompt))
    draft = cast_import.draft(worlds.builtin(checkout, 'testland'), four_sides(), 'kingswood')
    assert draft['target'] == 'factions' and draft['people'] is None
    assert 'Ash is missing' in draft['people_problem']
