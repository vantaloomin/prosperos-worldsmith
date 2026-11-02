"""The vendored Dungeon format reads, checks and writes worlds the way Dungeon does."""
import json
from pathlib import Path

import pytest

from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.dungeon_format.schema import City

FIXTURES = Path(__file__).parent / 'fixtures'


def make_world(folder: Path) -> Path:
    """A small world folder with one region, settlement, faction and person, and a town's engine file."""
    files = {
        'world.json': {'schema_version': 1, 'id': 'testland', 'name': 'Testland', 'default_ruleset': 'marvel'},
        'regions.json': {'regions': [{'id': 'the-vale', 'name': 'The Vale'}]},
        'settlements.json': {'settlements': [{'id': 'kingswood', 'name': 'Kingswood', 'region': 'the-vale'}]},
        'factions.json': {'factions': [{'id': 'timber-guild', 'name': 'The Timber Guild'}]},
        'cast.json': {'cast': [{'id': 'aldous-marr', 'name': 'Aldous Marr', 'faction': 'timber-guild',
                                'settlement': 'kingswood', 'secret': 'In debt to the Guild.'}]},
        'engine/cities/kingswood.json': json.loads((FIXTURES / 'kingswood.json').read_text(encoding='utf-8')),
    }
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')
    (folder / 'canon').mkdir()
    (folder / 'canon' / 'overview.md').write_text('# Testland\n', encoding='utf-8')
    return folder


def test_a_world_folder_reads_and_validates(tmp_path):
    contents = packages.folder_contents(make_world(tmp_path / 'testland'))
    assert packages.validate(contents) == []
    assert ('cities', 'kingswood') in contents['engine']


def test_a_broken_reference_is_reported(tmp_path):
    folder = make_world(tmp_path / 'testland')
    (folder / 'cast.json').write_text(json.dumps({'cast': [{'id': 'nobody', 'name': 'Nobody',
                                                            'faction': 'no-such-faction'}]}), encoding='utf-8')
    with pytest.raises(DomainError, match='no-such-faction'):
        packages.folder_contents(folder)


def test_a_folder_without_world_json_is_refused(tmp_path):
    (tmp_path / 'empty').mkdir()
    with pytest.raises(DomainError):
        packages.folder_contents(tmp_path / 'empty')


def test_a_package_round_trips_through_sqlite_and_back_to_a_folder(tmp_path):
    contents = packages.folder_contents(make_world(tmp_path / 'testland'))
    path = packages.write(contents, tmp_path / 'testland.sqlite')
    again = packages.read(path)
    assert packages.fingerprint(again) == packages.fingerprint(contents)
    packages.export(path, tmp_path / 'out')
    assert packages.fingerprint(packages.folder_contents(tmp_path / 'out')) == packages.fingerprint(contents)


def test_hidden_truths_are_marked():
    assert packages.hidden('cast', {'id': 'a', 'secret': 'x'})
    assert not packages.hidden('cast', {'id': 'a'})


def test_a_dungeon_city_file_validates_against_the_vendored_schema():
    city = City.model_validate(json.loads((FIXTURES / 'kingswood.json').read_text(encoding='utf-8')))
    assert city.id == 'kingswood' and city.places
