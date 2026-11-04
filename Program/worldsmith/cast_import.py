"""A Dramatis cast's outer square, drafted as the world's factions for the author to approve.

Prospero's Dramatis (vantaloomin/prosperos-dramatis) exports a cast as one `prospero-cast` file: the cast (an outer
square of sides, any of them split into an inner square of people) and the characters it names. Each side of the
outer square becomes one faction, from the cast's own words:

- its name is the side's label, and its summary the side's stance and note;
- its goals are the stance, then each inner corner's "<label> pushes for it <stance>";
- its rivals are the other sides, and it has no allies;
- the characters linked to the side give its jobs;
- a confirmed resonance from the side becomes the truth behind one of its jobs ("<a> quietly deals with <b>").

The model fills in what a cast has no word for (kind, tier, the stops it holds, two clocks and its jobs) under the
world wizard's faction rules, and what comes back is checked the way the wizard checks factions, once more with the
problems if it fails. The factions are queued as one draft. Approving it adds them to the world's factions section and
its factions in play together, and one undo takes both back.
"""
import json
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from worldsmith import drafts, models, progress, towns, worldgen, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError, require

FORMAT, VERSION = 'prospero-cast', 1
TEXT = 400  # Dungeon's longest record text (worldgen.Text)
CLOCKS = 2
# The history key for these writes. Not a town id (packages.ID has no colon), so no town's undo takes them.
UNDO = 'world:factions'
NO_SECTION = ('This world has no factions section (factions.json), so a cast has nowhere to go. Draft the world '
              'first, or add the section.')
SYSTEM = worldgen.SYSTEM.replace(
    'You are building a whole new world with them, one part at a\ntime, in the exact JSON shape asked for, fitting '
    'the pitch and the parts already written.',
    "You bring the sides of a story's cast into their world as the factions in play, in the\nexact JSON shape asked "
    "for, fitting the world's tone and keeping the cast's own words.")


# Reading the file: only what becomes a faction. Dramatis checks the rest when it saves the cast. ----------------

class Read(BaseModel):
    model_config = ConfigDict(extra='ignore')


class Corner(Read):
    id: str
    label: str = ''
    stance: str = ''
    role: str = ''
    note: str = ''
    character_id: str | None = None
    inner: 'Square | None' = None


class Square(Read):
    corners: list[Corner] = Field(min_length=2, max_length=4)


class Link(Read):
    a: str
    b: str
    status: str = ''


class Cast(Read):
    title: str = ''
    theme: str = ''
    outer: Square
    resonance: list[Link] = Field(default_factory=list)


class CastFile(Read):
    format: Literal['prospero-cast']
    version: int
    cast: Cast
    characters: dict[str, dict] = Field(default_factory=dict)


Corner.model_rebuild()


def read(raw: object) -> CastFile:
    """A cast file as Dramatis exports it, or one plain sentence on why it is not one."""
    require(isinstance(raw, dict) and raw.get('format') == FORMAT,
            "That is not a Dramatis cast file. Export one from the cast in Prospero's Dramatis.", 422)
    require(raw.get('version') == VERSION,
            f"This cast file is version {raw.get('version')}, and this Worldsmith reads version {VERSION}. Update "
            'Worldsmith, then import it again.', 422)
    try:
        return CastFile.model_validate(raw)
    except ValidationError as error:
        first = error.errors()[0]
        where = ' > '.join(str(part) for part in first['loc'])
        raise DomainError(f"The cast file is damaged at {where}: {first['msg']}", 422) from error


# What the cast says of each faction ---------------------------------------------------------------------------

def name_of(corner: Corner) -> str:
    """A corner as Dramatis names it: its label, else its role, else its id."""
    return corner.label.strip() or corner.role.strip().capitalize() or f'Corner {corner.id}'


def slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:60].strip('-')


def unique(wanted: str, taken: set[str]) -> str:
    found, count = wanted, 1
    while found in taken:
        count += 1
        found = f'{wanted}-{count}'
    return found


