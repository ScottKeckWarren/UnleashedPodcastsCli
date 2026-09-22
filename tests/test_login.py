"""`unleashed login` and `unleashed whoami`: the browser handshake and what it writes."""

import hashlib
import json
import threading
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
import respx

from unleashed import auth
from unleashed.cli import cli
from unleashed.config import load_config
from unleashed.errors import AuthError, ExitCode, ValidationError

API = "https://example.test/apiv1"
TOKEN_URL = f"{API}/cli/token"


def invoke(runner, args):
    return runner.invoke(cli, args, catch_exceptions=False)


class FakeBrowser:
    """Plays the user's browser: reads the authorize URL and hits the loopback listener.

    It has to answer from another thread, because the CLI only starts serving the
    listener after it has opened the browser.
    """

    def __init__(self, answer=None, *, opens=True):
        self.answer = answer
        self.opens = opens
        self.url = None
        self.thread = None

    @property
    def query(self):
        return parse_qs(urlsplit(self.url).query)

    def open(self, url):
        self.url = url
        self.thread = threading.Thread(target=self._redirect, daemon=True)
        self.thread.start()
        return self.opens

    def _redirect(self):
        query = self.query
        params = self.answer(query) if self.answer else {"code": "the-code"}
        params.setdefault("state", query["state"][0])
        redirect = query["redirect_uri"][0]
        urllib.request.urlopen(f"{redirect}?{urlencode(params)}", timeout=5).read()


@pytest.fixture
def browser(monkeypatch):
    def install(answer=None, *, opens=True):
        fake = FakeBrowser(answer, opens=opens)
        monkeypatch.setattr("unleashed.cli.webbrowser.open", fake.open)
        return fake

    return install


@pytest.fixture
def token_endpoint():
    with respx.mock:
        yield respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(200, json={"token": "7|minted", "token_type": "Bearer"})
        )


# --- the whole flow ----------------------------------------------------------


def test_login_writes_the_minted_token_to_the_home_config(runner, home, browser, token_endpoint):
    browser()
    result = invoke(runner, ["login", "--api-url", API])
    assert result.exit_code == ExitCode.SUCCESS, result.output
    config = load_config({})
    assert config.token == "7|minted"
    assert config.base_url == API
    assert str(home / ".unleashed" / "config") in result.output


def test_login_redeems_the_code_with_the_verifier_behind_the_hash(runner, browser, token_endpoint):
    fake = browser()
    invoke(runner, ["login", "--api-url", API])
    sent = json.loads(token_endpoint.calls.last.request.content)
    assert sent["code"] == "the-code"
    digest = hashlib.sha256(sent["verifier"].encode()).hexdigest()
    assert fake.query["verifier_hash"] == [digest]


def test_login_never_sends_the_verifier_to_the_browser(runner, browser, token_endpoint):
    fake = browser()
    invoke(runner, ["login", "--api-url", API])
    verifier = json.loads(token_endpoint.calls.last.request.content)["verifier"]
    assert verifier not in fake.url


def test_login_opens_the_site_rather_than_the_api(runner, browser, token_endpoint):
    fake = browser()
    invoke(runner, ["login", "--api-url", API])
    assert fake.url.startswith("https://example.test/cli/authorize?")


def test_login_redirects_to_a_loopback_listener(runner, browser, token_endpoint):
    fake = browser()
    invoke(runner, ["login", "--api-url", API])
    redirect = urlsplit(fake.query["redirect_uri"][0])
    assert redirect.scheme == "http"
    assert redirect.hostname == "127.0.0.1"
    assert redirect.port >= 1024


def test_login_asks_for_every_ability_by_default(runner, browser, token_endpoint):
    fake = browser()
    invoke(runner, ["login", "--api-url", API])
    assert fake.query["abilities[]"] == list(auth.ABILITIES)


def test_login_can_narrow_the_abilities(runner, browser, token_endpoint):
    fake = browser()
    invoke(runner, ["login", "--api-url", API, "--ability", "episodes:read"])
    assert fake.query["abilities[]"] == ["episodes:read"]


def test_login_names_the_device(runner, browser, token_endpoint):
    fake = browser()
    invoke(runner, ["login", "--api-url", API, "--device-name", "studio-mac"])
    assert fake.query["device_name"] == ["studio-mac"]


def test_login_defaults_the_device_to_the_hostname(runner, browser, token_endpoint, monkeypatch):
    monkeypatch.setattr("unleashed.cli.socket.gethostname", lambda: "scotts-laptop")
    fake = browser()
    invoke(runner, ["login", "--api-url", API])
    assert fake.query["device_name"] == ["scotts-laptop"]


