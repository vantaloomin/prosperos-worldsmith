"""Names for townsfolk and NPCs, from Dungeon's own name tables (vendored by scripts/sync_format.py into
worldsmith/dungeon_format/data): the name banks in names.json (per era and heritage, about 200 given names and 100
family names to a group) and the popular names by birth year in given_names.json.

A town names its people with `names`: a `bank` (left out, its era's), a `mix` of the bank's groups by weight, and
`groups` of its own for peoples the banks lack. `groups_for` reads that the way Dungeon's catalog.name_groups does,
`sample` draws names from it for a preview, and `invented_in` flags names that read as made up by a language model
(Elara, Voss, Vaeryn Duskmere), the way Dungeon's naming.py does, so the wizards can refuse them.

Other peoples (elves, dwarves, wolf-kin, oni: Dungeon's lifespans.json and its `peoples` name bank) live in a town by
the share of each kind its `kinds` block gives ({"dwarf": {"share": 0.1}}), humans the rest: `shares` and
`kind_groups` read that the way Dungeon's lifespans.py does, so a preview rolls each person's kind first.
"""
import json
import random
import re
from functools import cache
from pathlib import Path

DATA = Path(__file__).parent / 'dungeon_format' / 'data'
WORD = re.compile(r"[A-Z][A-Za-z'’-]+")
# As in Dungeon's naming.py: shapes models reach for when they coin a name, and words that only look like them.
COINED_GIVEN = re.compile(r'^(kael|vael|vaer|cael|lyr(a|ae|e)|zeph|nyx|vex|seraph|sylv[aei]r|elys|elar|eryn|vey|xyl|'
                          r'thal[aeiou]r|aeri|aeryn|ael)|(yra|yrin|ithra|ara?th|ys{2})$', re.I)
COINED_FAMILY = re.compile(r'^(raven|shadow|storm|night|moon|star|dusk|dawn|silver|frost|ember|thorn|wolf|black|'
                           r'iron|ash|winter|bright|grim|hollow|mist|sun)(wood|crest|vale|fall|mere|bane|wind|whisper|'
                           r'shade|heart|blade|song|fire|forge|thorne?|weaver|hollow|ridge|veil|born|walker|helm|'
                           r'shadow|mantle|ward|haven)$', re.I)
NOT_NAMES = re.compile(r'(ed|ing|ly|less|ness|ful)$', re.I)
MOST_SAMPLES = 40
HUMAN = 'human'
# As in Dungeon's lifespans.py: a kind listed with no share has DEFAULT_SHARE when no kind there has one, never more
# than DEFAULT_TOTAL of the town in all.
DEFAULT_SHARE = 0.1
DEFAULT_TOTAL = 0.3


@cache
def tables() -> tuple[dict, dict]:
    return (json.loads((DATA / 'names.json').read_text(encoding='utf-8')),
            json.loads((DATA / 'given_names.json').read_text(encoding='utf-8')))


@cache
def kinds_table() -> dict[str, dict]:
    return json.loads((DATA / 'lifespans.json').read_text(encoding='utf-8'))['kinds']


def kinds(city: dict) -> dict[str, dict]:
    """Every kind where this town is: the built-in ones with the town's `kinds` block's changes and its own."""
    found = {key: dict(value) for key, value in kinds_table().items()}
    listed = city.get('kinds')
    for key, value in (listed.items() if isinstance(listed, dict) else ()):
        if isinstance(value, dict):
            found[key] = {**found.get(key, {}), **value}
    return found


def peoples() -> list[dict]:
    """The peoples a world can hold, in Dungeon's order: {id, label, lifespan, folk, type}."""
    return [{'id': key, 'label': value['label'], 'lifespan': value['lifespan'], 'folk': value['folk'],
             'type': value.get('type') or value['label']}
            for key, value in kinds_table().items() if value.get('folk')]


def banks() -> dict[str, dict]:
    return tables()[0]['banks']


def eras() -> dict[str, dict]:
    return tables()[0]['eras']


def bank_of(names: dict | None, era: str) -> str:
    return (names or {}).get('bank') or eras().get(era, eras()['modern'])['bank']


