"""AI drafts: the model proposes new entries for a town, and nothing lands until the author approves them.

A draft asks for new entries in one part of a town: a list in its city file (places, notables, neighborhoods...) or
its quests. The prompt carries the world's pitch and the town as it stands, Dungeon's schema for the entries, and
the house rules for names and tone. What comes back is checked the way Dungeon would check it, once more with the
problems if it fails, and queued. Approving adds the entries to the town's file as it is then, through
worldsmith.towns, so it is checked again and can be undone like any other save.
"""
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from worldsmith import models, progress, towns, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError, require
from worldsmith.dungeon_format.schema import City

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, folder TEXT NOT NULL, town TEXT NOT NULL,
  target TEXT NOT NULL, ask TEXT NOT NULL, entries TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending');
"""
CITY_TARGETS = ('neighborhoods', 'places', 'notables', 'employers', 'careers', 'prices', 'local_color',
                'annual_events', 'transit', 'career_hubs')
# Draftable lists outside the city file: target -> (town part, key of its list).
OTHER_TARGETS = {'quests': ('adventures', 'quests'), 'dangers': ('adventures', 'dangers'),
                 'premades': ('premades', 'premades'), 'items': ('items', 'items')}
MOST_ENTRIES = 12
SYSTEM = """You help an author build worlds for Prospero's Dungeon, a text roleplaying game for consenting adults:
dark, morally complex stories where good outcomes are not guaranteed. You write new entries for one town, in the
exact JSON shape asked for, fitting the world's tone, era and existing people and places.

Names: original and grounded in the setting. Avoid names and words that read as AI cliches (Voss, Maren,
Thorne, Elara, Kael, "Drowned Lamp", "whispering", "tapestry", "testament", "palpable", "nestled").
Give people wants, debts and secrets; let places be lived in and specific. Keep ids lowercase-with-hyphens.

Answer with only a JSON array of the new entries: no commentary, no code fences."""


def connect() -> sqlite3.Connection:
    connection = towns.history()
    connection.executescript(SCHEMA)
    return connection


def part_of(target: str) -> tuple[str, str]:
    if target == 'town':
        return 'cities', 'town'
    if target in CITY_TARGETS:
        return 'cities', target
    require(target in OTHER_TARGETS, f'{target} cannot be drafted.', 404)
    return OTHER_TARGETS[target]


def entry_schema(target: str) -> dict | None:
    """Dungeon's JSON schema for one entry of a city list, with the definitions it uses; None outside the city."""
    if target not in CITY_TARGETS:
        return None
    full = City.model_json_schema()
    item = full['properties'][target]['items']
    wanted, found = [item['$ref'].split('/')[-1]], {}
    while wanted:
        name = wanted.pop()
        if name in found:
            continue
        found[name] = full['$defs'][name]
        wanted += re.findall(r'#/\$defs/(\w+)', json.dumps(found[name]))
    return {'entry': item, '$defs': found}


def brief(entry: dict) -> str:
    named = entry.get('name') or entry.get('title') or entry.get('item') or entry.get('id')
    about = entry.get('summary') or entry.get('about') or entry.get('hook') or ''
    return f"- {entry.get('id', '')}: {named}" + (f' ({about[:140]})' if about else '')


def prompt_for(found: dict, city: dict, target: str, current: list, ask: str, problems: list[str],
               shape: list | None = None) -> str:
    world = found['world']
    lines = [f"World: {world.get('name')} ({world.get('genre', '')}). {world.get('pitch', '')}",
             f"Town: {city.get('name')} ({city.get('era')}, money in {(city.get('currency') or {}).get('name', '')}). "
             f"{city.get('summary', '')}",
             'Neighborhoods: ' + ', '.join(f"{hood['id']} ({hood.get('name')})" for hood in city.get('neighborhoods', [])),
             'Places: ' + ', '.join(place['id'] for place in city.get('places', [])),
             'Sources (cite one in each entry\'s "source"): ' + ', '.join(city.get('sources', {})),
             f'\nThe town\'s {target} so far:']
    lines += [brief(entry) for entry in current[:60] if isinstance(entry, dict)] or ['(none)']
    schema = entry_schema(target)
    if schema:
        lines += ['\nEach new entry must match this JSON schema (Dungeon refuses anything else):', json.dumps(schema)]
    elif shape or current:
        lines += ['\nMatch the shape of this existing entry exactly:', json.dumps((shape or current)[0], ensure_ascii=False)]
    lines += [f'\nWrite new {target} for this town. The author asks: {ask.strip() or "a few more that fit"}',
              f'At most {MOST_ENTRIES}. Use new ids that are not taken. Reference only neighborhoods and places '
              'listed above.']
    if problems:
        lines += ['\nYour last answer was refused for these problems; fix them:', *problems[:20]]
    return '\n'.join(lines)


def example_from(found: dict, kind: str, key: str) -> list:
    """Entries of the same kind from another town in the world, as the shape for a town that has none yet."""
    for (each, _), data in sorted(found['engine'].items()):
        if each == kind and isinstance(data, dict) and data.get(key):
            return list(data[key])
    return []


