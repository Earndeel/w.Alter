import base64
import json
import os
import time
from unittest.mock import patch

import pytest

from walter_secrets import grants


def jwt(exp):
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"h.{body}.s"


@pytest.fixture
def home(tmp_path, monkeypatch):
    acc = tmp_path / "accounts"
    acc.mkdir()
    monkeypatch.setenv("WALTER_GRANTS_DIR", str(acc))
    return tmp_path


def card(home, ident, text):
    (home / "accounts" / f"{ident}.toml").write_text(text)


def private(path, text):
    old = os.umask(0o077)
    try:
        path.write_text(text)
    finally:
        os.umask(old)


def test_cards_are_validated(home):
    card(home, "bad", 'owner = "walter"\nkind = "magic"\n[secret]\ntoken = "file:/x"\n')
    with pytest.raises(grants.GrantError):
        grants.card("bad")
    card(home, "bad", 'owner = "walter"\nkind = "bot"\n[secret]\ntoken = "http://x"\n')
    with pytest.raises(grants.GrantError):
        grants.card("bad")
    with pytest.raises(grants.GrantError):
        grants.card("../escape")


def test_file_and_json_key_storage(home):
    private(home / "key.txt", "fake-key-not-live\n")
    private(home / "session.json", json.dumps({"tokens": {"account_id": "acct-1"}}))
    card(home, "k", f'owner = "walter"\nkind = "api_key"\n[secret]\ntoken = "file:{home}/key.txt"\n'
                    f'[attributes]\naccount = "file:{home}/session.json#tokens.account_id"\n')
    assert grants.access("k") == "fake-key-not-live"
    assert grants.attribute("k", "account") == "acct-1"
    with pytest.raises(grants.GrantError):
        grants.attribute("k", "missing")


def test_oauth_is_refreshed_only_by_its_renewer(home):
    private(home / "tok.json", json.dumps({"refresh_token": "r", "access_token": "old", "expires_at": time.time() - 5}))
    private(home / "client.json", json.dumps({"web": {"client_id": "c", "client_secret": "s"}}))
    text = (f'owner = "owner"\nkind = "oauth"\nrenewer = "walter-secrets"\n[secret]\ntoken = "file:{home}/tok.json"\n'
            f'client = "file:{home}/client.json#web"\n')
    card(home, "g", text)

    class R:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "fresh", "expires_in": 3600}
    with patch("httpx.post", return_value=R()) as post:
        assert grants.access("g") == "fresh"
        assert grants.access("g") == "fresh"          # cached until it nears expiry
        assert post.call_count == 1
    saved = json.loads((home / "tok.json").read_text())
    assert saved["refresh_token"] == "r" and oct((home / "tok.json").stat().st_mode & 0o777) == "0o600"
    assert json.loads(grants.access("g", "client")) == {"client_id": "c", "client_secret": "s"}
    assert grants.location("g") == home / "tok.json"
    private(home / "tok.json", json.dumps({"refresh_token": "r", "access_token": "old", "expires_at": 0}))
    card(home, "g", text.replace('renewer = "walter-secrets"', 'renewer = "vendor:other"'))
    with pytest.raises(grants.GrantError):
        grants.access("g")


def test_subscription_session_expiry(home):
    private(home / "auth.json", json.dumps({"tokens": {"access_token": jwt(time.time() + 7200)}}))
    card(home, "s", f'owner = "walter"\nkind = "subscription"\n[secret]\ntoken = "file:{home}/auth.json#tokens.access_token"\n')
    assert grants.access("s").startswith("h.")
    private(home / "auth.json", json.dumps({"tokens": {"access_token": jwt(time.time() - 10)}}))
    with pytest.raises(grants.GrantError):
        grants.access("s")


def test_vault_storage_is_audited(home):
    class V:
        def value(self, ref, field):
            assert (ref, field) == ("W.Alter · telegram", "bot_token")
            return "fake-bot-token"

        def find(self, ref):
            return {"id": "1", "name": ref}
    audited = []
    card(home, "bot", 'owner = "walter"\nkind = "bot"\n[secret]\ntoken = "vault:W.Alter · telegram#bot_token"\n')
    with patch("walter_secrets.vault.VAULT", V()), patch("walter_secrets.vault.audit", lambda *a, **k: audited.append(k)):
        assert grants.access("bot") == "fake-bot-token"
    assert audited == [{"grant": "bot"}]


