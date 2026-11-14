import os
import sys
import tempfile
from pathlib import Path

import pytest

# Import app against a disposable directory, not the user's installation.
os.environ['FUNK_DATA_DIR'] = tempfile.mkdtemp(prefix='funk-bot-tests-')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as service


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'DB', tmp_path / 'test.db')
    service.jobs.clear()
    service.init_db()