def fitted(parts: list[str]) -> str:
    """The parts as one text, each ending a sentence, keeping whole parts while they fit in Dungeon's limit."""
    text = ''
    for part in [part.strip() for part in parts if part.strip()]:
        part = part if part[-1] in '.!?' else part + '.'
        joined = f'{text} {part}'.strip()
        if len(joined) > TEXT:
            break
        text = joined
    return text


def sides(bundle: CastFile, taken: set[str]) -> list[dict]:
    """Each side of the outer square as a faction seed: `fixed` holds what the cast says (kept as it is), `givers`
    and `truths` what its jobs should carry."""
    cast = bundle.cast
    ids: dict[str, str] = {}
    for side in cast.outer.corners:
        ids[side.id] = unique(slug(name_of(side)) or f'side-{slug(side.id) or "x"}', taken | set(ids.values()))
    side_of = {corner.id: side.id for side in cast.outer.corners
               for corner in [side, *(side.inner.corners if side.inner else [])]}
    every = {corner.id: corner for side in cast.outer.corners
             for corner in [side, *(side.inner.corners if side.inner else [])]}

    def person(corner: Corner) -> str:
        character = bundle.characters.get(corner.character_id or '') or {}
        return str(character.get('name') or '').strip() or name_of(corner)

    seeds = []
    for side in cast.outer.corners:
        inner = side.inner.corners if side.inner else []
        goals = [side.stance.strip()] if side.stance.strip() else []
        goals += [f'{name_of(corner)} pushes for it {corner.stance.strip()}' for corner in inner if corner.stance.strip()]
        fixed = {'id': ids[side.id], 'name': name_of(side),
                 'rivals': [ids[other.id] for other in cast.outer.corners if other.id != side.id], 'allies': []}
        summary = fitted([side.stance, side.note])
        fixed |= ({'summary': summary} if summary else {}) | ({'goals': goals[:6]} if goals else {})
        linked = [corner for corner in [side, *inner] if corner.character_id in bundle.characters]
        truths = [f'{person(every[link.a])} quietly deals with {person(every[link.b])}' for link in cast.resonance
                  if link.status == 'confirmed' and link.a in every and link.b in every and side_of[link.a] == side.id]
        seeds.append({'fixed': fixed, 'givers': list(dict.fromkeys(person(corner) for corner in linked)),
                      'truths': truths})
    return seeds


# Asking the model -----------------------------------------------------------------------------------------------

def stops_of(found: dict) -> list[dict]:
    world_id = found['world'].get('id')
    travel = found['engine'].get(('travel', world_id)) or {}
    return [node for node in travel.get('nodes') or [] if isinstance(node, dict) and node.get('id')]


def existing(found: dict) -> list[dict]:
    """The world's factions now: its section's, and its factions in play's."""
    world_id = found['world'].get('id')
    section = (found['sections'].get('factions') or {}).get('factions') or []
    engine = (found['engine'].get(('factions', world_id)) or {}).get('factions') or []
    return [item for item in [*section, *engine] if isinstance(item, dict) and item.get('id')]


