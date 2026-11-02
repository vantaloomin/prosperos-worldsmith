"""World package files (.sqlite), in Dungeon's own format (dungeon_format/packages.py).

Export writes the open world, folder and town engine data together, as one file to share. Install writes that file
straight into Dungeon's data folder (packages/<id>.sqlite), where Dungeon lists it under Worlds > World packages
as an imported world. Only an own world is installed: a built-in world's package is rebuilt by Dungeon from the
shipped folder, so its changes go in through the Dungeon checkout instead. Import goes the other way: a package
file becomes a world folder Worldsmith can open and edit.
"""
import os
import sys
from pathlib import Path

from worldsmith import settings, worlds
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import require


def contents_of(opened: worlds.Opened) -> dict:
    """The world as a package holds it, checked the way Dungeon checks it (raises with its problems)."""
    contents = packages.folder_contents(opened.folder)
    if opened.data:
        contents['engine'] = worlds.engine_for(opened.data, contents['world']['id']) | contents['engine']
    return contents


def default_path(world_id: str) -> Path:
    return settings.home() / 'exports' / f'{world_id}.sqlite'


def dungeon_data() -> Path:
    """Dungeon's data folder, found the way Dungeon finds it (dungeon/identity.py data_dir): Settings' choice, else
    a portable Data folder beside the checkout's Program, else the user's app-data folder."""
    chosen = settings.load().get('dungeon_data')
    if chosen:
        return Path(chosen).expanduser()
    checkout = settings.load().get('dungeon_checkout')
    if checkout and (Path(checkout) / 'Data').is_dir():
        return Path(checkout) / 'Data'
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') / 'ProsperoDungeon'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'ProsperoDungeon'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'prospero-dungeon'


def install_world(opened: worlds.Opened) -> dict:
    require(opened.kind == 'folder', 'A built-in world is already in your Dungeon checkout; its changes ship with Dungeon.',
            409)
    world_id = str(packages.read_json(opened.folder / 'world.json').get('id') or '')
    checkout = settings.load().get('dungeon_checkout')
    builtin = {item['id'] for item in worlds.builtin_worlds(Path(checkout))} if checkout else set()
    require(world_id not in builtin, f'{world_id} is the id of a built-in world: give your world its own id first.', 409)
    return export_world(opened, str(dungeon_data() / packages.FOLDER / f'{world_id}.sqlite'))


def export_world(opened: worlds.Opened, to: str | None = None) -> dict:
    contents = contents_of(opened)
    path = Path(to).expanduser() if to else default_path(contents['world']['id'])
    if path.suffix.lower() != '.sqlite':
        # A folder (or a name with no extension) gets <world id>.sqlite inside it.
        path = path / f'{contents["world"]["id"]}.sqlite' if path.is_dir() or not path.suffix else \
            path.with_suffix('.sqlite')
    packages.write(contents, path)
    return {'path': str(path), **packages.summary(path)}


def import_package(package: str, folder: str) -> worlds.Opened:
    source = Path(package).expanduser()
    target = Path(folder).expanduser()
    require(source.suffix.lower() == '.sqlite', 'Pick a world package file (.sqlite).', 422)
    packages.export(source, target)
    settings.remember_folder(target)
    return worlds.folder(target)
