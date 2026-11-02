"""Tests for cli.py: Click command validation via CliRunner."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from flask import Flask
from harvest_invoicer.cli import (
    _blank_issuer,
    _multi_user_warning,
    _resolve_bill_to,
    _resolve_bill_to_lenient,
    _resolve_period,
    main,
)
from harvest_invoicer.db import default_db_path
from harvest_invoicer.model import REQUIRED_ISSUER_FIELDS, InvoiceLine
from harvest_invoicer.render import _PACKAGED_TEMPLATES_DIR
from werkzeug.middleware.proxy_fix import ProxyFix


def test_generate_demo_invalid_month() -> None:
    """generate --demo rejects a non-YYYY-MM month string with exit code != 0."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--demo", "--month", "junk"])
    assert result.exit_code != 0


def test_serve_has_no_per_invoice_flags() -> None:
    """serve hands per-invoice choices to the UI; only session flags remain."""
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--demo", "--month", "2026-06"])
    assert result.exit_code != 0
    assert "No such option" in result.output
    help_out = runner.invoke(main, ["serve", "--help"]).output
    for gone in (
        "--month",
        "--period-start",
        "--user",
        "--number",
        "--bill-to",
        "--merge-duplicates",
    ):
        assert gone not in help_out
    for kept in ("--harvest-client", "--templates-dir", "--output", "--demo"):
        assert kept in help_out


def test_edit_command_renamed_to_serve() -> None:
    """The old edit name is gone; serve is the editor entrypoint."""
    runner = CliRunner()
    result = runner.invoke(main, ["edit", "--help"])
    assert result.exit_code != 0
    assert "serve" in runner.invoke(main, ["--help"]).output


def test_resolve_period_defaults_to_month() -> None:
    """Without overrides the period spans the whole month."""
    start, end = _resolve_period("2026-06", None, None)
    assert start == date(2026, 6, 1)
    assert end == date(2026, 6, 30)


def test_resolve_period_overrides_win() -> None:
    """--period-start/--period-end take precedence over the month bounds."""
    start, end = _resolve_period(
        "2026-06",
        datetime(2026, 6, 10),
        datetime(2026, 6, 25),
    )
    assert start == date(2026, 6, 10)
    assert end == date(2026, 6, 25)


def test_generate_period_flags_require_single_month() -> None:
    """Explicit period with multiple months is rejected."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "generate",
            "--demo",
            "--month",
            "2026-05",
            "--month",
            "2026-06",
            "--period-start",
            "2026-05-01",
        ],
    )
    assert result.exit_code != 0
    assert "single --month" in result.output


def test_merge_duplicates_flag_available() -> None:
    """Headless generate exposes --merge-duplicates (serve uses the checkbox)."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--merge-duplicates" in result.output


