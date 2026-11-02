"""scripts/sync_format.py copies Dungeon's format files, rewires their imports and reports drift."""
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / 'scripts' / 'sync_format.py'
spec = importlib.util.spec_from_file_location('sync_format', SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def fake_checkout(root: Path) -> Path:
    files = {
        'Program/dungeon/errors.py': 'class DomainError(Exception):\n    pass\n',
        'Program/dungeon/packages.py': 'from dungeon.errors import DomainError\n\nFORMAT = 1\n',
        'Program/dungeon/world/schema.py': 'from pydantic import BaseModel\n',
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding='utf-8')
    return root


def test_sync_copies_and_rewires_imports(tmp_path):
    checkout, target = fake_checkout(tmp_path / 'dungeon'), tmp_path / 'vendored'
    assert sync.main([str(checkout)], target=target) == 0
    text = (target / 'packages.py').read_text(encoding='utf-8')
    assert 'from worldsmith.dungeon_format.errors import DomainError' in text
    assert text.startswith('# Vendored from prosperos-dungeon Program/dungeon/packages.py')
    assert json.loads((target / 'SOURCE.json').read_text(encoding='utf-8'))['repo'] == 'vantaloomin/prosperos-dungeon'


def test_check_reports_drift_and_changes_nothing(tmp_path):
    checkout, target = fake_checkout(tmp_path / 'dungeon'), tmp_path / 'vendored'
    sync.main([str(checkout)], target=target)
    assert sync.main([str(checkout), '--check'], target=target) == 0
    (checkout / 'Program/dungeon/packages.py').write_text('FORMAT = 2\n', encoding='utf-8')
    assert sync.main([str(checkout), '--check'], target=target) == 1
    assert 'FORMAT = 1' in (target / 'packages.py').read_text(encoding='utf-8')


def test_an_import_of_an_unvendored_module_stops_the_sync(tmp_path):
    checkout = fake_checkout(tmp_path / 'dungeon')
    (checkout / 'Program/dungeon/packages.py').write_text('from dungeon.story import x\n', encoding='utf-8')
    with pytest.raises(SystemExit):
        sync.main([str(checkout)], target=tmp_path / 'vendored')


def test_the_vendored_files_match_their_source_list():
    source = json.loads((sync.TARGET / 'SOURCE.json').read_text(encoding='utf-8'))
    assert source['files'] == sync.FILES
    for name in sync.FILES.values():
        assert (sync.TARGET / name).is_file()