def prompt_for(found: dict, bundle: CastFile, seeds: list[dict], problems: list[str]) -> str:
    world, cast = found['world'], bundle.cast
    stops = stops_of(found)
    lines = [f"World: {world.get('name')} ({world.get('genre') or ''}). {world.get('pitch') or ''}",
             'Stops on its travel map, the only ids "holds" may name: '
             + '; '.join(f"{stop.get('name') or stop['id']} ({stop['id']})" for stop in stops)
             if stops else 'This world has no travel map yet, so every "holds" stays empty.']
    standing = {item['id']: item.get('name') or item['id'] for item in existing(found)}
    if standing:
        lines.append('Factions already in the world (leave them as they are): '
                     + ', '.join(f'{name} ({key})' for key, name in standing.items()))
    lines += [f'\nThe author brings in the sides of the cast of their story "{cast.title or "untitled"}"'
              + (f', which asks: {cast.theme}' if cast.theme else '') + '. Each side becomes one faction. Keep the '
              'fields given for it exactly as they are, and write the rest.']
    for seed in seeds:
        lines.append(json.dumps(seed['fixed'], ensure_ascii=False))
        if seed['givers']:
            lines.append(f"  Its jobs are given by {', '.join(seed['givers'])} (each one's name as a job's \"giver\").")
        for truth in seed['truths']:
            lines.append(f'  Its secret, for one job\'s "truth": {truth}.')
    lines += ['\nWrite these factions as one JSON object matching this schema:', worldgen.schema_of('play'),
              '\n' + worldgen.FACTION_RULES.replace('Give each 1 or 2 clocks', f'Give each exactly {CLOCKS} clocks'),
              f'\nKeep every text field to at most {TEXT} characters.']
    if problems:
        lines += ['\nYour last answer was refused for these problems; fix them:', *problems]
    return '\n'.join(lines)


def with_truths(faction: dict, truths: list[str]) -> dict:
    """The cast's secrets put behind the faction's jobs, one each, wherever the model left them out."""
    jobs = [dict(job) for job in faction.get('jobs') or []]
    missing = [truth for truth in truths if not any(truth in job.get('truth', '') for job in jobs)]
    for at, truth in enumerate(missing[:len(jobs)]):
        job = jobs[at]
        joined = f"{truth}. {job.get('truth', '')}".strip()
        job['truth'] = joined if len(joined) <= TEXT else truth
    return faction | ({'jobs': jobs} if jobs else {})


def checked(seeds: list[dict], answer: dict, stops: set[str], standing: set[str]) -> tuple[list[dict], list[str]]:
    """The model's factions with the cast's own fields laid over them, and what Dungeon or the wizard would refuse."""
    written = {item.get('id'): item for item in answer.get('factions') or [] if isinstance(item, dict)}
    factions, problems = [], []
    for seed in seeds:
        key = seed['fixed']['id']
        if key not in written:
            problems.append(f'The answer has no faction {key}.')
            continue
        faction = with_truths(dict(written[key]) | seed['fixed'], seed['truths'])
        try:
            factions.append(worldgen.Faction.model_validate(faction).model_dump())
        except ValidationError as error:
            problems += [f'{key} > {problem}' for problem in worldgen.problems_of(error)]
            continue
        if len(faction.get('clocks') or []) != CLOCKS:
            problems.append(f'{key} needs exactly {CLOCKS} clocks.')
        if seed['truths'] and not faction.get('jobs'):
            problems.append(f'{key} needs a job for its secret to sit behind.')
    known = standing | {seed['fixed']['id'] for seed in seeds}
    return factions, problems + worldgen.faction_problems(factions, stops, known)


def draft(opened: worlds.Opened, raw: object) -> dict:
    """Ask for the cast's sides as factions, and queue them as one draft. Nothing is written to the world."""
    bundle = read(raw)
    found, _ = worlds.contents(opened)
    require('factions' in found['sections'], NO_SECTION, 409)
    world_id = found['world'].get('id') or opened.folder.name
    standing = {item['id'] for item in existing(found)}
    seeds = sides(bundle, standing)
    stops = {stop['id'] for stop in stops_of(found)}
    require(not progress.running(opened, 'cast'), 'A cast is already being brought into this world.', 409)
    problems: list[str] = []
    with progress.tracked(opened, 'cast', bundle.cast.title):
        for attempt in (1, 2):
            progress.report(opened, 'cast', 'write', attempt, problems)
            answer = worldgen.parsed_object(models.complete(SYSTEM, prompt_for(found, bundle, seeds, problems)),
                                            'factions')
            progress.report(opened, 'cast', 'check', attempt)
            factions, problems = checked(seeds, answer, stops, standing)
            if not problems:
                break
        else:
            raise DomainError("The model's factions still had problems after a retry: " + '; '.join(problems[:6]), 422)
    entry = {'cast': bundle.cast.title or 'Untitled cast', 'world': world_id, 'factions': factions}
    return drafts.queue(opened, world_id, 'factions', bundle.cast.theme, [entry])