class TestStateResolution:
    """State database resolution: env override, else the XDG data dir."""

    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_DB", "/srv/invoicer/state.db")
        assert default_db_path() == Path("/srv/invoicer/state.db")

    def test_xdg_data_home_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("HARVEST_INVOICER_DB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        assert default_db_path() == tmp_path / "harvest-invoicer" / "state.db"

    def test_blank_issuer_has_required_fields(self) -> None:
        issuer = _blank_issuer()
        assert issuer["name"] == ""
        assert issuer["bank"] == {"iban": "", "bic": ""}
        missing = REQUIRED_ISSUER_FIELDS - set(issuer.keys())
        assert not missing

    def test_generate_without_config_errors_helpfully(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_DB", str(tmp_path / "empty.db"))
        runner = CliRunner()
        result = runner.invoke(main, ["generate", "--month", "2026-06"])
        assert result.exit_code != 0
        assert "No configuration found" in result.output
        assert "harvest-invoicer serve" in result.output


class TestTemplatesInit:
    def test_creates_folder_with_packaged_copies(self, tmp_path: Path) -> None:
        """templates init scaffolds the directory with both template files."""
        target = tmp_path / "my-templates"
        runner = CliRunner()
        result = runner.invoke(main, ["templates", "init", str(target)])
        assert result.exit_code == 0
        for name in ("invoice.html", "style.css"):
            copied = target / name
            assert copied.exists()
            assert copied.read_bytes() == (_PACKAGED_TEMPLATES_DIR / name).read_bytes()
        assert "--templates-dir" in result.output

    def test_existing_files_preserved_without_force(self, tmp_path: Path) -> None:
        """A second run must not clobber user edits."""
        target = tmp_path / "my-templates"
        runner = CliRunner()
        runner.invoke(main, ["templates", "init", str(target)])
        (target / "style.css").write_text("/* customized */")
        result = runner.invoke(main, ["templates", "init", str(target)])
        assert result.exit_code == 0
        assert "skipped" in result.output
        assert (target / "style.css").read_text() == "/* customized */"

    def test_force_overwrites(self, tmp_path: Path) -> None:
        """--force restores the packaged versions."""
        target = tmp_path / "my-templates"
        runner = CliRunner()
        runner.invoke(main, ["templates", "init", str(target)])
        (target / "style.css").write_text("/* customized */")
        result = runner.invoke(main, ["templates", "init", str(target), "--force"])
        assert result.exit_code == 0
        assert (target / "style.css").read_bytes() == (
            _PACKAGED_TEMPLATES_DIR / "style.css"
        ).read_bytes()


def test_bill_to_flag_available() -> None:
    """Headless generate exposes --bill-to (serve uses the dropdown)."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--help"])
    assert result.exit_code == 0
    assert "--bill-to" in result.output


def test_generate_bill_to_unknown_key_errors() -> None:
    """--bill-to with a key missing from clients.json fails with the keys listed."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["generate", "--demo", "--month", "2026-06", "--bill-to", "Nonexistent"],
    )
    assert result.exit_code != 0
    assert "Nonexistent" in result.output
    assert "Available keys" in result.output


class TestPersistentDefaults:
    """issuer.json harvest_user / default_bill_to and the multi-user warning."""

    def test_bill_to_flag_beats_default(self) -> None:
        clients = {"A": {"name": "A"}, "B": {"name": "B"}}
        entry = _resolve_bill_to("A", "B", None, clients, [])
        assert entry is clients["A"]

    def test_default_bill_to_used_without_flag(self) -> None:
        clients = {"A": {"name": "A"}, "B": {"name": "B"}}
        entry = _resolve_bill_to(None, "B", None, clients, [])
        assert entry is clients["B"]

    def test_default_bill_to_unknown_key_errors(self) -> None:
        clients = {"A": {"name": "A"}}
        with pytest.raises(click.ClickException, match="default_bill_to"):
            _resolve_bill_to(None, "Nope", None, clients, [])

    def test_multi_user_warning_without_filter(self) -> None:
        lines = [
            InvoiceLine(concept="X", unit_price=1.0, quantity=1.0, user="Alice"),
            InvoiceLine(concept="Y", unit_price=1.0, quantity=1.0, user="Bob"),
        ]
        warning = _multi_user_warning(lines, None)
        assert warning is not None
        assert "2 people" in warning
        assert "Alice" in warning
        assert "Bob" in warning

    def test_no_warning_with_filter_or_single_user(self) -> None:
        lines = [
            InvoiceLine(concept="X", unit_price=1.0, quantity=1.0, user="Alice"),
            InvoiceLine(concept="Y", unit_price=1.0, quantity=1.0, user="Bob"),
        ]
        assert _multi_user_warning(lines, "Alice") is None
        single = [InvoiceLine(concept="X", unit_price=1.0, quantity=1.0, user="Al")]
        assert _multi_user_warning(single, None) is None


def test_harvest_client_flag_and_alias() -> None:
    """--harvest-client is the primary name; --client still parses."""
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "--help"])
    assert "--harvest-client" in result.output
    for flag in ("--harvest-client", "--client"):
        result = runner.invoke(
            main, ["generate", "--demo", "--month", "junk", flag, "X"]
        )
        # Fails on the month, never on the option name
        assert "No such option" not in result.output
        assert result.exit_code != 0


class TestLenientBillTo:
    """Editor lazy start: bill-to resolves without fetched data."""

    def test_explicit_key_wins(self) -> None:
        clients = {"a": {"name": "A"}, "b": {"name": "B"}}
        assert _resolve_bill_to_lenient("b", None, clients) is clients["b"]

    def test_unknown_explicit_key_errors(self) -> None:
        with pytest.raises(click.ClickException, match="Available keys"):
            _resolve_bill_to_lenient("nope", None, {"a": {"name": "A"}})

    def test_default_bill_to_used(self) -> None:
        clients = {"a": {"name": "A"}, "b": {"name": "B"}}
        assert _resolve_bill_to_lenient(None, "b", clients) is clients["b"]

    def test_falls_back_to_first_entry(self) -> None:
        clients = {"first": {"name": "F"}, "second": {"name": "S"}}
        assert _resolve_bill_to_lenient(None, None, clients) is clients["first"]

    def test_empty_clients_gives_empty_entry(self) -> None:
        assert _resolve_bill_to_lenient(None, None, {}) == {}


