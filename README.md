# Prospero's Worldsmith

A companion app to [Prospero's Dungeon](https://github.com/vantaloomin/prosperos-dungeon) for building out worlds:
towns, factions, people, quests and lore, drafted with AI help and approved by you, written in the exact world
format Dungeon loads.

Work in progress. Today it opens Dungeon's built-in worlds or any world folder, edits a town's files as forms
with Dungeon's own checks and undo, and drafts new places, people, quests and more with AI for you to approve.

## Models

Drafts come from the model you pick under "Brainstorm and drafts": Claude through Anthropic's API, any
OpenAI-compatible server (LM Studio, Ollama, OpenRouter), or the `claude` command line on your PC. API keys are kept
in Windows Credential Manager (the system keyring), not in a file.

## Checking with Dungeon, street maps and packages

- **Check with Dungeon** (a town's Town tab) runs the saved city file through Dungeon's own strict loader, and
  **Street map** draws it with Dungeon's map engine. Both run the code in your Dungeon checkout with its own Python
  (`Program\.venv`, made by Dungeon's `Windows\install.bat`). They use a scratch data folder, so your Dungeon saves
  are never touched.
- **Install into Dungeon** (an own world's overview) writes the world as one package into Dungeon's data folder
  (`packages\<id>.sqlite`), and Dungeon lists it under Worlds > World packages. It finds that folder the way Dungeon
  does: `%LOCALAPPDATA%\ProsperoDungeon`, or a portable `Data` folder in the checkout. `dungeon_data` in
  Worldsmith's settings.json overrides it. Built-in worlds are not installed: their changes are already in the
  checkout and ship with a Dungeon pull request.
- **Export .sqlite** writes the same package anywhere, to share. **World package** on the start screen unpacks one
  into a folder Worldsmith can open.

## Maps

- **Travel map** (left pane) and a town's **Map** tab are drawn maps you edit by hand. On the travel map, drag stops
  (this moves them on the world map), draw roads between them, and set each road's hours, terrain and danger. On a
  town's map, drag places between neighborhoods, and move neighborhoods (their lat/lon, which also anchors Dungeon's
  street map).
- **Interiors** (left pane) are the insides of keeps, caves, crypts and mines as rooms maps: rooms are boxes coloured
  by level, passages are links (open, door, stairs, ladder, shaft, crawl, water or secret, and locked, hidden or one
  way). Draw passages, drag rooms, add rooms and levels, pick the way in, or start a new interior at a travel-map
  stop. A save is checked with Dungeon's own interior schema first, so a room no passage reaches is refused. A
  room's summary, foes, hazard, loot and lore, and a passage's trap, are written in the file and kept by the map.
- Under each map is the same thing as **Mermaid text**, kept in step: paste it into any Mermaid viewer, or edit it
  and apply it back to the map.
- Saves keep the layout of Dungeon's files (the travel files keep one stop or road per line), so a Dungeon pull
  request shows only what changed.

## Running it on Windows

1. Install Python 3.12+ and Node 22+.
2. Double-click `Windows\install.bat` once (and again after updating).
3. Double-click `Windows\launch.bat`. Worldsmith opens at http://127.0.0.1:8795.

It runs alongside Dungeon (port 8785) without clashing.

## Staying in step with Dungeon

Worldsmith uses Dungeon's own world package code and city schema, copied into `Program/worldsmith/dungeon_format/`
with the Dungeon commit recorded in `SOURCE.json`. To update it:

```
cd Program
python scripts/sync_format.py "Z:\Coding Projects\prosperos-dungeon"
python -m pytest -q
```

CI checks the copy against Dungeon's latest `main` on every pull request and once a day.

## License

AGPL-3.0, like Dungeon.
