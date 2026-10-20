import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_replay_admission(monkeypatch):
    import server
    from replay_admission import ReplayAdmission
    monkeypatch.setattr(server, 'replay_admission', ReplayAdmission())
