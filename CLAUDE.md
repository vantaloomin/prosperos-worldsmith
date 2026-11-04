# Prospero's Worldsmith

A companion app to Prospero's Dungeon (vantaloomin/prosperos-dungeon) for building worlds with AI help. It reads and
writes Dungeon's world folders and `.sqlite` world packages, so everything it makes loads in Dungeon unchanged.

- Layout mirrors Dungeon: the app lives in `Program/` (Python package `worldsmith/`, FastAPI on port 8795; React +
  Vite screen in `src/`, dev server 5187); `Windows/` holds only the double-click scripts.
- `worldsmith/dungeon_format/` is Dungeon's own code, vendored. Never edit it here: change it in Dungeon, then run
  `python scripts/sync_format.py <dungeon checkout>`. CI's `dungeon-format` job fails when Dungeon's main has moved on.
- The model never writes into a world directly: AI output becomes a draft the author approves.
- `worldsmith/cast_import.py` reads Dramatis's `prospero-cast` file (vantaloomin/prosperos-dramatis, `dramatis/casts.py`
  `export`): each side of the cast's outer square becomes one faction in a single `factions` draft.
- Before pushing, from `Program/`: `python -m ruff check .`, `python -m pytest -q`, `npm run build`.
- `main` takes changes through pull requests.