def test_login_rejects_a_blank_device_name(runner, browser):
    browser()
    result = invoke(runner, ["login", "--api-url", API, "--device-name", "  "])
    assert result.exit_code == ExitCode.USAGE


def test_login_writes_a_named_profile_and_leaves_others(
    runner, configured, browser, token_endpoint
):
    browser()
    invoke(runner, ["login", "--profile", "client-a", "--api-url", API])
    assert load_config({}, profile="client-a").token == "7|minted"
    assert load_config({}).token == "tok-123"


def test_login_honours_the_global_profile(runner, browser, token_endpoint):
    browser()
    invoke(runner, ["--profile", "client-b", "login", "--api-url", API])
    assert load_config({}, profile="client-b").token == "7|minted"


def test_login_local_writes_into_the_working_directory(runner, work, browser, token_endpoint):
    browser()
    invoke(runner, ["login", "--local", "--api-url", API])
    assert (work / ".unleashed" / "config").exists()


def test_login_reuses_the_profiles_api_url(runner, configured, browser, token_endpoint):
    fake = browser()
    result = invoke(runner, ["login"])
    assert result.exit_code == ExitCode.SUCCESS
    assert fake.url.startswith("https://example.test/cli/authorize")


def test_login_falls_back_to_the_environment_url(runner, browser, token_endpoint):
    fake = browser()
    result = runner.invoke(cli, ["login"], obj={"env": {"UNLEASHED_API_URL": API}})
    assert result.exit_code == ExitCode.SUCCESS
    assert fake.url.startswith("https://example.test/cli/authorize")


def test_login_defaults_to_production(runner, browser):
    fake = browser()
    with respx.mock:
        respx.post(f"{auth.DEFAULT_API_URL}/cli/token").mock(
            return_value=httpx.Response(200, json={"token": "7|prod"})
        )
        invoke(runner, ["login"])
    assert fake.url.startswith("https://unleashedpodcasts.com/cli/authorize")


def test_login_prints_the_url_when_the_browser_does_not_open(runner, browser, token_endpoint):
    fake = browser(opens=False)
    result = invoke(runner, ["login", "--api-url", API])
    assert "Open this URL" in result.output
    assert fake.url in result.output


def test_login_never_prints_the_token(runner, browser, token_endpoint):
    browser()
    result = invoke(runner, ["login", "--api-url", API])
    assert "7|minted" not in result.output


def test_login_no_browser_skips_the_browser(runner, monkeypatch, token_endpoint):
    def refuse(_url):
        raise AssertionError("the browser must not open")

    monkeypatch.setattr("unleashed.cli.webbrowser.open", refuse)
    monkeypatch.setattr(auth, "DEFAULT_WAIT_SECONDS", 0.2)
    result = invoke(runner, ["login", "--api-url", API, "--no-browser"])
    assert "Open this URL" in result.output
    assert result.exit_code == ExitCode.AUTH


# --- failures ----------------------------------------------------------------


def test_login_denied_in_the_browser_exits_four_and_writes_nothing(runner, home, browser):
    browser(lambda _q: {"error": "access_denied"})
    result = invoke(runner, ["login", "--api-url", API])
    assert result.exit_code == ExitCode.AUTH
    assert "denied" in result.output
    assert not (home / ".unleashed" / "config").exists()


def test_login_rejects_a_redirect_for_another_attempt(runner, home, browser, token_endpoint):
    browser(lambda _q: {"code": "c", "state": "someone-elses"})
    result = invoke(runner, ["login", "--api-url", API])
    assert result.exit_code == ExitCode.AUTH
    assert not token_endpoint.called
    assert not (home / ".unleashed" / "config").exists()


def test_login_reports_a_failed_exchange(runner, home, browser):
    browser()
    with respx.mock:
        respx.post(TOKEN_URL).mock(
            return_value=httpx.Response(400, json={"message": "This authorization code is bad."})
        )
        result = invoke(runner, ["login", "--api-url", API])
    assert result.exit_code == ExitCode.AUTH
    assert "authorization code" in result.output
    assert not (home / ".unleashed" / "config").exists()


def test_login_times_out_waiting_for_the_browser(runner, monkeypatch):
    monkeypatch.setattr("unleashed.cli.webbrowser.open", lambda _url: True)
    monkeypatch.setattr(auth, "DEFAULT_WAIT_SECONDS", 0.2)
    result = invoke(runner, ["login", "--api-url", API])
    assert result.exit_code == ExitCode.AUTH
    assert "Gave up waiting" in result.output


# --- the pieces --------------------------------------------------------------


