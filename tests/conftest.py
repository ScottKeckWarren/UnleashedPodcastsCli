import pytest
from click.testing import CliRunner

from unleashed.config import Config


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Never read the developer's real ~/.unleashed/config during a test run."""
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("UNLEASHED_API_URL", raising=False)
    monkeypatch.delenv("UNLEASHED_API_TOKEN", raising=False)
    monkeypatch.delenv("UNLEASHED_PROFILE", raising=False)
    monkeypatch.chdir(work)
    return home, work


@pytest.fixture
def home(isolated_home):
    return isolated_home[0]


@pytest.fixture
def work(isolated_home):
    return isolated_home[1]


def write_config(directory, body):
    """Write a config file into <directory>/.unleashed/config."""
    path = directory / ".unleashed" / "config"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    path.chmod(0o600)
    return path


@pytest.fixture
def home_config(home):
    def _write(body):
        return write_config(home, body)

    return _write


@pytest.fixture
def local_config(work):
    def _write(body, directory=None):
        return write_config(directory or work, body)

    return _write


@pytest.fixture
def configured(home_config):
    """The ordinary case: one home config with a default profile."""
    return home_config("[default]\napi_url = https://example.test/apiv1\napi_token = tok-123\n")


@pytest.fixture
def config():
    return Config(base_url="https://example.test/apiv1", token="tok-123")


@pytest.fixture
def env():
    return {
        "UNLEASHED_API_URL": "https://example.test/apiv1",
        "UNLEASHED_API_TOKEN": "tok-123",
    }


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def episode_payload():
    return {
        "data": {
            "uuid": "ep-uuid-1",
            "podcast_uuid": "pod-uuid-1",
            "podcast_name": "The Example Show",
            "name": "Episode 101",
            "target_published_date": "2026-09-15",
            "actual_published_date": None,
            "status": "Draft",
            "is_published": False,
            "description": "Show notes here.",
            "canonical_url": None,
            "cover_art_file_id": None,
            "transcript_status": None,
        }
    }
