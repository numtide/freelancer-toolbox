"""OpenID Connect login for a server deployment (opt-in via ``serve --oidc-*``).

Authlib drives the authorization-code flow: discovery from the issuer, PKCE,
state and nonce kept in the (signed) session cookie, and ID-token signature
and claim validation (iss, aud, exp, iat, nonce).  On top of that this module
adds the allow-list, a login guard in front of every route, and the session
cookie policy.

Nothing secret is logged: failures log the exception type and message, which
for Authlib/requests/joserfc errors carry the provider's error code or the
failing claim, never tokens, codes, or the client secret.  Logged values are
``repr``-quoted, so provider-supplied text cannot forge log lines.

The session is a signed (not encrypted) cookie: its contents, including the
PKCE verifier and nonce during a login, are readable by the user's own
browser.  Rotating the session secret invalidates every session.
"""

from __future__ import annotations

import time
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode, urlsplit

from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, redirect, render_template, request, session, url_for
from flask.sessions import SecureCookieSessionInterface

if TYPE_CHECKING:
    from flask.typing import ResponseReturnValue

    from harvest_invoicer.config import OidcSettings

# Endpoints reachable without a session: the login flow itself and the
# static assets its pages use.
OIDC_ENDPOINTS = frozenset(
    {"oidc_login", "oidc_callback", "oidc_logout", "oidc_logout_page"}
)
_PUBLIC_ENDPOINTS = OIDC_ENDPOINTS | {"static", "favicon"}

# Paths a post-login redirect must never land on (it would loop).
_AUTH_PATHS = ("/login", "/oidc/", "/logout")

# ID-token signature algorithms accepted (asymmetric only), intersected with
# what the provider advertises.
ID_TOKEN_ALGS = ("RS256", "PS256", "ES256", "EdDSA")

_SESSION_USER = "user"
_SESSION_NEXT = "oidc_next"
# When the login happened (epoch seconds): bounds the session's lifetime
# however often the cookie is refreshed.
_SESSION_LOGIN_AT = "login_at"


