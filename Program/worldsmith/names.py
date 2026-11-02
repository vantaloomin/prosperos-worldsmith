"""Names for townsfolk and NPCs, from Dungeon's own name tables (vendored by scripts/sync_format.py into
worldsmith/dungeon_format/data): the name banks in names.json (per era and heritage, about 200 given names and 100
family names to a group) and the popular names by birth year in given_names.json.

A town names its people with `names`: a `bank` (left out, its era's), a `mix` of the bank's groups by weight, and
`groups` of its own for peoples the banks lack. `groups_for` reads that the way Dungeon's catalog.name_groups does,
`sample` draws names from it for a preview, and `invented_in` flags names that read as made up by a language model
(Elara, Voss, Vaeryn Duskmere), the way Dungeon's naming.py does, so the wizards can refuse them.
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
# How many names a town's own group needs before it is a real spread rather than a handful.
MOST_SAMPLES = 40


@cache
def tables() -> tuple[dict, dict]:
    return (json.loads((DATA / 'names.json').read_text(encoding='utf-8')),
            json.loads((DATA / 'given_names.json').read_text(encoding='utf-8')))


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
    groups = banks().get(bank, {}) | (own.get('groups') or {})
    if own.get('mix'):
        mix = own['mix']
    elif own.get('groups'):
        mix = dict.fromkeys(own['groups'], 1.0)
    elif bank == era['bank'] and era['mix']:
        mix = era['mix']
    else:
        mix = {}
    mix = {key: weight for key, weight in mix.items() if weight > 0 and key in groups}
    return groups, mix or dict.fromkeys(groups, 1.0)


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
    """Names drawn the way the town's mix weighs its groups: {name, group}."""
    groups, mix = groups_for(city)
    rng = random.Random(seed)
    keys = list(mix)
    drawn = []
    for _ in range(min(count, MOST_SAMPLES)):
        key = rng.choices(keys, weights=[mix[key] for key in keys])[0]
        group = groups[key]
        drawn.append({'name': f"{given_from(group, rng)} {rng.choice(group['family'])}", 'group': key})
    return drawn


def spread(city: dict) -> dict:
    """How wide a town's names run: given and family names it can draw on, and from which groups."""
    groups, mix = groups_for(city)
    given, family = set(), set()
    for key in mix:
        group = groups[key]
        given.update([*group.get('feminine', []), *group.get('masculine', []), *group.get('neutral', [])])
        family.update(group['family'])
    return {'bank': bank_of(city.get('names'), city.get('era', 'modern')), 'given': len(given),
            'family': len(family), 'groups': [{'id': key, 'weight': mix[key], 'own': key in (city.get('names') or {}).get('groups', {})}
                                              for key in mix]}


def view(city: dict, seed: str = 'worldsmith') -> dict:
    """What the Names tab shows: the banks to pick from (each with its groups), the town's spread and samples."""
    return {'banks': {bank: sorted(groups) for bank, groups in banks().items()},
            'era_bank': eras().get(city.get('era', 'modern'), eras()['modern'])['bank'],
            'spread': spread(city), 'samples': sample(city, 12, seed)}


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
