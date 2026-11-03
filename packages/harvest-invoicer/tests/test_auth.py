"""Tests for auth.py: OIDC login against a tiny in-process provider.

The provider is a real HTTP server on loopback (discovery, JWKS, token and
userinfo endpoints) that signs ID tokens with a freshly generated RSA key,
so the app goes through Authlib's full path: discovery, PKCE, state and
nonce, signature and claim validation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask, jsonify, request
from harvest_invoicer import db as state_db
from harvest_invoicer.app import create_app
from harvest_invoicer.auth import safe_next
from harvest_invoicer.config import OidcSettings
from harvest_invoicer.model import InvoiceLine
from joserfc import jwt
from joserfc.jwk import RSAKey
from werkzeug.serving import make_server

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    from flask.testing import FlaskClient
    from werkzeug.test import TestResponse

_CLIENT_ID = "invoicer"
_CLIENT_SECRET = "client-secret"  # noqa: S105 — test fixture
_SESSION_SECRET = "s" * 32


class Provider:
    """A minimal OpenID provider: just enough of the code flow for the app."""

    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "test-key"})
        self.codes: dict[str, dict[str, Any]] = {}
        self.userinfo: dict[str, Any] = {}
        self.issuer = ""
        # Public client: no secret, the code exchange rests on PKCE alone.
        self.public_client = False
        # ID-token signing algorithms advertised in discovery.
        self.algs = ["RS256"]
        # Overrides how an ID token is produced (bad keys, alg none, ...);
        # returning None leaves it out of the token response.
        self.sign: Callable[[dict[str, Any]], str | None] | None = None
        app = Flask("provider")

        @app.get("/.well-known/openid-configuration")
        def discovery() -> Any:
            return jsonify(
                issuer=self.issuer,
                authorization_endpoint=f"{self.issuer}/authorize",
                token_endpoint=f"{self.issuer}/token",
                userinfo_endpoint=f"{self.issuer}/userinfo",
                jwks_uri=f"{self.issuer}/jwks",
                end_session_endpoint=f"{self.issuer}/logout",
                id_token_signing_alg_values_supported=self.algs,
            )

        @app.get("/jwks")
        def jwks() -> Any:
            return jsonify(keys=[self.key.as_dict(private=False)])

        @app.post("/token")
        def token() -> Any:
            auth = request.authorization
            if self.public_client:
                client_ok = not auth and request.form.get("client_id") == _CLIENT_ID
            else:
                client_ok = bool(auth) and (auth.username, auth.password) == (
                    _CLIENT_ID,
                    _CLIENT_SECRET,
                )
            if not client_ok:
                return jsonify(error="invalid_client"), 401
            grant = self.codes.pop(request.form.get("code", ""), None)
            verifier = request.form.get("code_verifier", "")
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode()
            )
            if grant is None or challenge != grant["challenge"]:
                return jsonify(error="invalid_grant"), 400
            if self.sign is not None:
                id_token = self.sign(grant["claims"])
            else:
                id_token = jwt.encode(
                    {"alg": "RS256", "kid": "test-key"}, grant["claims"], self.key
                )
            body: dict[str, Any] = {
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 300,
            }
            if id_token is not None:
                body["id_token"] = id_token
            return jsonify(body)

        @app.get("/userinfo")
        def userinfo() -> Any:
            if request.headers.get("Authorization") != "Bearer access-token":
                return jsonify(error="invalid_token"), 401
            return jsonify(self.userinfo)

        self.app = app

    def issue_code(self, auth_nonce: str, challenge: str, **claims: Any) -> str:
        """Approve a login: the code the provider would redirect back with."""
        now = int(time.time())
        base = {
            "iss": self.issuer,
            "sub": "user-1",
            "aud": _CLIENT_ID,
            "iat": now,
            "exp": now + 300,
            "nonce": auth_nonce,
            "email": "jane@example.com",
            "email_verified": True,
        }
        base.update(claims)
        code = secrets.token_urlsafe(16)
        self.codes[code] = {
            "challenge": challenge,
            "claims": {k: v for k, v in base.items() if v is not None},
        }
        return code


@pytest.fixture(scope="module")
def provider() -> Generator[Provider]:
    prov = Provider()
    server = make_server("127.0.0.1", 0, prov.app, threaded=True)
    prov.issuer = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield prov
    server.shutdown()


@pytest.fixture(autouse=True)
def _no_proxy(monkeypatch: pytest.MonkeyPatch, provider: Provider) -> None:
    # The provider lives on loopback: never route it through a proxy.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    provider.codes.clear()
    provider.userinfo = {}
    provider.public_client = False
    provider.algs = ["RS256"]
    provider.sign = None


def _settings(provider: Provider, **overrides: object) -> OidcSettings:
    fields: dict[str, object] = {
        "issuer": provider.issuer,
        "client_id": _CLIENT_ID,
        "client_secret": _CLIENT_SECRET,
        "session_secret": _SESSION_SECRET,
        "allowed_emails": ["Jane@Example.com"],
        # The test client's origin.
        "public_url": "http://localhost",
    }
    fields.update(overrides)
    return OidcSettings(**fields)


def _make_app(
    tmp_path: Path,
    oidc: OidcSettings | None,
    trusted_proxies: int = 0,
) -> Flask:
    app = create_app(
        lines=[InvoiceLine(concept="Backend", unit_price=100.0, quantity=1.0)],
        issuer={"name": "Jane Doe Consulting", "bank": {"iban": "", "bic": ""}},
        client={"name": "Acme"},
        invoice_number="2026-06",
        output_path=tmp_path / "invoice.pdf",
        oidc=oidc,
        trusted_proxies=trusted_proxies,
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(tmp_path: Path, provider: Provider) -> Generator[FlaskClient]:
    with _make_app(tmp_path, _settings(provider)).test_client() as c:
        yield c


def _authorize_params(resp: TestResponse) -> dict[str, str]:
    """The query of the provider redirect /login answers with."""
    assert resp.status_code == 302
    query = parse_qs(urlsplit(resp.headers["Location"]).query)
    return {k: v[0] for k, v in query.items()}


def _login(
    c: FlaskClient, provider: Provider, next_path: str = "/", **claims: Any
) -> TestResponse:
    """Run the whole code flow and return the callback's response."""
    params = _authorize_params(c.get("/login", query_string={"next": next_path}))
    code = provider.issue_code(params["nonce"], params["code_challenge"], **claims)
    return c.get(
        "/oidc/callback", query_string={"code": code, "state": params["state"]}
    )


