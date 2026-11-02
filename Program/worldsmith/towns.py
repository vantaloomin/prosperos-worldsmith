"""A town's engine files: read, checked, saved and undone.

A town is up to five files named by its id: `cities` (checked against Dungeon's own City schema, which also checks
that every place, notable and event names a neighborhood, place or source that exists), `adventures`, `items`,
`finds` and `premades`. A built-in world keeps them in the checkout's data folder, a world folder in its `engine/`.

Saving refuses a city Dungeon would refuse, and keeps the file as it was, so the last save can be undone. The
history lives in Worldsmith's own folder, so nothing extra appears in a Dungeon checkout or a world folder.
"""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from worldsmith import settings
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError, require
from worldsmith.dungeon_format.schema import City
from worldsmith.worlds import TOWN_KINDS, Opened

HISTORY = """
CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, path TEXT NOT NULL, before TEXT);
"""
MOST_HISTORY = 200


def path_of(opened: Opened, town: str, kind: str) -> Path:
    require(kind in TOWN_KINDS, f'{kind} is not part of a town.', 404)
    require(bool(packages.ID.match(town)), 'A town id is lowercase words joined by hyphens.', 422)
    root = opened.data if opened.data else opened.folder / 'engine'
    return root / kind / f'{town}.json'


def problems_in(kind: str, data: object) -> list[str]:
    """What Dungeon would refuse in a town file. A city is checked against Dungeon's schema; the other parts only
    need to be JSON objects for now."""
    if not isinstance(data, dict):
        return [f'The {kind} file needs to be a JSON object.']
    if kind != 'cities':
        return []
    try:
        City.model_validate(data)
    except ValidationError as error:
        return [readable(item) for item in error.errors()]
    return []


def readable(item: dict) -> str:
    where = ' > '.join(str(part) for part in item['loc'])
    message = item['msg'].removeprefix('Value error, ')
    return f'{where}: {message}' if where else message


def read(opened: Opened, town: str) -> dict:
    parts, problems = {}, {}
    for kind in TOWN_KINDS:
        path = path_of(opened, town, kind)
        parts[kind] = packages.read_json(path) if path.is_file() else None
        if parts[kind] is not None:
            problems[kind] = problems_in(kind, parts[kind])
    require(parts['cities'] is not None, f'{town} has no city file in this world.', 404)
    return {'id': town, 'parts': parts, 'problems': problems, 'undo': undoable(opened, town)}


def indent_of(text: str) -> int:
    """The indent a JSON file was written with (Dungeon's city files use 1, its quests 2), so a save keeps it."""
    for line in text.splitlines()[1:]:
        stripped = line.lstrip(' ')
        if stripped and len(stripped) < len(line):
            return len(line) - len(stripped)
    return 2


def kept_floats(before: object, after: object) -> object:
    """The browser turns 2.0 into 2; put the float back wherever the file had one with the same value, so a save
    changes only what the author changed."""
    if isinstance(before, dict) and isinstance(after, dict):
        return {key: kept_floats(before.get(key), value) for key, value in after.items()}
    if isinstance(before, list) and isinstance(after, list):
        return [kept_floats(before[at] if at < len(before) else None, value) for at, value in enumerate(after)]
    if isinstance(before, float) and type(after) is int and before == after:
        return before
    return after


def dumped(data: object, indent: int) -> str:
    return json.dumps(data, indent=indent, ensure_ascii=False) + '\n'


def history() -> sqlite3.Connection:
    path = settings.home() / 'history.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(HISTORY)
    return connection


def save(opened: Opened, town: str, kind: str, data: object) -> dict:
    path = path_of(opened, town, kind)
    found = problems_in(kind, data)
    if found:
        raise DomainError('Dungeon would refuse this: ' + '; '.join(found[:8])
                          + (f' (and {len(found) - 8} more)' if len(found) > 8 else ''), 422, 'invalid')
    if kind == 'cities':
        require(data.get('id') == town, 'A city file keeps its town id; make a new town to change it.', 422)
    before = path.read_text(encoding='utf-8') if path.is_file() else None
    if before:
        data = kept_floats(json.loads(before), data)
    text = dumped(data, indent_of(before) if before else 1 if kind == 'cities' else 2)
    if text != before:
        with closing(history()) as connection, connection:
            connection.execute('INSERT INTO history (at, path, before) VALUES (?, ?, ?)',
                               (datetime.now(timezone.utc).isoformat(timespec='seconds'), str(path), before))
            connection.execute('DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT ?)',
                               (MOST_HISTORY,))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8', newline='\n')
    return read(opened, town)


def undoable(opened: Opened, town: str) -> list[dict]:
    """The saves of this town that can be undone, newest first."""
    paths = {str(path_of(opened, town, kind)): kind for kind in TOWN_KINDS}
    with closing(history()) as connection:
        rows = connection.execute(f"SELECT id, at, path FROM history WHERE path IN ({','.join('?' * len(paths))}) "
                                  'ORDER BY id DESC LIMIT 20', list(paths)).fetchall()
    return [{'id': row['id'], 'at': row['at'], 'kind': paths[row['path']]} for row in rows]


def undo(opened: Opened, town: str) -> dict:
    """Put back the town's last saved file as it was before that save."""
    paths = [str(path_of(opened, town, kind)) for kind in TOWN_KINDS]
    with closing(history()) as connection, connection:
        row = connection.execute(f"SELECT id, path, before FROM history WHERE path IN ({','.join('?' * len(paths))}) "
                                 'ORDER BY id DESC LIMIT 1', paths).fetchone()
        require(row is not None, 'There is nothing to undo for this town.', 409)
        path = Path(row['path'])
        if row['before'] is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(row['before'], encoding='utf-8', newline='\n')
        connection.execute('DELETE FROM history WHERE id = ?', (row['id'],))
    return read(opened, town)


def city_schema() -> dict:
    return City.model_json_schema()
