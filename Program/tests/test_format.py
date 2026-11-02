"""The vendored Dungeon format reads, checks and writes worlds the way Dungeon does."""
import json

import pytest

from tests.conftest import FIXTURES, make_world
from worldsmith.dungeon_format import packages
from worldsmith.dungeon_format.errors import DomainError
from worldsmith.dungeon_format.schema import City


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
