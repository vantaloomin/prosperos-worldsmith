"""Dungeon's own code, run from the Dungeon checkout set in Settings, for the checks and previews the vendored
format cannot give: the strict city loader (catalog.prepare, which also knows the shared careers and name banks)
and the street map engine (townmap.build).

It runs the checkout's Python (Program/.venv, made by Dungeon's installer) in a separate process, with a scratch
data folder so nothing touches the player's real Dungeon data. Without a checkout or its .venv, these say what is
missing instead of guessing.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from worldsmith import settings
from worldsmith.dungeon_format.errors import DomainError, require

TIMEOUT = 120

# Read from stdin: {"task": "city", "city": {...}, "map": bool, "seed": str}. Writes one JSON object to stdout.
SCRIPT = r'''
import json, sys
task = json.load(sys.stdin)

def described(error):
    if hasattr(error, 'errors'):
        try:
            return [' > '.join(str(part) for part in item['loc']) + ': ' + item['msg'] for item in error.errors()]
        except Exception:
            pass
    return [str(error)]

from dungeon.world import catalog
out = {}
try:
    city = catalog.prepare(task['city'])
    out = {'ok': True, 'problems': []}
except Exception as error:
    out = {'ok': False, 'problems': described(error)}
if out['ok'] and task.get('map'):
    from dungeon import townmap
    if townmap.has_map(city):
        try:
            board = townmap.build(city, task.get('seed') or 'worldsmith')
            board['name'] = city['name']
            out['map'] = board
        except Exception as error:
            out['map_problem'] = described(error)[0]
    else:
        out['map_problem'] = 'This town has no street map (town_map style "none").'
print(json.dumps(out))
'''


def checkout() -> Path:
    found = settings.load().get('dungeon_checkout')
    require(bool(found), 'Set your Dungeon checkout first (World > Dungeon checkout) to check with Dungeon itself.', 409)
    return Path(found)


def python_in(root: Path) -> Path:
    """The checkout's own Python, made by Dungeon's installer (WORLDSMITH_DUNGEON_PYTHON overrides it)."""
    override = os.environ.get('WORLDSMITH_DUNGEON_PYTHON')
    if override:
        return Path(override)
    for candidate in (root / 'Program/.venv/Scripts/python.exe', root / 'Program/.venv/bin/python'):
        if candidate.is_file():
            return candidate
    raise DomainError(f'{root} has no Program/.venv yet. Run Windows\\install.bat in that Dungeon checkout once, then '
                      'try again.', 409)


def run(task: dict) -> dict:
    root = checkout()
    python = python_in(root)
    with tempfile.TemporaryDirectory(prefix='worldsmith-dungeon-') as scratch:
        env = os.environ | {'PYTHONPATH': str(root / 'Program'), 'DUNGEON_DATA_DIR': scratch,
                            'DUNGEON_DB': str(Path(scratch) / 'dungeon.sqlite3'), 'PYTHONIOENCODING': 'utf-8'}
        try:
            done = subprocess.run([str(python), '-c', SCRIPT], input=json.dumps(task), capture_output=True,
                                  text=True, encoding='utf-8', cwd=root / 'Program', env=env, timeout=TIMEOUT,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32'
                                  else 0)
        except subprocess.TimeoutExpired as error:
            raise DomainError('Dungeon took too long to check this town.', 504) from error
        except OSError as error:
            raise DomainError(f'Could not start Dungeon\'s Python: {error}', 502) from error
    lines = [line for line in done.stdout.splitlines() if line.startswith('{')]
    if done.returncode or not lines:
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ['no output']
        raise DomainError(f'Dungeon\'s check could not run: {tail[0]}', 502)
    return json.loads(lines[-1])


def check_city(city: dict, with_map: bool = False, seed: str = 'worldsmith') -> dict:
    """{"ok", "problems"} from Dungeon's strict loader, plus "map" (the street map board) when asked and it loads."""
    return run({'task': 'city', 'city': city, 'map': with_map, 'seed': seed})