# Approving and undoing --------------------------------------------------------------------------------------------

def paths(opened: worlds.Opened, world_id: str) -> tuple[Path, Path]:
    """The world's factions section, and its factions in play (a built-in world keeps those in the data folder)."""
    engine = opened.data / 'factions' if opened.data else opened.folder / 'engine' / 'factions'
    return opened.folder / 'factions.json', engine / f'{world_id}.json'


def section_entry(faction: dict) -> dict:
    """A faction as the package section lists it, the way the world wizard writes it."""
    return {key: faction[key] for key in ('id', 'name', 'kind', 'summary', 'goals')}


def approve(opened: worlds.Opened, entry: dict) -> dict:
    """Add the drafted factions to the section and the factions in play, as one save that one undo takes back."""
    found, _ = worlds.contents(opened)
    require('factions' in found['sections'], NO_SECTION, 409)
    world_id = found['world'].get('id') or opened.folder.name
    factions = [worldgen.Faction.model_validate(item).model_dump() for item in entry['factions']]
    standing = {item['id'] for item in existing(found)}
    clashes = sorted(standing & {item['id'] for item in factions})
    require(not clashes, f'The world has gained {", ".join(clashes)} since this draft. Reject it and import the cast '
            'again.', 409)
    problems = worldgen.faction_problems(factions, {stop['id'] for stop in stops_of(found)},
                                         standing | {item['id'] for item in factions})
    require(not problems, 'The world has changed since this draft: ' + '; '.join(problems[:6]), 409)
    section_path, engine_path = paths(opened, world_id)
    section = dict(found['sections']['factions'])
    section['factions'] = [*section['factions'], *(section_entry(item) for item in factions)]
    before = packages.validate(found)
    after = packages.validate(found | {'sections': found['sections'] | {'factions': section}})
    added = [problem for problem in after if problem not in before]
    require(not added, 'Dungeon would refuse the world with these factions: ' + '; '.join(added[:6]), 409)
    engine = found['engine'].get(('factions', world_id))
    engine = dict(engine, factions=[*(engine.get('factions') or []), *factions]) if isinstance(engine, dict) \
        else worldgen.factions_file(world_id, {'factions': factions})
    batch = f'cast-{uuid.uuid4().hex}'
    for path, data, indent in ((section_path, section, 2), (engine_path, engine, 1)):
        text = path.read_text(encoding='utf-8') if path.is_file() else None
        towns.write_tracked(path, towns.dumped(data, towns.indent_of(text) if text else indent, text), text, UNDO,
                            batch)
    return worlds.overview(opened)


def rows(connection: sqlite3.Connection, opened: worlds.Opened) -> list[sqlite3.Row]:
    found, _ = worlds.contents(opened)
    section_path, engine_path = paths(opened, found['world'].get('id') or opened.folder.name)
    return connection.execute('SELECT * FROM history WHERE town = ? AND path IN (?, ?) ORDER BY id DESC',
                              (UNDO, str(section_path), str(engine_path))).fetchall()


def imports(opened: worlds.Opened) -> list[dict]:
    """The cast imports into this world that can be undone, newest first."""
    with closing(towns.history()) as connection:
        found = rows(connection, opened)
    return list({row['batch']: {'at': row['at']} for row in reversed(found)}.values())[::-1]


def undo(opened: worlds.Opened) -> dict:
    """Take the last approved cast import back out of the section and the factions in play."""
    with closing(towns.history()) as connection, connection:
        found = rows(connection, opened)
        require(bool(found), 'There is no cast import to undo in this world.', 409)
        towns.put_back(connection, found[0])
    return worlds.overview(opened)
