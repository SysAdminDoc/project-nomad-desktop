"""Shared fixtures for NOMAD Field Desk API tests."""

import os
import sys
import uuid
import shutil
from pathlib import Path

import pytest

# Ensure project root is on sys.path so imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TEST_TMP_ROOT = Path(PROJECT_ROOT) / "test_runtime"
TEST_TMP_ROOT.mkdir(exist_ok=True)

@pytest.fixture()
def app():
    """Create a Flask app backed by a temporary SQLite database."""
    db_uri = f'file:nomad_test_{uuid.uuid4().hex}?mode=memory&cache=shared'
    data_dir = TEST_TMP_ROOT / f'nomad_data_{uuid.uuid4().hex}'
    data_dir.mkdir()
    keeper = None

    # Point config at temp directory before any imports touch it
    import config
    config._config_cache = {'db_path': db_uri, 'data_dir': str(data_dir)}
    config._config_mtime = float('inf')  # prevent re-read from disk

    # Keep one connection open so the shared in-memory database persists
    import sqlite3
    keeper = sqlite3.connect(db_uri, uri=True)

    # Initialize the DB schema in the shared in-memory database
    from db import init_db
    init_db()

    # Create the Flask app
    from web.app import create_app
    application = create_app()
    application.config['TESTING'] = True

    yield application

    if keeper is not None:
        keeper.close()
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def db(app):
    """Direct DB connection for seeding test data."""
    from db import get_db
    conn = get_db()
    yield conn
    conn.close()