def safe_next(target: str | None) -> str:
    """The post-login redirect target, or ``/`` when it is not safe.

    Only same-origin relative paths are kept: no scheme or host, no
    protocol-relative ``//host``, no backslashes (browsers read ``/\\host``
    as ``//host``), no control characters, and nothing in the login flow.
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return "/"
    if "\\" in target or any(ord(c) < 32 or ord(c) == 127 for c in target):
        return "/"
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return "/"
    if parts.path == "/login" or parts.path.startswith(_AUTH_PATHS):
        return "/"
    return target


class _SessionInterface(SecureCookieSessionInterface):
    """Signed-cookie sessions whose Secure flag follows the request.

    Secure whenever the browser reached us over https (as reported by a
    trusted proxy), or always with ``--secure-cookies``.
    """

    def __init__(self, force_secure: bool) -> None:
        self.force_secure = force_secure

    def get_cookie_secure(self, app: Flask) -> bool:
        return self.force_secure or request.is_secure


def init_oidc(app: Flask, oidc: OidcSettings) -> None:
    """Require an allow-listed OIDC login for every request to *app*."""
    lifetime = timedelta(hours=oidc.session_lifetime_hours)
    app.secret_key = oidc.session_secret.get_secret_value()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=lifetime,
    )
    app.session_interface = _SessionInterface(oidc.secure_cookies)

    client_secret = oidc.client_secret.get_secret_value()
    client_kwargs: dict[str, Any] = {
        "scope": oidc.scopes,
        "code_challenge_method": "S256",
    }
    if not client_secret:
        # Public client: PKCE alone authenticates the code exchange.
        client_kwargs["token_endpoint_auth_method"] = "none"  # noqa: S105 — a method name
    oauth = OAuth(app)
    provider = oauth.register(
        "oidc",
        client_id=oidc.client_id,
        client_secret=client_secret or None,
        server_metadata_url=f"{oidc.issuer}/.well-known/openid-configuration",
        client_kwargs=client_kwargs,
    )

    def _session_current() -> bool:
        """The session's login is younger than the configured lifetime."""
        login_at = session.get(_SESSION_LOGIN_AT)
        if not isinstance(login_at, int):
            return False
        return 0 <= time.time() - login_at < lifetime.total_seconds()

    def _is_allowed(user: dict[str, str]) -> bool:
        if not user.get("sub"):
            return False
        if oidc.allow_any_user or user["sub"] in oidc.allowed_subjects:
            return True
        return bool(user.get("email")) and user["email"] in oidc.allowed_emails

    def _external(path: str) -> str:
        # Always the configured origin: request headers never shape the
        # redirect or post-logout URIs.
        return oidc.public_url + path

    def _metadata() -> dict[str, Any]:
        """Provider metadata, checked to belong to the configured issuer."""
        meta: dict[str, Any] = provider.load_server_metadata()
        # OIDC Discovery: the document must name the issuer it was fetched for.
        if str(meta.get("issuer", "")).rstrip("/") != oidc.issuer:
            msg = "discovery document issuer does not match the configured issuer"
            raise ValueError(msg)
        # Pin ID-token verification to asymmetric algorithms both sides
        # support.  Authlib verifies with the metadata's list, so narrowing it
        # in place (the cached metadata dict) is what enforces the allow-list.
        offered = meta.get("id_token_signing_alg_values_supported") or ["RS256"]
        algs = [a for a in ID_TOKEN_ALGS if a in offered]
        if not algs:
            msg = f"provider offers no accepted ID-token algorithm ({offered!r})"
            raise ValueError(msg)
        meta["id_token_signing_alg_values_supported"] = algs
        return meta

    def _auth_page(status: int, title: str, message: str, **ctx: object) -> Response:
        return Response(
            render_template("auth.html", title=title, message=message, **ctx),
            status=status,
        )

    def _login_failed(exc: Exception) -> Response:
        # One answer for every failure (bad state, provider error, invalid
        # token): the browser learns nothing about which check failed.
        session.clear()
        app.logger.warning("OIDC login failed: %s: %r", type(exc).__name__, str(exc))
        return _auth_page(
            400,
            "Sign-in failed",
            "The sign-in could not be completed. Please try again.",
            retry=True,
        )

    def _verified_email(claims: dict[str, Any]) -> str:
        verified = claims.get("email_verified")
        if verified is True or str(verified).lower() == "true":
            return str(claims.get("email") or "").strip().lower()
        return ""

    @app.before_request
    def _require_login() -> ResponseReturnValue | None:
        if request.endpoint in _PUBLIC_ENDPOINTS:
            return None
        user = session.get(_SESSION_USER)
        if user and _session_current() and _is_allowed(user):
            return None
        if user:
            # Expired, or removed from the allow-list since logging in.
            session.clear()
        if request.headers.get("HX-Request"):
            # htmx would follow a redirect inside its XHR; have it reload the
            # page it is on (path only — the host part is never trusted).
            current = urlsplit(request.headers.get("HX-Current-URL", ""))
            back = current.path + (f"?{current.query}" if current.query else "")
            login = url_for("oidc_login", next=safe_next(back))
            return Response("Unauthorized.", status=401, headers={"HX-Redirect": login})
        if request.method in ("GET", "HEAD"):
            target = request.full_path.rstrip("?")
            return redirect(url_for("oidc_login", next=target))
        return Response("Unauthorized.", status=401)

    @app.context_processor
    def _auth_context() -> dict[str, object]:
        return {"auth_user": session.get(_SESSION_USER)}

    @app.get("/login")
    def oidc_login() -> ResponseReturnValue:
        nxt = safe_next(request.args.get("next"))
        # Start from an empty session: nothing from before the login (a
        # planted cookie, a stale identity) survives it.
        session.clear()
        session[_SESSION_NEXT] = nxt
        try:
            _metadata()
            resp: ResponseReturnValue = provider.authorize_redirect(
                _external("/oidc/callback")
            )
        except Exception as exc:  # noqa: BLE001 — provider unreachable/misconfigured
            return _login_failed(exc)
        return resp

    @app.get("/oidc/callback")
    def oidc_callback() -> ResponseReturnValue:
        nxt = safe_next(session.get(_SESSION_NEXT))
        try:
            meta = _metadata()
            # Validates state (against the session), exchanges the code with
            # the PKCE verifier, and verifies the ID token incl. the nonce.
            # Authlib only checks aud when told to: pin both iss and aud.
            token = provider.authorize_access_token(
                claims_options={
                    "iss": {"essential": True, "values": [meta["issuer"]]},
                    "aud": {"essential": True, "values": [oidc.client_id]},
                }
            )
            if not token.get("userinfo"):
                msg = "token response carries no ID token"
                raise ValueError(msg)  # noqa: TRY301
            claims = dict(token["userinfo"])
            missing = "email" not in claims or "email_verified" not in claims
            if missing and meta.get("userinfo_endpoint"):
                info = provider.userinfo(token=token)
                if info.get("sub") != claims["sub"]:
                    msg = "userinfo subject does not match the ID token"
                    raise ValueError(msg)  # noqa: TRY301
                claims.update(
                    {k: info[k] for k in ("email", "email_verified") if k in info}
                )
        except Exception as exc:  # noqa: BLE001 — any failure denies the login
            return _login_failed(exc)

        user = {"sub": str(claims["sub"]), "email": _verified_email(claims)}
        # Fresh session for the new identity (drops Authlib's state data).
        session.clear()
        if not _is_allowed(user):
            app.logger.warning(
                "OIDC login denied for sub=%r email=%r", user["sub"], user["email"]
            )
            return _auth_page(
                403,
                "Not authorized",
                "This account is not allowed to use the invoicer.",
                denied=user["email"] or user["sub"],
            )
        session.permanent = True
        session[_SESSION_USER] = user
        session[_SESSION_LOGIN_AT] = int(time.time())
        return redirect(nxt)

    @app.get("/logout")
    def oidc_logout_page() -> ResponseReturnValue:
        # GET never signs out (a link or image elsewhere could trigger it);
        # it only offers the form, whose POST the CSRF guard covers.
        return _auth_page(200, "Sign out", "Sign out of the invoicer?", sign_out=True)

    @app.post("/logout")
    def oidc_logout() -> ResponseReturnValue:
        session.clear()
        try:
            end_session = _metadata().get("end_session_endpoint")
        except Exception:  # noqa: BLE001 — logging out locally still works
            end_session = None
        if end_session:
            # RP-initiated logout: end the provider session too, then come
            # back (register this post-logout URI with the provider).
            params = {
                "client_id": oidc.client_id,
                "post_logout_redirect_uri": _external("/"),
            }
            sep = "&" if "?" in end_session else "?"
            return redirect(f"{end_session}{sep}{urlencode(params)}", code=303)
        return _auth_page(200, "Signed out", "You have been signed out.", retry=True)
