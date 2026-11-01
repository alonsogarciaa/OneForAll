import pytest
from fastapi.testclient import TestClient

from djengine.app_paths import AppPaths
from djengine.server import Services, create_app
from djengine.settings import load_settings


@pytest.fixture
def paths(tmp_path):
    return AppPaths.from_root(tmp_path / "data")


@pytest.fixture
def client(paths):
    svc = Services(paths, load_settings(paths.settings_path), None, None, None, None, False)
    return TestClient(create_app(svc, token="t"))