class TestDisabled:
    """Without OIDC configuration the editor is exactly the local app."""

    def test_editor_open_without_login(self, tmp_path: Path) -> None:
        c = _make_app(tmp_path, None).test_client()
        assert c.get("/").status_code == 200
        assert c.post("/lines/add").status_code == 200
        assert b"Sign out" not in c.get("/").data

    def test_auth_routes_absent(self, tmp_path: Path) -> None:
        c = _make_app(tmp_path, None).test_client()
        for path in ("/login", "/oidc/callback", "/logout"):
            assert c.get(path).status_code == 404

    def test_no_session_cookie(self, tmp_path: Path) -> None:
        c = _make_app(tmp_path, None).test_client()
        assert "Set-Cookie" not in c.get("/").headers


class TestGuard:
    def test_unauthenticated_get_redirects_to_login(self, client: FlaskClient) -> None:
        resp = client.get("/settings?tab=email")
        assert resp.status_code == 302
        location = urlsplit(resp.headers["Location"])
        assert location.path == "/login"
        assert parse_qs(location.query)["next"] == ["/settings?tab=email"]

    def test_unauthenticated_post_is_401(self, client: FlaskClient) -> None:
        resp = client.post("/lines/add")
        assert resp.status_code == 401

    def test_htmx_request_told_to_reload_via_login(self, client: FlaskClient) -> None:
        # A redirect would be followed inside the XHR; htmx needs HX-Redirect.
        resp = client.get(
            "/send/modal",
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "http://localhost/settings?tab=email",
            },
        )
        assert resp.status_code == 401
        location = urlsplit(resp.headers["HX-Redirect"])
        assert location.path == "/login"
        assert parse_qs(location.query)["next"] == ["/settings?tab=email"]

    def test_htmx_redirect_ignores_foreign_current_url(
        self, client: FlaskClient
    ) -> None:
        resp = client.post(
            "/lines/add",
            headers={
                "HX-Request": "true",
                "HX-Current-URL": "https://evil.example/settings",
            },
        )
        assert resp.status_code == 401
        # Only the path is kept: the redirect stays on this origin.
        location = urlsplit(resp.headers["HX-Redirect"])
        assert parse_qs(location.query)["next"] == ["/settings"]
        resp = client.post(
            "/lines/add",
            headers={"HX-Request": "true", "HX-Current-URL": "/\\evil.example"},
        )
        assert parse_qs(urlsplit(resp.headers["HX-Redirect"]).query)["next"] == ["/"]

    def test_session_expires_after_lifetime(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        _login(client, provider)
        assert client.get("/").status_code == 200
        with client.session_transaction() as sess:
            sess["login_at"] = int(time.time()) - 13 * 3600
        assert client.get("/").status_code == 302

    def test_session_without_login_time_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        _login(client, provider)
        with client.session_transaction() as sess:
            del sess["login_at"]
        assert client.get("/").status_code == 302

    def test_session_lifetime_configurable(
        self, tmp_path: Path, provider: Provider
    ) -> None:
        app = _make_app(tmp_path, _settings(provider, session_lifetime_hours=1))
        with app.test_client() as c:
            _login(c, provider)
            with c.session_transaction() as sess:
                sess["login_at"] = int(time.time()) - 2 * 3600
            assert c.get("/").status_code == 302

    def test_login_assets_exempt(self, client: FlaskClient) -> None:
        assert client.get("/static/app.css").status_code == 200
        assert client.get("/favicon.ico").status_code == 200

    def test_healthz_needs_no_session(self, client: FlaskClient) -> None:
        resp = client.get("/healthz", headers={"Host": "10.42.0.17:8321"})
        assert resp.status_code == 200
        assert resp.data == b"ok"
        assert "Set-Cookie" not in resp.headers  # no session started
        # The exemption is that one endpoint, not a path prefix.
        for path in ("/healthz/", "/healthz/x", "/healthzx"):
            assert client.get(path).status_code in (302, 404), path
        assert client.get("/").status_code == 302

    def test_quit_disabled_on_server(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        _login(client, provider)
        assert client.post("/quit").status_code == 404


class TestArchiveGuarded:
    """Archived invoices (links, list, send, delete) need a login too."""

    def _app_with_invoice(
        self, tmp_path: Path, provider: Provider, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[Flask, str]:
        monkeypatch.setattr(
            "harvest_invoicer.app.pdf_from_html", lambda _h, _u=None: b"%PDF-fake"
        )
        app = create_app(
            lines=[InvoiceLine(concept="Backend", unit_price=100.0, quantity=1.0)],
            issuer={"name": "Jane Doe Consulting", "bank": {"iban": "", "bic": ""}},
            client={"name": "Acme"},
            invoice_number="2026-06",
            output_path=None,
            db_path=tmp_path / "state.db",
            oidc=_settings(provider),
        )
        app.config["TESTING"] = True
        with app.test_client() as c:
            _login(c, provider)
            assert c.post("/render").status_code == 200
        record = state_db.latest_invoice(tmp_path / "state.db")
        assert record is not None
        return app, str(record["id"])

    def test_links_require_login(
        self, tmp_path: Path, provider: Provider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app, invoice_id = self._app_with_invoice(tmp_path, provider, monkeypatch)
        anon = app.test_client()
        for path in (
            f"/invoices/{invoice_id}.pdf",
            f"/invoices/{invoice_id}.pdf?download=1",
            "/invoices",
            f"/invoices/{invoice_id}/send",
            "/pdf",
        ):
            resp = anon.get(path)
            assert resp.status_code == 302, path
            assert urlsplit(resp.headers["Location"]).path == "/login"
        for path in (f"/invoices/{invoice_id}/send", f"/invoices/{invoice_id}/delete"):
            assert anon.post(path).status_code == 401, path
        assert state_db.latest_invoice(tmp_path / "state.db") is not None

    def test_signed_in_user_gets_the_pdf(
        self, tmp_path: Path, provider: Provider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        app, invoice_id = self._app_with_invoice(tmp_path, provider, monkeypatch)
        with app.test_client() as c:
            _login(c, provider)
            resp = c.get(f"/invoices/{invoice_id}.pdf")
        assert resp.status_code == 200
        assert resp.data == b"%PDF-fake"


class TestLogin:
    def test_login_redirects_with_pkce_state_nonce(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        params = _authorize_params(client.get("/login"))
        assert params["client_id"] == _CLIENT_ID
        assert params["response_type"] == "code"
        assert params["scope"] == "openid email profile"
        assert params["code_challenge_method"] == "S256"
        assert params["redirect_uri"] == "http://localhost/oidc/callback"
        for key in ("state", "nonce", "code_challenge"):
            assert params[key]

    def test_allowed_email_logs_in_and_returns_to_saved_path(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, next_path="/settings?tab=email")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/settings?tab=email"
        assert client.get("/").status_code == 200
        assert client.post("/lines/add").status_code == 200

    def test_email_match_is_case_insensitive(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, email="JANE@example.COM")
        assert resp.status_code == 302
        assert client.get("/").status_code == 200

    def test_header_shows_user_and_logout(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        _login(client, provider)
        for path in ("/", "/settings"):
            page = client.get(path).data
            assert b"jane@example.com" in page
            assert b'action="/logout"' in page

    def test_session_cookie_flags(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider)
        cookie = resp.headers["Set-Cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=Lax" in cookie
        # Plain http without --secure-cookies: not Secure (local testing).
        assert "Secure" not in cookie

    def test_secure_cookies_flag(self, tmp_path: Path, provider: Provider) -> None:
        app = _make_app(tmp_path, _settings(provider, secure_cookies=True))
        with app.test_client() as c:
            assert "Secure" in _login(c, provider).headers["Set-Cookie"]

    def test_session_regenerated_on_login(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        # Pre-login session contents (e.g. planted by an attacker) are dropped.
        with client.session_transaction() as sess:
            sess["planted"] = "x"
        _login(client, provider)
        with client.session_transaction() as sess:
            assert "planted" not in sess
            assert not any(k.startswith("_state_") for k in sess)
            assert sess["user"]["email"] == "jane@example.com"

    def test_email_from_userinfo_when_id_token_lacks_it(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        # Zitadel's default: profile claims only at the userinfo endpoint.
        provider.userinfo = {
            "sub": "user-1",
            "email": "jane@example.com",
            "email_verified": True,
        }
        resp = _login(client, provider, email=None, email_verified=None)
        assert resp.status_code == 302
        assert client.get("/").status_code == 200

    def test_userinfo_consulted_when_email_unverified_claim_missing(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        provider.userinfo = {
            "sub": "user-1",
            "email": "jane@example.com",
            "email_verified": True,
        }
        resp = _login(client, provider, email_verified=None)
        assert resp.status_code == 302
        assert client.get("/").status_code == 200

    def test_userinfo_for_another_subject_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        provider.userinfo = {"sub": "someone-else", "email": "jane@example.com"}
        resp = _login(client, provider, email=None, email_verified=None)
        assert resp.status_code == 400

    def test_allowed_subject(self, tmp_path: Path, provider: Provider) -> None:
        app = _make_app(
            tmp_path,
            _settings(provider, allowed_emails=[], allowed_subjects=["user-1"]),
        )
        # No email anywhere: the subject alone identifies the account.
        provider.userinfo = {"sub": "user-1"}
        with app.test_client() as c:
            assert _login(c, provider, email=None).status_code == 302
            assert c.get("/").status_code == 200

    def test_public_client_without_secret(
        self, tmp_path: Path, provider: Provider
    ) -> None:
        provider.public_client = True
        app = _make_app(tmp_path, _settings(provider, client_secret=""))
        with app.test_client() as c:
            assert _login(c, provider).status_code == 302
            assert c.get("/").status_code == 200

    def test_allow_any_user(self, tmp_path: Path, provider: Provider) -> None:
        app = _make_app(
            tmp_path, _settings(provider, allowed_emails=[], allow_any_user=True)
        )
        with app.test_client() as c:
            assert _login(c, provider, email="x@y.io").status_code == 302
            assert c.get("/").status_code == 200


class TestRejected:
    def _assert_denied(self, c: FlaskClient, resp: TestResponse, status: int) -> None:
        assert resp.status_code == status
        with c.session_transaction() as sess:
            assert "user" not in sess
        # Still locked out — and the error page never redirects (no loop).
        assert c.get("/").status_code == 302
        assert "Location" not in resp.headers

    def test_disallowed_email_403(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, email="mallory@example.com")
        self._assert_denied(client, resp, 403)
        assert b"mallory@example.com" in resp.data
        assert b'action="/logout"' in resp.data

    def test_unverified_email_403(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, email_verified=False)
        self._assert_denied(client, resp, 403)

    def test_bad_state_rejected(self, client: FlaskClient, provider: Provider) -> None:
        params = _authorize_params(client.get("/login"))
        code = provider.issue_code(params["nonce"], params["code_challenge"])
        resp = client.get(
            "/oidc/callback", query_string={"code": code, "state": "forged"}
        )
        self._assert_denied(client, resp, 400)

    def test_missing_state_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        params = _authorize_params(client.get("/login"))
        code = provider.issue_code(params["nonce"], params["code_challenge"])
        resp = client.get("/oidc/callback", query_string={"code": code})
        self._assert_denied(client, resp, 400)

    def test_callback_without_login_rejected(self, client: FlaskClient) -> None:
        resp = client.get("/oidc/callback", query_string={"code": "x", "state": "y"})
        self._assert_denied(client, resp, 400)

    def test_wrong_nonce_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, nonce="replayed")
        self._assert_denied(client, resp, 400)

    def test_wrong_audience_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, aud="another-client")
        self._assert_denied(client, resp, 400)

    def test_wrong_audience_with_our_azp_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        # azp alone must not stand in for the audience check.
        resp = _login(client, provider, aud="another-client", azp=_CLIENT_ID)
        self._assert_denied(client, resp, 400)

    def test_wrong_issuer_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, iss="https://evil.example")
        self._assert_denied(client, resp, 400)

    def test_expired_token_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        past = int(time.time()) - 3600
        resp = _login(client, provider, iat=past - 300, exp=past)
        self._assert_denied(client, resp, 400)

    def test_provider_error_rejected(self, client: FlaskClient) -> None:
        client.get("/login")
        resp = client.get(
            "/oidc/callback", query_string={"error": "access_denied", "state": "x"}
        )
        self._assert_denied(client, resp, 400)

    def test_signature_by_other_key_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        rogue = RSAKey.generate_key(2048, parameters={"kid": "test-key"})
        provider.sign = lambda claims: jwt.encode(
            {"alg": "RS256", "kid": "test-key"}, claims, rogue
        )
        self._assert_denied(client, _login(client, provider), 400)

    def test_alg_none_rejected(self, client: FlaskClient, provider: Provider) -> None:
        def _b64(data: dict[str, Any]) -> str:
            raw = json.dumps(data).encode()
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        provider.algs = ["RS256", "none"]
        provider.sign = lambda claims: f"{_b64({'alg': 'none'})}.{_b64(claims)}."
        self._assert_denied(client, _login(client, provider), 400)

    def test_token_response_without_id_token_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        provider.sign = lambda _claims: None
        self._assert_denied(client, _login(client, provider), 400)

    def test_unsupported_signing_algs_refuse_login(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        # Only HS256 (shared-secret) offered: nothing we accept, so no login.
        provider.algs = ["HS256"]
        resp = client.get("/login")
        assert resp.status_code == 400
        assert "Location" not in resp.headers

    def test_state_replay_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        params = _authorize_params(client.get("/login"))
        code = provider.issue_code(params["nonce"], params["code_challenge"])
        query = {"code": code, "state": params["state"]}
        assert client.get("/oidc/callback", query_string=query).status_code == 302
        # The state was consumed: replaying the same callback fails.
        self._assert_denied(
            client, client.get("/oidc/callback", query_string=query), 400
        )

    def test_failure_log_has_no_control_characters(
        self, client: FlaskClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        client.get("/login")
        client.get(
            "/oidc/callback",
            query_string={
                "error": "access_denied",
                "error_description": "x\nFAKE LOG LINE\r\n",
                "state": "x",
            },
        )
        messages = [r.getMessage() for r in caplog.records if "OIDC" in r.getMessage()]
        assert messages
        assert all("\n" not in m and "\r" not in m for m in messages)

    def test_failure_page_uniform(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        # Every validation failure looks the same to the browser.
        bodies = {
            _login(client, provider, nonce="bad").data,
            _login(client, provider, aud="other").data,
            client.get("/oidc/callback", query_string={"state": "x"}).data,
        }
        assert len(bodies) == 1

    def test_revoked_user_logged_out(self, tmp_path: Path, provider: Provider) -> None:
        # The allow-list is checked on every request, not only at login.
        app = _make_app(tmp_path, _settings(provider))
        with app.test_client() as c:
            _login(c, provider)
            with c.session_transaction() as sess:
                sess["user"] = {"sub": "user-1", "email": "removed@example.com"}
            assert c.get("/").status_code == 302


class TestLogout:
    def test_get_logout_changes_nothing(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        # GET only offers the sign-out form; signing out needs the POST.
        _login(client, provider)
        resp = client.get("/logout")
        assert resp.status_code == 200
        assert b'action="/logout"' in resp.data
        assert client.get("/").status_code == 200

    def test_cross_origin_logout_rejected(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        _login(client, provider)
        resp = client.post("/logout", headers={"Origin": "https://evil.example"})
        assert resp.status_code == 403
        assert client.get("/").status_code == 200

    def test_logout_clears_session_and_ends_provider_session(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        _login(client, provider)
        resp = client.post("/logout", headers={"Origin": "http://localhost"})
        assert resp.status_code == 303
        location = urlsplit(resp.headers["Location"])
        assert f"{location.scheme}://{location.netloc}" == provider.issuer
        assert location.path == "/logout"
        query = parse_qs(location.query)
        assert query["client_id"] == [_CLIENT_ID]
        assert query["post_logout_redirect_uri"] == ["http://localhost/"]
        with client.session_transaction() as sess:
            assert "user" not in sess
        assert client.get("/").status_code == 302


class TestSafeNext:
    @pytest.mark.parametrize(
        "target",
        [
            "https://evil.example/",
            "//evil.example/x",
            "/\\evil.example",
            "\\\\evil.example",
            "evil.example",
            "javascript:alert(1)",
            "/ok\r\nLocation: https://evil.example",
            "",
            None,
            "/login",
            "/oidc/callback?code=x",
            "/logout",
        ],
    )
    def test_unsafe_targets_fall_back_to_root(self, target: str | None) -> None:
        assert safe_next(target) == "/"

    @pytest.mark.parametrize("target", ["/", "/settings", "/settings?tab=email"])
    def test_relative_paths_kept(self, target: str) -> None:
        assert safe_next(target) == target

    def test_open_redirect_ignored_end_to_end(
        self, client: FlaskClient, provider: Provider
    ) -> None:
        resp = _login(client, provider, next_path="//evil.example/phish")
        assert resp.headers["Location"] == "/"


_FORWARDED = {
    "X-Forwarded-Proto": "https",
    "X-Forwarded-Host": "invoicer.example.com",
    "X-Forwarded-For": "203.0.113.9",
}


class TestProxy:
    def test_forwarded_proto_honored(self, tmp_path: Path, provider: Provider) -> None:
        app = _make_app(tmp_path, _settings(provider), trusted_proxies=1)
        with app.test_client() as c:
            # The proxy forwards the public host (localhost in these tests).
            headers = {**_FORWARDED, "X-Forwarded-Host": "localhost"}
            resp = c.get("/login", headers=headers)
            # The request arrived over https at the proxy: cookie is Secure.
            assert "Secure" in resp.headers["Set-Cookie"]
            # The redirect URI comes from --public-url only, never from
            # (forwarded) request headers.
            params = _authorize_params(resp)
            assert params["redirect_uri"] == "http://localhost/oidc/callback"

    def test_forwarded_foreign_host_rejected(
        self, tmp_path: Path, provider: Provider
    ) -> None:
        """A forwarded Host other than the public URL's is refused, reads
        included (DNS rebinding through the proxy)."""
        app = _make_app(tmp_path, _settings(provider), trusted_proxies=1)
        with app.test_client() as c:
            assert c.get("/login", headers=_FORWARDED).status_code == 403
            assert c.get("/", headers=_FORWARDED).status_code == 403

    def test_forwarded_headers_ignored_without_trusted_proxy(
        self, tmp_path: Path, provider: Provider
    ) -> None:
        app = _make_app(tmp_path, _settings(provider), trusted_proxies=0)
        with app.test_client() as c:
            resp = c.get("/login", headers=_FORWARDED)
            params = _authorize_params(resp)
            assert params["redirect_uri"] == "http://localhost/oidc/callback"
            assert "Secure" not in resp.headers["Set-Cookie"]

    def test_public_url_fixes_redirect_uri_and_csrf_host(
        self, tmp_path: Path, provider: Provider
    ) -> None:
        app = _make_app(
            tmp_path,
            _settings(provider, public_url="https://invoicer.example.com"),
            trusted_proxies=1,
        )
        with app.test_client() as c:
            params = _authorize_params(c.get("/login"))
            assert (
                params["redirect_uri"] == "https://invoicer.example.com/oidc/callback"
            )
            _login(c, provider)
            # The CSRF guard accepts the public host behind the proxy.
            resp = c.post(
                "/lines/add",
                headers={
                    **_FORWARDED,
                    "Origin": "https://invoicer.example.com",
                },
            )
            assert resp.status_code == 200
            resp = c.post(
                "/lines/add",
                headers={**_FORWARDED, "Origin": "https://evil.example"},
            )
            assert resp.status_code == 403