def groups_for(city: dict) -> tuple[dict[str, dict], dict[str, float]]:
    """The groups a town draws its people's names from, and the weight of each (Dungeon's catalog.name_groups)."""
    own = city.get('names') or {}
    era = eras().get(city.get('era', 'modern'), eras()['modern'])
    bank = bank_of(own, city.get('era', 'modern'))
    base = banks().get(bank, {}) | (own.get('groups') or {})
    groups = base
    listed = city.get('kinds')
    if isinstance(listed, dict) and listed:
        # A listed kind no group is tied to takes its names from the peoples bank's group for it.
        tied = {group.get('kind') for group in base.values()}
        groups = {key: banks()['peoples'][key] for key in listed
                  if key in banks().get('peoples', {}) and key not in tied} | base
    if own.get('mix'):
        mix = own['mix']
    elif own.get('groups'):
        mix = dict.fromkeys(own['groups'], 1.0)
    elif bank == era['bank'] and era['mix']:
        mix = era['mix']
    else:
        mix = {}
    mix = {key: weight for key, weight in mix.items() if weight > 0 and key in groups}
    return groups, mix or dict.fromkeys(base, 1.0)


def shares(city: dict) -> dict[str, float]:
    """The share of the town's people of each kind other than human (Dungeon's lifespans.shares); humans the rest."""
    block = city.get('kinds') if isinstance(city.get('kinds'), dict) else {}
    block = {key: value for key, value in block.items() if isinstance(value, dict)}
    if not block:
        return {}
    given = any('share' in value for value in block.values())
    found = {key: value['share'] if 'share' in value else 0 if given else min(DEFAULT_SHARE, DEFAULT_TOTAL / len(block))
             for key, value in block.items()}
    groups, mix = groups_for(city)
    total = sum(mix.values())
    known = kinds(city)
    for key, weight in mix.items():
        kind = groups[key].get('kind')
        if kind and kind not in block and kind in known:
            found[kind] = found.get(kind, 0) + weight / total
    found = {key: share for key, share in sorted(found.items())
             if isinstance(share, (int, float)) and share > 0 and key != HUMAN and key in known}
    total = sum(found.values())
    return {key: share / total for key, share in found.items()} if total > 1 else found


def kind_groups(city: dict, kind: str) -> dict[str, float]:
    """The name groups people of a kind take their names from, with weights (Dungeon's lifespans.groups_for)."""
    groups, mix = groups_for(city)
    own = ((city.get('kinds') or {}).get(kind) or {}).get('groups') if isinstance(city.get('kinds'), dict) else None
    if own:
        return {key: mix.get(key, 1.0) for key in own if key in groups} or kind_groups(city, HUMAN)
    tied = {key: weight for key, weight in mix.items() if (groups[key].get('kind') or HUMAN) == kind}
    if not tied and kind != HUMAN:
        tied = {key: 1.0 for key, group in groups.items() if group.get('kind') == kind}
    if tied:
        return tied
    return kind_groups(city, HUMAN) if kind != HUMAN else mix


def drawn_group(city: dict, rng: random.Random) -> tuple[str, str]:
    """(name group, kind) for one person: the kind first by the town's shares, then a group of that kind's."""
    groups, mix = groups_for(city)
    found = shares(city)
    if not found:
        key = rng.choices(list(mix), weights=list(mix.values()))[0]
        return key, groups[key].get('kind') or HUMAN
    kind, mark = HUMAN, rng.random()
    for key, share in found.items():
        if mark < share:
            kind = key
            break
        mark -= share
    weights = kind_groups(city, kind)
    return rng.choices(list(weights), weights=list(weights.values()))[0], kind


def given_from(group: dict, rng: random.Random) -> str:
    """A given name from the group's lists, or (a modern group linked to cultures) from those cultures' popular
    names across birth years."""
    names = [*group.get('feminine', []), *group.get('masculine', []), *group.get('neutral', [])]
    cultures = tables()[1]['cultures']
    linked = [key for key in group.get('cultures') or {} if key in cultures]
    if linked and (not names or rng.random() < 0.7):
        cohort = rng.choice(cultures[rng.choice(linked)]['cohorts'])
        return rng.choice([*cohort['feminine'], *cohort['masculine']])
    return rng.choice(names)


def sample(city: dict, count: int = 12, seed: str = 'worldsmith') -> list[dict]:
    """Names drawn the way Dungeon draws townsfolk: each person's kind by the town's shares, then a group by the mix:
    {name, group, kind (None for a human)}."""
    groups, _mix = groups_for(city)
    labels = kinds(city)
    rng = random.Random(seed)
    drawn = []
    for _ in range(min(count, MOST_SAMPLES)):
        key, kind = drawn_group(city, rng)
        group = groups[key]
        drawn.append({'name': f"{given_from(group, rng)} {rng.choice(group['family'])}", 'group': key,
                      'kind': None if kind == HUMAN else (labels.get(kind) or {}).get('label', kind)})
    return drawn


