# Vendored from prosperos-dungeon Program/dungeon/packages.py by scripts/sync_format.py. Edit it there, then sync.
"""World packages (requirements "World packages"; docs/packages.md).

A world is one SQLite file: its canon, cast, personas, hidden truths, planned beats, rules, tables, prices and
assets. The same world can be written out as a folder of Markdown and JSON (for bulk edits, or for an author to keep
in git) and read back in; a validator checks the folder before it replaces anything.

The folder (dungeon/world/packages/vallarith is one):
- `world.json`: the world's settings (name, calendar, currency, the ruleset and tier defaults).
- `canon/*.md` and any other `.md`: the world's documents, kept as written.
- Section files, each a JSON object holding one list of entries with ids (`lore.json` `entries`, `cast.json`
  `cast`, SECTIONS). The rest of the object (schema_version, fields, notes) is kept with the section.
- `engine/<kind>/<key>.json`: the game's own data for the world's towns and roads (a town's adventure, items and
  finds; the world's travel map, arcs, factions in play, institutions and tiers; premades and city files).
  ENGINE_KINDS.
- `assets/**`: maps and images, kept as bytes.

The built-in worlds ship as folders (dungeon/world/packages/<id>); the game's own data for them still lives in
dungeon/world/data, and is gathered into the package's `engine` part as it is built. A built-in package is built
into the data folder (packages/<id>.sqlite) when first asked for, and built again whenever its sources change.

In the file every entry is a row (`entries`), with whether it holds a hidden truth, so an editor can mark it; the
engine's data are documents (`engine`); the rest is `documents`, `assets` and `meta`.
"""
import hashlib
import json
import mimetypes
import re
import sqlite3
from contextlib import closing
from pathlib import Path

from worldsmith.dungeon_format.errors import DomainError, require

FORMAT = 1
BUILTIN = Path(__file__).parent / 'world' / 'packages'
DATA = Path(__file__).parent / 'world' / 'data'
FOLDER = 'packages'
# Section file -> the key of its list of entries.
SECTIONS = {'lore': 'entries', 'regions': 'regions', 'settlements': 'settlements', 'factions': 'factions',
            'deities': 'powers', 'cast': 'cast', 'personas': 'personas', 'hidden-truths': 'truths', 'beats': 'arcs'}
# Sections whose every entry is hidden from the player; and the fields that hold a hidden truth in any entry.
HIDDEN_SECTIONS = ('hidden-truths',)
HIDDEN_FIELDS = ('secret', 'secrets', 'guise', 'mortal_life', 'truth', 'hidden')
ENGINE_KINDS = ('adventures', 'arcs', 'art', 'cities', 'factions', 'finds', 'institutions', 'items', 'premades',
                'tiers', 'travel', 'hexes')
ID = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
# Cross-references that must name an entry of another section: (section, field, the section it names).
REFERENCES = (('settlements', 'region', 'regions'), ('cast', 'faction', 'factions'), ('cast', 'settlement', 'settlements'),
              ('settlements', 'faction', 'factions'))
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entries (
  section TEXT NOT NULL, id TEXT NOT NULL, position INTEGER NOT NULL, name TEXT NOT NULL DEFAULT '',
  hidden INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL, PRIMARY KEY (section, id));
