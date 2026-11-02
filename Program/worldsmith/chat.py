"""The brainstorm chat: a model that knows the open world talks ideas through with the author.

It never changes the world. When an idea is ready it proposes a draft, marked in its answer as
`<draft town="kingswood" target="places">a smugglers' den by the landing</draft>`; the screen offers each as a
button, and pressing it runs an ordinary draft (worldsmith.drafts) that lands in the approval queue.
"""
import re
from contextlib import closing

from worldsmith import drafts, models, towns, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import require

SCHEMA = """
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, folder TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL);
"""
MOST_TURNS = 30
MOST_MESSAGE = 8000
DRAFT = re.compile(r'<draft\s+town="([a-z0-9-]+)"\s+target="([a-z_]+)"\s*>(.*?)</draft>', re.S)
SYSTEM = """You are a world-building partner for an author making worlds for Prospero's Dungeon, a text roleplaying
game for consenting adults: dark, morally complex stories where good outcomes are not guaranteed. Talk ideas
through like a sharp co-writer: offer specific options, push on what makes a place or person interesting (wants,
debts, secrets, who profits), and keep to the world's established facts and tone. Be concise.

Avoid names and words that read as AI cliches (Voss, Maren, Thorne, Elara, Kael, "Drowned Lamp", "whispering",
"tapestry", "testament", "palpable", "nestled").

You cannot change the world yourself. When the author wants an idea written up, propose a draft by adding, on its
own line, a tag like <draft town="TOWN_ID" target="TARGET">what to draft, in one or two sentences</draft>.
TARGET is one of: {targets}. Use only town ids from the list below. The author decides whether to run it."""


def connect():
    connection = towns.history()
    connection.executescript(SCHEMA)
    return connection


def world_brief(opened: worlds.Opened, town: str | None) -> str:
    found, _ = worlds.contents(opened)
    world = found['world']
    lines = [f"World: {world.get('name')} ({world.get('genre', '')}). {world.get('pitch', '')}"]
    factions = (found['sections'].get('factions') or {}).get('factions') or []
    if factions:
        lines.append('Factions: ' + '; '.join(f"{item.get('name')} ({item.get('id')})" for item in factions[:40]
                                              if isinstance(item, dict)))
    listed = worlds.towns(found)
    lines.append('Towns: ' + '; '.join(f"{item['name']} (id {item['id']}{', a road' if item['road'] else ''})"
                                       for item in listed))
    if town:
        city = found['engine'].get(('cities', town)) or {}
        lines.append(f"\nThe author has {city.get('name', town)} open: {city.get('summary', '')}")
        for key in ('neighborhoods', 'places', 'notables'):
            entries = [item for item in city.get(key) or [] if isinstance(item, dict)]
            if entries:
                lines.append(f'{key.title()}: ' + '; '.join(
                    f"{item.get('name')}" + (f" ({item.get('role')})" if item.get('role') else '') for item in entries[:50]))
        quests = (found['engine'].get(('adventures', town)) or {}).get('quests') or []
        if quests:
            lines.append('Quests: ' + '; '.join(str(item.get('title')) for item in quests if isinstance(item, dict)))
    return '\n'.join(lines)


def history(opened: worlds.Opened) -> list[dict]:
    with closing(connect()) as connection:
        rows = connection.execute('SELECT id, at, role, text FROM chat WHERE folder = ? ORDER BY id DESC LIMIT ?',
                                  (str(opened.folder), MOST_TURNS * 2)).fetchall()
    return [shown(dict(row)) for row in reversed(rows)]


def shown(row: dict) -> dict:
    proposals = [{'town': town, 'target': target, 'ask': ' '.join(ask.split())}
                 for town, target, ask in DRAFT.findall(row['text'])] if row['role'] == 'assistant' else []
    return {'id': row['id'], 'at': row['at'], 'role': row['role'], 'text': DRAFT.sub('', row['text']).strip(),
            'proposals': proposals}


def say(opened: worlds.Opened, message: str, town: str | None = None) -> list[dict]:
    """The author's message and the model's answer, added to the world's chat; the chat as it now stands."""
    message = message.strip()
    require(bool(message), 'Write something to say first.', 422)
    require(len(message) <= MOST_MESSAGE, 'That message is too long for the chat.', 422)
    require(town is None or bool(packages.ID.match(town)), 'A town id is lowercase words joined by hyphens.', 422)
    earlier = history(opened)
    transcript = '\n\n'.join(f"{'Author' if turn['role'] == 'user' else 'You'}: {turn['text']}" for turn in earlier)
    prompt = (world_brief(opened, town) + ('\n\nThe conversation so far:\n' + transcript if transcript else '')
              + f'\n\nAuthor: {message}\n\nYou:')
    system = SYSTEM.format(targets=', '.join([*drafts.CITY_TARGETS, *drafts.OTHER_TARGETS]))
    answer = models.complete(system, prompt).strip() or '(The model gave no answer.)'
    with closing(connect()) as connection, connection:
        for role, text in (('user', message), ('assistant', answer)):
            connection.execute('INSERT INTO chat (at, folder, role, text) VALUES (?, ?, ?, ?)',
                               (drafts.now(), str(opened.folder), role, text))
    return history(opened)


def clear(opened: worlds.Opened) -> list[dict]:
    with closing(connect()) as connection, connection:
        connection.execute('DELETE FROM chat WHERE folder = ?', (str(opened.folder),))
    return []
