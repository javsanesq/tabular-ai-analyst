import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("DATA_DIR", "/tmp/tabular_analyst_tests")
os.environ.setdefault("API_AUTH_TOKEN", "")

from tabular_analyst.main import app


@pytest.fixture()
def client():
    data_dir = Path(os.environ["DATA_DIR"])
    shutil.rmtree(data_dir, ignore_errors=True)
    with TestClient(app) as test_client:
        yield test_client

