"""The server answers on /api and serves the built screen for everything else."""
from fastapi.testclient import TestClient

from worldsmith.main import create_app


def test_health():
    response = TestClient(create_app()).get('/api/health')
    assert response.status_code == 200 and response.json()['ok']


def test_format_names_the_dungeon_commit_and_package_parts():
    data = TestClient(create_app()).get('/api/format').json()
    assert data['repo'] == 'vantaloomin/prosperos-dungeon' and len(data['commit']) >= 7
    assert 'cast' in data['sections'] and 'cities' in data['engine_kinds']


def test_the_built_screen_is_served_with_a_fallback_to_index(tmp_path):
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<div id="root"></div>', encoding='utf-8')
    client = TestClient(create_app(dist=tmp_path))
    assert 'root' in client.get('/').text
    assert 'root' in client.get('/towns/kingswood').text
    assert client.get('/../pyproject.toml').status_code in (200, 404)
    assert 'worldsmith' not in client.get('/../pyproject.toml').text