def parsed(text: str) -> list:
    """The first JSON list of objects in the model's answer, whatever prose or fences surround it."""
    decoder, error = json.JSONDecoder(), None
    for start in [match.start() for match in re.finditer(r'\[', text)]:
        try:
            entries, _ = decoder.raw_decode(text, start)
        except ValueError as failure:
            error = error or failure
            continue
        if isinstance(entries, list) and entries and all(isinstance(entry, dict) for entry in entries):
            return entries[:MOST_ENTRIES]
    require(error is None, f'The model\'s answer was not valid JSON: {error}', 502)
    raise DomainError('The model did not answer with a JSON list of entries.', 502)


def merged(files: dict, target: str, entries: list) -> tuple[str, dict, list[str]]:
    """The town file with the new entries added, and what Dungeon would refuse in it."""
    kind, key = part_of(target)
    data = dict(files['parts'][kind] or {})
    current = list(data.get(key) or [])
    if kind == 'cities':
        source = next(iter(data.get('sources') or {}), None)
        entries = [entry if 'source' in entry or not source else entry | {'source': source} for entry in entries]
    taken = {entry.get('id') for entry in current if isinstance(entry, dict)}
    clashes = sorted(str(entry.get('id')) for entry in entries if entry.get('id') in taken)
    data[key] = current + entries
    problems = [f'{target} already has {", ".join(clashes)}'] if clashes else []
    return kind, data, problems + towns.problems_in(kind, data)


def draft(opened: worlds.Opened, town: str, target: str, ask: str) -> dict:
    kind, key = part_of(target)
    files = towns.read(opened, town)
    found, _ = worlds.contents(opened)
    current = list((files['parts'][kind] or {}).get(key) or [])
    shape = current or example_from(found, kind, key)
    problems: list[str] = []
    with progress.tracked(opened, 'draft', target):
        for attempt in (1, 2):
            progress.report(opened, 'draft', 'write', attempt, problems)
            entries = parsed(models.complete(SYSTEM, prompt_for(found, files['parts']['cities'], target, current, ask,
                                                                problems, shape)))
            progress.report(opened, 'draft', 'check', attempt)
            _, _, problems = merged(files, target, entries)
            if not problems:
                break
        else:
            raise DomainError('The model\'s draft still had problems after a retry: ' + '; '.join(problems[:6]), 422)
        return queue(opened, town, target, ask, entries)


def queue(opened: worlds.Opened, town: str, target: str, ask: str, entries: list) -> dict:
    with closing(connect()) as connection, connection:
        cursor = connection.execute(
            'INSERT INTO drafts (at, folder, town, target, ask, entries) VALUES (?, ?, ?, ?, ?, ?)',
            (now(), str(opened.folder), town, target, ask, json.dumps(entries, ensure_ascii=False)))
    return shown(cursor.lastrowid)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def shown(draft_id: int) -> dict:
    with closing(connect()) as connection:
        row = connection.execute('SELECT * FROM drafts WHERE id = ?', (draft_id,)).fetchone()
    require(row is not None, 'That draft is gone.', 404)
    entries = json.loads(row['entries'])
    hidden = sum(1 for entry in entries if packages.hidden('cast', entry))
    if row['target'] == 'world' and entries:
        hidden = len(entries[0]['files'].get('hidden-truths.json', {}).get('truths', []))
    elif row['target'] == 'town' and entries:
        hidden = sum(1 for person in entries[0].get('notables') or [] if packages.hidden('cast', person))
    return {'id': row['id'], 'at': row['at'], 'town': row['town'], 'target': row['target'], 'ask': row['ask'],
            'status': row['status'], 'entries': entries, 'hidden': hidden}


def pending(opened: worlds.Opened) -> list[dict]:
    with closing(connect()) as connection:
        rows = connection.execute("SELECT id FROM drafts WHERE folder = ? AND status = 'pending' ORDER BY id DESC",
                                  (str(opened.folder),)).fetchall()
    return [shown(row['id']) for row in rows]


def decide(opened: worlds.Opened, draft_id: int, approve: bool, entries: list | None = None) -> dict:
    """Approve (optionally with the author's edits to the entries) or reject a pending draft."""
    item = shown(draft_id)
    require(item['status'] == 'pending', 'That draft was already decided.', 409)
    town = None
    if approve and item['target'] == 'town':
        from worldsmith import wizard
        town = wizard.approve_town(opened, (entries or item['entries'])[0])
    elif approve and item['target'] == 'world':
        from worldsmith import worldgen
        worldgen.approve_world(opened, item['entries'][0])
    elif approve:
        files = towns.read(opened, item['town'])
        kind, data, problems = merged(files, item['target'], entries if entries is not None else item['entries'])
        if problems:
            raise DomainError('The town has changed since this draft and Dungeon would refuse it now: '
                              + '; '.join(problems[:6]), 409)
        town = towns.save(opened, item['town'], kind, data)
    with closing(connect()) as connection, connection:
        connection.execute('UPDATE drafts SET status = ? WHERE id = ?', ('approved' if approve else 'rejected', draft_id))
    return {'draft': shown(draft_id), 'town': town}