def spread(city: dict) -> dict:
    """How wide a town's names run: given and family names it can draw on, and from which groups."""
    groups, mix = groups_for(city)
    given, family = set(), set()
    for key in [*mix, *(key for kind in shares(city) for key in kind_groups(city, kind))]:
        group = groups[key]
        given.update([*group.get('feminine', []), *group.get('masculine', []), *group.get('neutral', [])])
        family.update(group['family'])
    return {'bank': bank_of(city.get('names'), city.get('era', 'modern')), 'given': len(given),
            'family': len(family), 'groups': [{'id': key, 'weight': mix[key], 'own': key in (city.get('names') or {}).get('groups', {})}
                                              for key in mix]}


def view(city: dict, seed: str = 'worldsmith') -> dict:
    """What the Names tab shows: the banks to pick from (each with its groups), the town's spread and samples, the
    peoples a town can hold and the share of each it has."""
    return {'banks': {bank: sorted(groups) for bank, groups in banks().items() if bank != 'peoples'},
            'era_bank': eras().get(city.get('era', 'modern'), eras()['modern'])['bank'],
            'spread': spread(city), 'samples': sample(city, 12, seed), 'peoples': peoples(),
            'shares': shares(city), 'present': present(city)}


def present(city: dict) -> dict[str, float]:
    """The share of the town's people of each kind other than human, however it comes about: the `kinds` block's
    shares, else the weight of the mix's groups tied to a kind (Kingswood's halflings)."""
    found = shares(city)
    if found:
        return found
    groups, mix = groups_for(city)
    total = sum(mix.values()) or 1
    for key, weight in mix.items():
        kind = groups[key].get('kind')
        if kind and kind != HUMAN:
            found[kind] = found.get(kind, 0) + weight / total
    return found


def prompt_text(era: str) -> str:
    """The banks as a model reads them, the era's own first: each group with a few of its names."""
    rng = random.Random('prompt')
    first = eras().get(era, eras()['modern'])['bank']
    lines = []
    for bank in sorted(banks(), key=lambda key: key != first):
        parts = []
        for key, group in banks()[bank].items():
            given = [*group.get('feminine', []), *group.get('masculine', [])] or group.get('neutral', [])
            picks = rng.sample(given, min(3, len(given))) if given else []
            parts.append(f"{key} ({', '.join(picks)} / {', '.join(group['family'][:2])})")
        lines.append(f"- {bank}{' (the era default)' if bank == first else ''}: {'; '.join(parts)}")
    return '\n'.join(lines)


def peoples_text() -> str:
    """The peoples as a model reads them: by folk and type, each id with its lifespan."""
    lines: dict[str, list[str]] = {}
    for item in peoples():
        years = "doesn't age" if item['lifespan'] is None else f"{item['lifespan']}y"
        lines.setdefault(f"{item['folk']}, {item['type']}", []).append(f"{item['id']} ({years})")
    return '\n'.join(f'- {key}: {", ".join(found)}' for key, found in lines.items())


# Invented-sounding names --------------------------------------------------------------------------------------

@cache
def invented() -> frozenset[str]:
    found = tables()[1]['invented']
    return frozenset(word.casefold() for word in [*found['given'], *found['family']])


@cache
def known() -> frozenset[str]:
    """Every word of every name in the tables: real names, however unusual, are never flagged."""
    words = set()
    for item in tables()[1]['cultures'].values():
        for cohort in item['cohorts']:
            words.update(word for name in [*cohort['feminine'], *cohort['masculine']] for word in name.split())
        words.update(word for name in item['surnames'] for word in name.split())
    for bank in banks().values():
        for group in bank.values():
            for key in ('feminine', 'masculine', 'neutral', 'family'):
                words.update(word for name in group.get(key, []) for word in name.split())
    return frozenset(word.casefold() for word in words)


def coined(word: str) -> bool:
    folded = word.casefold()
    if folded in invented():
        return True
    if folded in known() or NOT_NAMES.search(word):
        return False
    return bool(COINED_GIVEN.search(word) or COINED_FAMILY.search(word))


def invented_in(*names: str) -> list[str]:
    """The words of these names that read as invented by a model, in order of first use."""
    found = [word for name in names for word in WORD.findall(name or '') if coined(word)]
    return list(dict.fromkeys(found))
