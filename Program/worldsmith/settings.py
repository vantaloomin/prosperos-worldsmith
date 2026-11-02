"""Worldsmith's own settings, kept in one JSON file in the user's folder (WORLDSMITH_HOME overrides where).

- `dungeon_checkout`: a prosperos-dungeon checkout, whose built-in worlds Worldsmith can open and edit in place.
- `recent_folders`: world folders opened lately, newest first.
- `model`: which model drafts (worldsmith.models); its API key is in the system keyring, not here.
"""
import json
import os
from pathlib import Path

MOST_RECENT = 10


def home() -> Path:
    if os.environ.get('WORLDSMITH_HOME'):
        return Path(os.environ['WORLDSMITH_HOME'])
    if os.name == 'nt' and os.environ.get('APPDATA'):
        return Path(os.environ['APPDATA']) / 'ProsperoWorldsmith'
    return Path.home() / '.prosperos-worldsmith'


def path() -> Path:
    return home() / 'settings.json'


def load() -> dict:
    try:
        saved = json.loads(path().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        saved = {}
    saved = saved if isinstance(saved, dict) else {}
    recent = [item for item in saved.get('recent_folders') or [] if isinstance(item, str)]
    checkout = saved.get('dungeon_checkout')
    model = saved.get('model') if isinstance(saved.get('model'), dict) else {}
    return {'dungeon_checkout': checkout if isinstance(checkout, str) and checkout else None,
            'recent_folders': recent[:MOST_RECENT], 'model': model}


def save(settings: dict) -> dict:
    kept = load() | {key: settings[key] for key in ('dungeon_checkout', 'recent_folders', 'model') if key in settings}
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps(kept, indent=2) + '\n', encoding='utf-8')
    return load()


def remember_folder(folder: Path) -> dict:
    name = str(folder)
    recent = [name] + [item for item in load()['recent_folders'] if item != name]
    return save({'recent_folders': recent[:MOST_RECENT]})
