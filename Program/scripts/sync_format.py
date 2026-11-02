"""Copy Dungeon's world format into worldsmith/dungeon_format: `python scripts/sync_format.py DUNGEON_CHECKOUT`.

Worldsmith writes worlds Dungeon must load unchanged, so it uses Dungeon's own package code and city schema rather
than a rewrite, and Dungeon's own name tables (names.json, given_names.json) so towns draw names from the same banks. This script copies those files from a Dungeon checkout, points their `dungeon.` imports at the
vendored copies, and stamps SOURCE.json with the commit they came from.

`--check` changes nothing and exits 1 when the vendored files differ from the checkout's (CI runs it against
Dungeon's latest main to catch drift).
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
TARGET = HERE / 'worldsmith' / 'dungeon_format'
# Dungeon file (from the checkout's root) -> vendored module name.
FILES = {
    'Program/dungeon/errors.py': 'errors.py',
    'Program/dungeon/packages.py': 'packages.py',
    'Program/dungeon/world/schema.py': 'schema.py',
}
# Dungeon data files copied as they are, into data/: the name tables Dungeon draws townsfolk and NPC names from.
DATA = {
    'Program/dungeon/world/data/names.json': 'data/names.json',
    'Program/dungeon/world/data/given_names.json': 'data/given_names.json',
}
# Dungeon module -> vendored module, for imports inside the copied files.
MODULES = {'dungeon.errors': 'errors', 'dungeon.packages': 'packages', 'dungeon.world.schema': 'schema'}
IMPORT = re.compile(r'^from (dungeon(?:\.\w+)*) import', re.M)
HEADER = '# Vendored from prosperos-dungeon {path} by scripts/sync_format.py. Edit it there, then sync.\n'


def vendored(text: str, path: str) -> str:
    """A Dungeon file as the vendored copy holds it: a header, and its imports pointed at the other copies."""
    def swap(match: re.Match) -> str:
        module = match.group(1)
        if module not in MODULES:
            raise SystemExit(f'{path} imports {module}, which is not vendored. Add it to FILES and MODULES.')
        return f'from worldsmith.dungeon_format.{MODULES[module]} import'
    return HEADER.format(path=path) + IMPORT.sub(swap, text)


def commit_of(checkout: Path) -> str:
    try:
        return subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return 'unknown'


def wanted(checkout: Path) -> dict[str, str]:
    found = {}
    for source, name in FILES.items():
        path = checkout / source
        if not path.is_file():
            raise SystemExit(f'{path} is missing. Is {checkout} a prosperos-dungeon checkout?')
        found[name] = vendored(path.read_text(encoding='utf-8'), source)
    for source, name in DATA.items():
        path = checkout / source
        if not path.is_file():
            raise SystemExit(f'{path} is missing. Is {checkout} a prosperos-dungeon checkout?')
        found[name] = path.read_text(encoding='utf-8')
    return found


def differences(found: dict[str, str], target: Path) -> list[str]:
    return [name for name, text in found.items()
            if not (target / name).is_file() or (target / name).read_text(encoding='utf-8') != text]


def main(argv: list[str] | None = None, target: Path = TARGET) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('checkout', type=Path, help='a prosperos-dungeon checkout')
    parser.add_argument('--check', action='store_true', help='report drift and change nothing')
    args = parser.parse_args(argv)
    found = wanted(args.checkout)
    changed = differences(found, target)
    if args.check:
        if changed:
            print(f'Dungeon\'s format has moved on: {", ".join(changed)}. Run scripts/sync_format.py and check the tests.')
            return 1
        print('The vendored format matches this Dungeon checkout.')
        return 0
    target.mkdir(parents=True, exist_ok=True)
    for name, text in found.items():
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(text, encoding='utf-8', newline='\n')
    source = {'repo': 'vantaloomin/prosperos-dungeon', 'commit': commit_of(args.checkout), 'files': FILES | DATA}
    (target / 'SOURCE.json').write_text(json.dumps(source, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Synced {len(found)} files ({", ".join(changed) or "no changes"}).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