def test_site_url_strips_the_api_prefix():
    assert auth.site_url("http://localhost:8018/apiv1/") == "http://localhost:8018"


def test_site_url_falls_back_to_the_origin():
    assert auth.site_url("https://example.test/api/v9") == "https://example.test"


def test_handshake_verifier_hash_is_a_sha256_hex_digest():
    handshake = auth.Handshake(verifier="secret", state="s")
    assert handshake.verifier_hash == hashlib.sha256(b"secret").hexdigest()


def test_handshake_secrets_are_fresh_each_time():
    assert auth.Handshake().verifier != auth.Handshake().verifier


def test_handshake_never_shows_its_secrets():
    handshake = auth.Handshake()
    assert handshake.verifier not in repr(handshake)


def test_code_from_rejects_an_unknown_error():
    handshake = auth.Handshake()
    with pytest.raises(auth.LoginError, match="server_error"):
        auth.code_from({"state": handshake.state, "error": "server_error"}, handshake)


def test_code_from_rejects_a_missing_code():
    handshake = auth.Handshake()
    with pytest.raises(auth.LoginError, match="no authorization code"):
        auth.code_from({"state": handshake.state}, handshake)


def test_listener_ignores_other_paths():
    with auth.LoopbackListener() as listener:
        port = urlsplit(listener.redirect_uri).port

        def stray_then_callback():
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(f"http://127.0.0.1:{port}/favicon.ico", timeout=5)
            urllib.request.urlopen(f"{listener.redirect_uri}?code=c&state=s", timeout=5).read()

        thread = threading.Thread(target=stray_then_callback, daemon=True)
        thread.start()
        assert listener.wait(5) == {"code": "c", "state": "s"}
        thread.join(5)


@respx.mock
def test_exchange_maps_a_validation_failure():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(422, json={"errors": {}}))
    with pytest.raises(ValidationError):
        auth.exchange(API, "c", "v")


@respx.mock
def test_exchange_rejects_a_body_without_a_token():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, text="<html>login</html>"))
    with pytest.raises(auth.ApiError, match="without a token"):
        auth.exchange(API, "c", "v")


@respx.mock
def test_exchange_reports_an_unreachable_api():
    respx.post(TOKEN_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(auth.ApiError, match="Could not reach"):
        auth.exchange(API, "c", "v")


@respx.mock
def test_exchange_sends_no_bearer_token():
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"token": "7|t"}))
    auth.exchange(API, "c", "v")
    assert "Authorization" not in route.calls.last.request.headers


@respx.mock
def test_exchange_treats_a_bad_code_as_an_auth_failure():
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(400, json={"message": "bad"}))
    with pytest.raises(AuthError):
        auth.exchange(API, "c", "v")


# --- whoami ------------------------------------------------------------------


@respx.mock
def test_whoami_shows_the_tokens_user(runner, configured):
    route = respx.get(f"{API}/whoami").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "uuid": "u-1",
                    "name": "Scott",
                    "email": "scott@example.test",
                    "token": {"device_name": "laptop", "abilities": ["episodes:read"]},
                }
            },
        )
    )
    result = invoke(runner, ["whoami", "--output", "json"])
    assert result.exit_code == ExitCode.SUCCESS
    assert json.loads(result.output)["token"]["abilities"] == ["episodes:read"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-123"


@respx.mock
def test_whoami_with_a_dead_token_suggests_login(runner, configured):
    respx.get(f"{API}/whoami").mock(return_value=httpx.Response(401, json={}))
    result = invoke(runner, ["whoami"])
    assert result.exit_code == ExitCode.AUTH
    assert "unleashed login" in result.output


@respx.mock
def test_whoami_supports_query(runner, configured):
    respx.get(f"{API}/whoami").mock(
        return_value=httpx.Response(200, json={"data": {"email": "scott@example.test"}})
    )
    result = invoke(runner, ["whoami", "--query", "email", "--output", "text"])
    assert result.output.strip() == "scott@example.test"


@respx.mock
def test_whoami_warns_about_an_exposed_config(runner, configured):
    configured.chmod(0o644)
    respx.get(f"{API}/whoami").mock(return_value=httpx.Response(200, json={"data": {}}))
    result = invoke(runner, ["whoami"])
    assert "readable by other users" in result.output


# --- abilities ---------------------------------------------------------------


@respx.mock
def test_a_missing_ability_exits_eight_and_says_why(runner, configured):
    respx.get(f"{API}/episodes/x").mock(
        return_value=httpx.Response(403, json={"message": "Invalid ability provided."})
    )
    result = invoke(runner, ["episodes", "get", "x"])
    assert result.exit_code == ExitCode.FORBIDDEN
    assert "does not grant" in result.output