def test_check_reports_metadata_only(home):
    (home / "open.txt").write_text("fake-key-not-live")
    (home / "open.txt").chmod(0o644)
    card(home, "k", f'owner = "walter"\nkind = "api_key"\n[secret]\ntoken = "file:{home}/open.txt"\n')
    card(home, "x", 'owner = "owner"\nkind = "cookies"\n[secret]\ntoken = "external:Brave profile on the Mac"\n')
    out = grants.check()
    assert not out["ok"]
    rows = {r["id"]: r for r in out["grants"]}
    assert rows["k"]["problems"] == ["token: readable by others"]
    assert rows["x"]["ok"]
    assert "fake-key-not-live" not in json.dumps(out)
    with pytest.raises(grants.GrantError):
        grants.access("x")


def claude_card(home):
    card(home, "claude", f'owner = "owner"\nkind = "subscription"\nprovider = "anthropic-claude"\n'
         f'renewer = "walter-secrets"\n[secret]\ntoken = "file:{home}/claude.json#claudeAiOauth.accessToken"\n')


def test_claude_opaque_tokens_refresh_atomically_without_cli_or_secret_disclosure(home):
    claude_card(home)
    private(home / "claude.json", json.dumps({"claudeAiOauth": {
        "accessToken": "fake-old", "refreshToken": "fake-refresh", "expiresAt": 0,
        "scopes": ["user:inference", "user:profile"], "subscriptionType": "pro"}}))
    class Response:
        status_code = 200
        def json(self):
            return {"access_token": "fake-new", "refresh_token": "fake-rotated", "expires_in": 7200}
    with patch("httpx.post", return_value=Response()) as post, patch("subprocess.run") as cli:
        assert grants.access("claude") == "fake-new"
        assert grants.access("claude") == "fake-new"
        assert post.call_count == 1 and not cli.called
    saved = json.loads((home / "claude.json").read_text())["claudeAiOauth"]
    assert saved["refreshToken"] == "fake-rotated" and saved["subscriptionType"] == "pro"
    assert (home / "claude.json").stat().st_mode & 0o777 == 0o600
    health = grants.check("claude")
    assert health["ok"] and health["grants"][0]["refreshable"]
    assert "fake-" not in json.dumps(health)


def test_claude_refresh_failure_preserves_the_existing_file(home):
    claude_card(home)
    private(home / "claude.json", json.dumps({"claudeAiOauth": {
        "accessToken": "fake-old", "refreshToken": "fake-refresh", "expiresAt": 0}}))
    before = (home / "claude.json").read_bytes()
    with patch("httpx.post", return_value=type("R", (), {"status_code": 401})()):
        with pytest.raises(grants.GrantError, match="HTTP 401"):
            grants.access("claude")
    assert (home / "claude.json").read_bytes() == before


def _api_card(home, ident="provider", allow='["llm", "router"]'):
    private(home / "key", "k-123")
    private(home / "acct", "acct-1")
    card(home, ident, f'owner = "walter"\nkind = "api_key"\nallow = {allow}\n'
                      f'[secret]\ntoken = "file:{home / "key"}"\n[attributes]\naccount = "file:{home / "acct"}"\n'
                      '[env]\nPROVIDER_KEY = "token"\nPROVIDER_ACCOUNT = "attribute:account"\n')
    grants._values.clear()


def test_allow_names_the_reader_and_refuses_others(home):
    _api_card(home)
    assert grants.access("provider", consumer="llm") == "k-123"
    for reader in (None, "memory"):
        with pytest.raises(grants.GrantError):
            grants.access("provider", consumer=reader)


def test_env_value_resolves_declared_names_without_fallback(home, monkeypatch):
    _api_card(home)
    monkeypatch.setenv("UNDECLARED_KEY", "from-env")
    assert grants.env_value("PROVIDER_KEY", "router") == "k-123"
    assert grants.env_value("PROVIDER_ACCOUNT", "router") == "acct-1"
    with pytest.raises(grants.GrantError):
        grants.env_value("PROVIDER_KEY", "telegram")
    with pytest.raises(grants.GrantError):          # the environment is never a fallback
        grants.env_value("UNDECLARED_KEY", "router")


def test_environment_injects_only_the_named_grants(home):
    _api_card(home)
    _api_card(home, "other", '["llm"]')
    assert grants.environment(["provider"], "router") == {"PROVIDER_KEY": "k-123", "PROVIDER_ACCOUNT": "acct-1"}
    with pytest.raises(grants.GrantError):
        grants.environment(["other"], "router")


def test_env_must_point_to_a_declared_part(home):
    card(home, "broken", 'owner = "walter"\nkind = "api_key"\n[secret]\ntoken = "file:/x"\n[env]\nX = "missing"\n')
    with pytest.raises(grants.GrantError):
        grants.card("broken")
