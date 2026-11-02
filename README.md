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