class TestServeOidc:
    """serve --oidc-*: opt-in server mode, validated before the app starts."""

    _SECRET = "s" * 32

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "OIDC_ISSUER",
            "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET",
            "OIDC_CLIENT_SECRET_FILE",
            "OIDC_ALLOWED_EMAILS",
            "OIDC_ALLOWED_SUBJECTS",
            "OIDC_ALLOW_ANY_USER",
            "OIDC_SCOPES",
            "PUBLIC_URL",
            "SESSION_SECRET",
            "SESSION_SECRET_FILE",
            "TRUSTED_PROXIES",
            "SECURE_COOKIES",
            "SERVER",
            "THREADS",
            "SESSION_LIFETIME",
        ):
            monkeypatch.delenv(f"HARVEST_INVOICER_{var}", raising=False)

    @pytest.fixture
    def started(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        """Capture the app (and run kwargs) instead of serving it."""
        seen: dict[str, object] = {}

        def _run(app: Flask, **kwargs: object) -> None:
            seen["app"] = app
            seen.update(kwargs)

        def _serve(app: Flask, **kwargs: object) -> None:  # OIDC: waitress
            _run(app, **kwargs)

        import waitress  # noqa: PLC0415

        monkeypatch.setattr(Flask, "run", _run)
        monkeypatch.setattr(waitress, "serve", _serve)
        return seen

    def _invoke(self, *args: str, env: dict[str, str] | None = None) -> object:
        return CliRunner().invoke(
            main, ["serve", "--demo", "--no-browser", *args], env=env
        )

    def _oidc_env(self, **extra: str) -> dict[str, str]:
        env = {
            "HARVEST_INVOICER_OIDC_ISSUER": "https://auth.example.com",
            "HARVEST_INVOICER_OIDC_CLIENT_ID": "invoicer",
            "HARVEST_INVOICER_OIDC_CLIENT_SECRET": "client-secret",
            "HARVEST_INVOICER_OIDC_ALLOWED_EMAILS": "jane@example.com,Bob@X.io",
            "HARVEST_INVOICER_SESSION_SECRET": self._SECRET,
            "HARVEST_INVOICER_PUBLIC_URL": "https://invoicer.example.com",
        }
        env.update(extra)
        return env

    def test_disabled_by_default(self, started: dict[str, object]) -> None:
        result = self._invoke()
        assert result.exit_code == 0, result.output
        app = started["app"]
        assert isinstance(app, Flask)
        assert "oidc_login" not in app.view_functions
        assert "unauthenticated editor" not in result.output  # loopback bind

    def test_enabled_from_env(self, started: dict[str, object]) -> None:
        bind_all = "0.0.0.0"  # noqa: S104 — test input, nothing is bound
        result = self._invoke("--host", bind_all, env=self._oidc_env())
        assert result.exit_code == 0, result.output
        app = started["app"]
        assert isinstance(app, Flask)
        assert "oidc_login" in app.view_functions
        assert "OIDC login" in result.output
        assert "unauthenticated" not in result.output
        # Unauthenticated requests are sent to the login page.
        resp = app.test_client().get("/")
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("/login")

    def test_missing_session_secret_fails_fast(
        self, started: dict[str, object]
    ) -> None:
        env = self._oidc_env()
        del env["HARVEST_INVOICER_SESSION_SECRET"]
        result = self._invoke(env=env)
        assert result.exit_code != 0
        assert "HARVEST_INVOICER_SESSION_SECRET" in result.output
        assert "app" not in started

    def test_empty_allow_list_fails_closed(self, started: dict[str, object]) -> None:
        env = self._oidc_env()
        del env["HARVEST_INVOICER_OIDC_ALLOWED_EMAILS"]
        result = self._invoke(env=env)
        assert result.exit_code != 0
        assert "--oidc-allow-any-user" in result.output
        assert "app" not in started

    def test_missing_public_url_fails_fast(self, started: dict[str, object]) -> None:
        env = self._oidc_env()
        del env["HARVEST_INVOICER_PUBLIC_URL"]
        result = self._invoke(env=env)
        assert result.exit_code != 0
        assert "--public-url" in result.output
        assert "app" not in started

    def test_session_lifetime_option(self, started: dict[str, object]) -> None:
        env = self._oidc_env(HARVEST_INVOICER_SESSION_LIFETIME="2")
        result = self._invoke(env=env)
        assert result.exit_code == 0, result.output
        app = started["app"]
        assert isinstance(app, Flask)
        assert app.permanent_session_lifetime.total_seconds() == 2 * 3600

    def test_oidc_options_without_issuer_rejected(
        self, started: dict[str, object]
    ) -> None:
        env = self._oidc_env()
        del env["HARVEST_INVOICER_OIDC_ISSUER"]
        result = self._invoke(env=env)
        assert result.exit_code != 0
        assert "--oidc-issuer" in result.output
        assert "app" not in started

    def test_secrets_from_files(
        self, tmp_path: Path, started: dict[str, object]
    ) -> None:
        # Mounted Kubernetes secrets end with a newline; it is stripped.
        secret_file = tmp_path / "client-secret"
        secret_file.write_text("from-file\n")
        session_file = tmp_path / "session-secret"
        session_file.write_text(self._SECRET + "\n")
        env = self._oidc_env(
            HARVEST_INVOICER_OIDC_CLIENT_SECRET_FILE=str(secret_file),
            HARVEST_INVOICER_SESSION_SECRET_FILE=str(session_file),
        )
        del env["HARVEST_INVOICER_OIDC_CLIENT_SECRET"]
        del env["HARVEST_INVOICER_SESSION_SECRET"]
        result = self._invoke(env=env)
        assert result.exit_code == 0, result.output
        app = started["app"]
        assert isinstance(app, Flask)
        assert app.secret_key == self._SECRET

    def test_secret_and_secret_file_conflict(
        self, tmp_path: Path, started: dict[str, object]
    ) -> None:
        secret_file = tmp_path / "client-secret"
        secret_file.write_text("from-file")
        env = self._oidc_env(HARVEST_INVOICER_OIDC_CLIENT_SECRET_FILE=str(secret_file))
        result = self._invoke(env=env)
        assert result.exit_code != 0
        assert "not both" in result.output

    def test_secrets_never_echoed(self, started: dict[str, object]) -> None:
        result = self._invoke(env=self._oidc_env())
        assert "client-secret" not in result.output
        assert self._SECRET not in result.output

    def test_trusted_proxies_default(self, started: dict[str, object]) -> None:
        # One proxy is trusted in OIDC mode: X-Forwarded-Proto is honored.
        self._invoke(env=self._oidc_env())
        app = started["app"]
        assert isinstance(app, Flask)
        assert isinstance(app.wsgi_app, ProxyFix)
        assert app.wsgi_app.x_proto == 1
        assert app.wsgi_app.x_host == 1

    def test_trusted_proxies_override(self, started: dict[str, object]) -> None:
        self._invoke("--trusted-proxies", "2", env=self._oidc_env())
        app = started["app"]
        assert isinstance(app, Flask)
        assert isinstance(app.wsgi_app, ProxyFix)
        assert app.wsgi_app.x_proto == 2

    def test_no_proxy_fix_without_oidc(self, started: dict[str, object]) -> None:
        self._invoke()
        app = started["app"]
        assert isinstance(app, Flask)
        assert not isinstance(app.wsgi_app, ProxyFix)

    def test_public_url_shown_as_editor_url(self, started: dict[str, object]) -> None:
        result = self._invoke(
            env=self._oidc_env(HARVEST_INVOICER_PUBLIC_URL="https://inv.example.com")
        )
        assert result.exit_code == 0, result.output
        assert "https://inv.example.com/" in result.output


class TestServeServer:
    """serve --server: waitress with OIDC, the Werkzeug dev server otherwise."""

    _SECRET = "s" * 32

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("OIDC_ISSUER", "SESSION_SECRET", "SERVER", "THREADS"):
            monkeypatch.delenv(f"HARVEST_INVOICER_{var}", raising=False)

    @pytest.fixture
    def servers(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, list[object]]:
        """Record which server ran (and with what) instead of serving."""
        import waitress  # noqa: PLC0415

        seen: dict[str, list[object]] = {"werkzeug": [], "waitress": []}

        def _run(app: Flask, **kwargs: object) -> None:
            seen["werkzeug"].append(kwargs)

        def _serve(app: object, **kwargs: object) -> None:
            seen["waitress"].append(kwargs)

        monkeypatch.setattr(Flask, "run", _run)
        monkeypatch.setattr(waitress, "serve", _serve)
        return seen

    def _oidc_env(self) -> dict[str, str]:
        return {
            "HARVEST_INVOICER_OIDC_ISSUER": "https://auth.example.com",
            "HARVEST_INVOICER_OIDC_CLIENT_ID": "invoicer",
            "HARVEST_INVOICER_OIDC_ALLOWED_EMAILS": "jane@example.com",
            "HARVEST_INVOICER_SESSION_SECRET": self._SECRET,
            "HARVEST_INVOICER_PUBLIC_URL": "https://invoicer.example.com",
        }

    def _invoke(self, *args: str, env: dict[str, str] | None = None) -> object:
        return CliRunner().invoke(
            main, ["serve", "--demo", "--no-browser", *args], env=env
        )

    def test_local_mode_uses_werkzeug(self, servers: dict[str, list[object]]) -> None:
        result = self._invoke("--port", "9001")
        assert result.exit_code == 0, result.output
        assert servers["waitress"] == []
        assert servers["werkzeug"] == [
            {"host": "127.0.0.1", "port": 9001, "debug": False, "threaded": True}
        ]

    def test_oidc_mode_uses_waitress(self, servers: dict[str, list[object]]) -> None:
        bind_all = "0.0.0.0"  # noqa: S104 — test input, nothing is bound
        result = self._invoke(
            "--host", bind_all, "--port", "9002", env=self._oidc_env()
        )
        assert result.exit_code == 0, result.output
        assert servers["werkzeug"] == []
        (kwargs,) = servers["waitress"]
        assert isinstance(kwargs, dict)
        assert kwargs["host"] == bind_all
        assert kwargs["port"] == 9002
        assert kwargs["threads"] == 8
        # ProxyFix (in the app) handles X-Forwarded-*: waitress must neither
        # interpret nor strip them.
        assert "trusted_proxy" not in kwargs
        assert kwargs["clear_untrusted_proxy_headers"] is False
        assert kwargs["ident"] == "harvest-invoicer"
        assert kwargs["max_request_body_size"] == 1024 * 1024

    def test_threads_option(self, servers: dict[str, list[object]]) -> None:
        env = {**self._oidc_env(), "HARVEST_INVOICER_THREADS": "3"}
        assert self._invoke(env=env).exit_code == 0
        (kwargs,) = servers["waitress"]
        assert isinstance(kwargs, dict)
        assert kwargs["threads"] == 3

    def test_force_waitress_locally(self, servers: dict[str, list[object]]) -> None:
        result = self._invoke("--server", "waitress", "--threads", "2")
        assert result.exit_code == 0, result.output
        assert servers["werkzeug"] == []
        (kwargs,) = servers["waitress"]
        assert isinstance(kwargs, dict)
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["threads"] == 2

    def test_force_werkzeug_with_oidc(self, servers: dict[str, list[object]]) -> None:
        env = {**self._oidc_env(), "HARVEST_INVOICER_SERVER": "werkzeug"}
        result = self._invoke(env=env)
        assert result.exit_code == 0, result.output
        assert servers["waitress"] == []
        assert len(servers["werkzeug"]) == 1

    @pytest.mark.parametrize(
        "args", [("--server", "gunicorn"), ("--threads", "0"), ("--threads", "x")]
    )
    def test_invalid_values_rejected(
        self, servers: dict[str, list[object]], args: tuple[str, str]
    ) -> None:
        result = self._invoke(*args)
        assert result.exit_code != 0
        assert "Invalid value" in result.output
        assert servers == {"werkzeug": [], "waitress": []}

    def test_sigterm_stops_waitress(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SIGTERM (Kubernetes) becomes SystemExit inside serve(), which waitress
        turns into a graceful shutdown; the previous handler is restored."""
        import signal  # noqa: PLC0415

        import waitress  # noqa: PLC0415

        before = signal.getsignal(signal.SIGTERM)
        raised: list[type[BaseException]] = []

        def _serve(app: object, **kwargs: object) -> None:
            try:
                signal.raise_signal(signal.SIGTERM)
            except SystemExit as exc:
                raised.append(type(exc))
                raise

        monkeypatch.setattr(waitress, "serve", _serve)
        result = self._invoke("--server", "waitress")
        assert raised == [SystemExit]
        assert result.exit_code == 0
        assert signal.getsignal(signal.SIGTERM) == before