CREATE TABLE IF NOT EXISTS documents (path TEXT PRIMARY KEY, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS engine (kind TEXT NOT NULL, key TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (kind, key));
CREATE TABLE IF NOT EXISTS assets (path TEXT PRIMARY KEY, mime TEXT NOT NULL, bytes BLOB NOT NULL);
"""


# Reading a folder ---------------------------------------------------------------------------------

def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise DomainError(f'{path.name} is not valid JSON: {error}', 422) from error


def folder_contents(folder: Path) -> dict:
    """Everything a world folder holds, read and checked, as the package will keep it."""
    require(folder.is_dir(), f'{folder} is not a folder.', 404)
    require((folder / 'world.json').is_file(), 'A world folder needs a world.json.', 422)
    world = read_json(folder / 'world.json')
    require(isinstance(world, dict) and bool(world.get('id')) and bool(world.get('name')),
            'world.json needs an id and a name.', 422)
    sections = {}
    for name, key in SECTIONS.items():
        path = folder / f'{name}.json'
        if path.is_file():
            data = read_json(path)
            require(isinstance(data, dict) and isinstance(data.get(key), list),
                    f'{name}.json needs a list under "{key}".', 422)
            sections[name] = data
    documents = {path.relative_to(folder).as_posix(): path.read_text(encoding='utf-8')
                 for path in sorted(folder.rglob('*.md')) if 'engine' not in path.relative_to(folder).parts}
    engine = {}
    for kind in ENGINE_KINDS:
        for path in sorted((folder / 'engine' / kind).glob('*.json')):
            engine[(kind, path.stem)] = read_json(path)
    assets = {path.relative_to(folder).as_posix(): path.read_bytes()
              for path in sorted((folder / 'assets').rglob('*')) if path.is_file()}
    contents = {'world': world, 'sections': sections, 'documents': documents, 'engine': engine, 'assets': assets}
    problems = validate(contents)
    require(not problems, 'The world folder has problems: ' + '; '.join(problems[:12])
            + (f' (and {len(problems) - 12} more)' if len(problems) > 12 else ''), 422)
    return contents


def validate(contents: dict) -> list[str]:
    """What is wrong with a world's contents: ids missing, malformed or repeated, and references to nothing."""
    problems, ids = [], {}
    for name, data in contents['sections'].items():
        ids[name] = section_ids(name, data[SECTIONS[name]], problems)
    for section, field, target in REFERENCES:
        if section in contents['sections'] and target in ids:
            problems += broken_references(section, contents['sections'][section][SECTIONS[section]], field, target,
                                          ids[target])
    return problems


def entry_label(entry: dict, number: int) -> str:
    """An entry as its author knows it: by its id or its title, its place in the list only when it has neither."""
    named = entry.get('id') or entry.get('title') or entry.get('name')
    return f'"{named}"' if isinstance(named, str) and named.strip() else f'entry {number}'


def section_ids(name: str, entries: list, problems: list[str]) -> set[str]:
    seen = set()
    for number, entry in enumerate(entries, 1):
        entry_id = entry.get('id') if isinstance(entry, dict) else None
        if not isinstance(entry, dict):
            problems.append(f'{name} entry {number} is not an object')
        elif not isinstance(entry_id, str) or not ID.match(entry_id):
            problems.append(f'{name} {entry_label(entry, number)} needs a lowercase kebab-case id')
        elif entry_id in seen:
            problems.append(f'{name} has two entries with the id {entry_id}')
        if isinstance(entry_id, str):
            seen.add(entry_id)
    return seen


def broken_references(section: str, entries: list, field: str, target: str, known: set[str]) -> list[str]:
    problems = []
    for entry in entries:
        named = entry.get(field) if isinstance(entry, dict) else None
        for value in named if isinstance(named, list) else [named] if named else []:
            if isinstance(value, str) and value not in known:
                problems.append(f"{section} {entry.get('id')}: {field} {value} is not in {target}")
    return problems


def hidden(section: str, entry: dict) -> bool:
    return section in HIDDEN_SECTIONS or any(entry.get(field) for field in HIDDEN_FIELDS)


# The package file ---------------------------------------------------------------------------------

def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def write(contents: dict, path: Path) -> Path:
    """A package file from a world's contents; an existing file is replaced only once the new one is whole."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix('.partial')
    partial.unlink(missing_ok=True)
    with closing(connect(partial)) as connection, connection:
        connection.executescript(SCHEMA)
        meta = {'format': FORMAT, 'world': contents['world'],
                'sections': {name: {key: value for key, value in data.items() if key != SECTIONS[name]}
                             for name, data in contents['sections'].items()}}
        connection.executemany('INSERT INTO meta (key, value) VALUES (?, ?)',
                               [(key, json.dumps(value, ensure_ascii=False)) for key, value in meta.items()])
        connection.executemany(
            'INSERT INTO entries (section, id, position, name, hidden, data) VALUES (?, ?, ?, ?, ?, ?)',
            [(name, entry['id'], position, str(entry.get('name') or entry.get('title') or ''),
              int(hidden(name, entry)), json.dumps(entry, ensure_ascii=False))
             for name, data in contents['sections'].items() for position, entry in enumerate(data[SECTIONS[name]])])
        connection.executemany('INSERT INTO documents (path, text) VALUES (?, ?)', contents['documents'].items())
        connection.executemany('INSERT INTO engine (kind, key, data) VALUES (?, ?, ?)',
                               [(kind, key, json.dumps(data, ensure_ascii=False))
                                for (kind, key), data in contents['engine'].items()])
        connection.executemany('INSERT INTO assets (path, mime, bytes) VALUES (?, ?, ?)',
                               [(name, mimetypes.guess_type(name)[0] or 'application/octet-stream', data)
                                for name, data in contents['assets'].items()])
    partial.replace(path)
    return path


def read(path: Path) -> dict:
    """A package file's contents, in the shape folder_contents gives."""
    require(path.is_file(), 'That world package does not exist.', 404)
    with closing(connect(path)) as connection:
        meta = {row['key']: json.loads(row['value']) for row in connection.execute('SELECT key, value FROM meta')}
        require(meta.get('format') == FORMAT, 'That world package is from another version of Dungeon.', 422)
        sections = {name: header | {SECTIONS[name]: []} for name, header in meta['sections'].items()}
        for row in connection.execute('SELECT section, data FROM entries ORDER BY section, position'):
            sections[row['section']][SECTIONS[row['section']]].append(json.loads(row['data']))
        return {'world': meta['world'], 'sections': sections,
                'documents': {row['path']: row['text'] for row in connection.execute('SELECT path, text FROM documents')},
                'engine': {(row['kind'], row['key']): json.loads(row['data'])
                           for row in connection.execute('SELECT kind, key, data FROM engine')},
                'assets': {row['path']: bytes(row['bytes']) for row in connection.execute('SELECT path, bytes FROM assets')}}


def export(path: Path, folder: Path) -> Path:
    """A package written out as a world folder (into an empty or new folder)."""
    contents = read(path)
    require(not folder.exists() or not any(folder.iterdir()), 'Export a world into an empty folder.', 409)
    folder.mkdir(parents=True, exist_ok=True)
    dump(folder / 'world.json', contents['world'])
    for name, data in contents['sections'].items():
        dump(folder / f'{name}.json', data)
    for name, text in contents['documents'].items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    for (kind, key), data in contents['engine'].items():
        dump(folder / 'engine' / kind / f'{key}.json', data)
    for name, data in contents['assets'].items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return folder


def dump(path: Path, data: object):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


def fingerprint(contents: dict) -> str:
    """A hash of a world's contents, to tell whether a built package is still current."""
    digest = hashlib.sha256()
    digest.update(json.dumps([contents['world'], contents['sections'], contents['documents'],
                              sorted((f'{kind}/{key}', data) for (kind, key), data in contents['engine'].items())],
                             sort_keys=True, ensure_ascii=False).encode())
    for name in sorted(contents['assets']):
        digest.update(name.encode() + hashlib.sha256(contents['assets'][name]).digest())
    return digest.hexdigest()


# Built-in worlds ----------------------------------------------------------------------------------

def builtin_ids() -> list[str]:
    return sorted(path.name for path in BUILTIN.iterdir() if (path / 'world.json').is_file())


def engine_for(world_id: str) -> dict:
    """The game's own data for a world (dungeon/world/data): its travel map, arcs, factions in play and tiers, and for
    each town on its map the town's adventure, items, finds, premades and city file."""
    found = {}
    for kind in ('travel', 'arcs', 'factions', 'tiers'):
        path = DATA / kind / f'{world_id}.json'
        if path.is_file():
            found[(kind, world_id)] = read_json(path)
    towns = {node['city'] for node in (found.get(('travel', world_id)) or {}).get('nodes', []) if node.get('city')}
    for town in sorted(towns):
        for kind in ('adventures', 'items', 'finds', 'premades', 'cities'):
            path = DATA / kind / f'{town}.json'
            if path.is_file():
                found[(kind, town)] = read_json(path)
    return found


def builtin_contents(world_id: str) -> dict:
    require(world_id in builtin_ids(), 'That world is not built in.', 404)
    contents = folder_contents(BUILTIN / world_id)
    contents['engine'] = engine_for(world_id) | contents['engine']
    return contents


def installed(root: Path, world_id: str) -> Path:
    """A built-in world's package in the data folder, built (again) when missing or out of date. One the author has
    edited in the world editor (meta `edited`, dungeon/package_edit.py) is kept as edited until it is reset."""
    contents = builtin_contents(world_id)
    path = Path(root) / FOLDER / f'{world_id}.sqlite'
    current = fingerprint(contents)
    if path.is_file():
        try:
            with closing(connect(path)) as connection:
                kept = {row['key']: json.loads(row['value']) for row in connection.execute(
                    "SELECT key, value FROM meta WHERE key IN ('fingerprint', 'edited')")}
            if kept.get('edited') or kept.get('fingerprint') == current:
                return path
        except sqlite3.Error:
            pass
    write(contents, path)
    with closing(connect(path)) as connection, connection:
        connection.execute("INSERT INTO meta (key, value) VALUES ('fingerprint', ?)", (json.dumps(current),))
    return path


def reset(root: Path, world_id: str) -> Path:
    """A built-in world's package built again from the shipped files, its edits gone."""
    require(world_id in builtin_ids(), 'Only a built-in world can be reset to how it shipped.', 409)
    (Path(root) / FOLDER / f'{world_id}.sqlite').unlink(missing_ok=True)
    return installed(root, world_id)


def summary(path: Path) -> dict:
    """What a package holds, for the screen: the world, and how many entries each section has (and how many hide
    a truth)."""
    with closing(connect(path)) as connection:
        world = json.loads(connection.execute("SELECT value FROM meta WHERE key='world'").fetchone()['value'])
        counts = {row['section']: {'entries': row['n'], 'hidden': row['h']} for row in connection.execute(
            'SELECT section, COUNT(*) AS n, SUM(hidden) AS h FROM entries GROUP BY section ORDER BY section')}
        documents = connection.execute('SELECT COUNT(*) AS n FROM documents').fetchone()['n']
        engine = connection.execute('SELECT COUNT(*) AS n FROM engine').fetchone()['n']
        assets = connection.execute('SELECT COUNT(*) AS n FROM assets').fetchone()['n']
        edited = connection.execute("SELECT value FROM meta WHERE key='edited'").fetchone()
    return {'id': world['id'], 'name': world['name'], 'sections': counts, 'documents': documents, 'engine': engine,
            'assets': assets, 'size': path.stat().st_size, 'edited': bool(edited and json.loads(edited['value']))}


def import_folder(root: Path, folder: Path) -> dict:
    """A world folder made into a package in the data folder, once it validates. A built-in world's id is refused:
    its package is built from the shipped folder."""
    contents = folder_contents(folder)
    world_id = contents['world']['id']
    require(isinstance(world_id, str) and bool(ID.match(world_id)), 'world.json needs a lowercase kebab-case id.', 422)
    require(world_id not in builtin_ids(), f'{world_id} is a built-in world; give the folder another id.', 409)
    return summary(write(contents, Path(root) / FOLDER / f'{world_id}.sqlite'))
