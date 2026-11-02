"""Tests for the pydantic configuration models."""

from __future__ import annotations

import pytest
from harvest_invoicer.config import (
    ClientConfig,
    IssuerConfig,
    OidcSettings,
    SmtpSettings,
    friendly_error,
    parse_tax_id_label,
    smtp_env_raw,
)
from pydantic import ValidationError


class TestParseTaxIdLabel:
    def test_plain_string_kept(self) -> None:
        assert parse_tax_id_label("VAT No.") == "VAT No."
        assert parse_tax_id_label("  NIF  ") == "NIF"
        assert parse_tax_id_label("") == ""

    def test_json_map_parsed(self) -> None:
        assert parse_tax_id_label('{"en": "Tax ID", "es": "NIF"}') == {
            "en": "Tax ID",
            "es": "NIF",
        }

    @pytest.mark.parametrize(
        "raw",
        ['{"en": 5}', "{}", "{not json", '["en", "es"]', '"just a string"'],
    )
    def test_malformed_map_kept_as_string(self, raw: str) -> None:
        # Anything that is not a non-empty string->string object stays a string.
        assert parse_tax_id_label(raw) == raw.strip()


class TestSmtpSettings:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in (
            "HOST",
            "PORT",
            "USERNAME",
            "FROM_ADDRESS",
            "ENCRYPTION",
            "REPLY_TO",
            "PASSWORD",
        ):
            monkeypatch.delenv(f"HARVEST_INVOICER_SMTP_{var}", raising=False)

    def test_stored_values(self) -> None:
        s = SmtpSettings(
            host="db-host", port="587", username="u", from_address="a@b.io"
        )
        assert s.host == "db-host"
        assert s.port == 587  # coerced from str
        assert s.from_address == "a@b.io"
        assert s.password.get_secret_value() == ""

    def test_env_overrides_stored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_HOST", "env-host")
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_FROM_ADDRESS", "env@from.io")
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_PASSWORD", "secret")
        s = SmtpSettings(host="db-host", from_address="db@from.io")
        assert s.host == "env-host"
        assert s.from_address == "env@from.io"
        assert s.password.get_secret_value() == "secret"

    def test_from_address_shape_validated(self) -> None:
        with pytest.raises(ValidationError):
            SmtpSettings(host="h", from_address="a@@b")
        with pytest.raises(ValidationError):
            SmtpSettings(host="h", reply_to="nope@")
        # Empty is fine (unset), and a normal address passes.
        assert SmtpSettings(host="h").from_address == ""
        assert SmtpSettings(host="h", from_address="me@x.io").from_address == "me@x.io"

    def test_password_excluded_from_dump(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_PASSWORD", "secret")
        s = SmtpSettings(host="h")
        assert "password" not in s.model_dump()
        assert "secret" not in repr(s)  # SecretStr masks in repr

    def test_blank_port_is_unset(self) -> None:
        assert SmtpSettings(host="h", port="").port is None
        assert SmtpSettings(host="h", encryption="").encryption == "starttls"

    def test_bad_port_raises_friendly(self) -> None:
        with pytest.raises(ValidationError) as ei:
            SmtpSettings(host="h", port="not-a-port")
        assert "Port must be a number" in friendly_error(ei.value)

    def test_smtp_env_raw(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HARVEST_INVOICER_SMTP_HOST", "h")
        assert smtp_env_raw("host") == "h"
        assert smtp_env_raw("username") == ""
        assert smtp_env_raw("from_name") == ""  # not env-backed


class TestClientConfig:
    def test_vat_range_and_coercion(self) -> None:
        assert ClientConfig(vat_rate="0.21").vat_rate == pytest.approx(0.21)
        assert ClientConfig(vat_rate="").vat_rate is None
        with pytest.raises(ValidationError):
            ClientConfig(vat_rate="1.5")
        with pytest.raises(ValidationError):
            ClientConfig(vat_rate="abc")

    def test_email_shape(self) -> None:
        with pytest.raises(ValidationError):
            ClientConfig(email="notanemail")
        assert ClientConfig(email="a@b.io").email == "a@b.io"

    @pytest.mark.parametrize("bad", ["a@", "@", "@b.io", "a@@b"])
    def test_email_shape_rejects_malformed(self, bad: str) -> None:
        # The old bare `"@" in v` check let all of these through.
        with pytest.raises(ValidationError):
            ClientConfig(email=bad)

    @pytest.mark.parametrize(
        "ok", ["a@b.io", "user@sub.example.co.uk", "a+b@x.io", "user@localhost"]
    )
    def test_email_shape_accepts_valid_including_internal(self, ok: str) -> None:
        # Single-label internal domains stay valid for local-relay setups.
        assert ClientConfig(email=ok).email == ok

    def test_email_empty_is_allowed(self) -> None:
        assert ClientConfig(email="").email == ""

    def test_extra_lines_coerced(self) -> None:
        c = ClientConfig(
            extra_lines=[{"concept": "Fee", "unit_price": "10", "quantity": "2"}]
        )
        assert c.extra_lines[0].unit_price == pytest.approx(10.0)
        assert c.extra_lines[0].quantity == pytest.approx(2.0)


class TestIssuerConfig:
    def test_bad_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IssuerConfig(email="nope")

    def test_defaults_and_bank(self) -> None:
        i = IssuerConfig(name="Jane", bank={"iban": "DE00", "bic": "X"})
        assert i.name == "Jane"
        assert i.bank.iban == "DE00"
        assert i.language == ""


class TestOidcSettings:
    _SECRET = "s" * 32

    def _make(self, **overrides: object) -> OidcSettings:
        fields: dict[str, object] = {
            "issuer": "https://auth.example.com",
            "client_id": "invoicer",
            "session_secret": self._SECRET,
            "allowed_emails": ["Jane@Example.com"],
            "public_url": "https://invoicer.example.com",
        }
        fields.update(overrides)
        return OidcSettings(**fields)

    def test_valid_config_normalized(self) -> None:
        s = self._make(
            issuer="https://auth.example.com/",
            public_url="https://invoicer.example.com/",
            allowed_emails=[" Jane@Example.com ", "bob@x.io"],
        )
        assert s.issuer == "https://auth.example.com"
        assert s.public_url == "https://invoicer.example.com"
        # Emails match case-insensitively: stored lower-cased.
        assert s.allowed_emails == frozenset({"jane@example.com", "bob@x.io"})
        assert s.scopes == "openid email profile"

    def test_session_secret_required(self) -> None:
        with pytest.raises(ValidationError) as ei:
            self._make(session_secret="")
        assert "session secret" in friendly_error(ei.value)

    def test_short_session_secret_rejected(self) -> None:
        with pytest.raises(ValidationError) as ei:
            self._make(session_secret="too-short")  # noqa: S106
        assert "at least 32 characters" in friendly_error(ei.value)

    def test_empty_allow_list_fails_closed(self) -> None:
        with pytest.raises(ValidationError) as ei:
            self._make(allowed_emails=[])
        assert "--oidc-allow-any-user" in friendly_error(ei.value)

    def test_allow_any_user_is_explicit_opt_out(self) -> None:
        s = self._make(allowed_emails=[], allow_any_user=True)
        assert s.allow_any_user

    def test_subjects_alone_are_an_allow_list(self) -> None:
        s = self._make(allowed_emails=[], allowed_subjects=["12345"])
        assert s.allowed_subjects == frozenset({"12345"})

    def test_client_id_required(self) -> None:
        with pytest.raises(ValidationError) as ei:
            self._make(client_id=" ")
        assert "client ID" in friendly_error(ei.value)

    @pytest.mark.parametrize(
        "bad", ["auth.example.com", "http://auth.example.com", "ftp://x.io"]
    )
    def test_issuer_must_be_https(self, bad: str) -> None:
        with pytest.raises(ValidationError) as ei:
            self._make(issuer=bad)
        assert "https" in friendly_error(ei.value)

    def test_plain_http_issuer_allowed_on_loopback(self) -> None:
        # Local development against a provider on this machine.
        assert self._make(issuer="http://127.0.0.1:9000").issuer.startswith("http:")

    def test_openid_scope_required(self) -> None:
        with pytest.raises(ValidationError) as ei:
            self._make(scopes="email profile")
        assert "openid" in friendly_error(ei.value)

    @pytest.mark.parametrize(
        "bad", ["invoicer.example.com", "https://x.io/sub", "https://x.io?a=1"]
    )
    def test_public_url_must_be_an_origin(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            self._make(public_url=bad)

    def test_public_url_required(self) -> None:
        with pytest.raises(ValidationError) as ei:
            self._make(public_url="")
        assert "--public-url" in friendly_error(ei.value)

    def test_plain_http_public_url_only_on_loopback(self) -> None:
        assert self._make(public_url="http://localhost:8321").public_url
        with pytest.raises(ValidationError):
            self._make(public_url="http://invoicer.example.com")

    def test_session_lifetime(self) -> None:
        assert self._make().session_lifetime_hours == 12
        assert self._make(session_lifetime_hours=1).session_lifetime_hours == 1
        with pytest.raises(ValidationError):
            self._make(session_lifetime_hours=0)

    def test_secrets_masked_in_repr(self) -> None:
        s = self._make(client_secret="top-secret")  # noqa: S106
        assert "top-secret" not in repr(s)
        assert self._SECRET not in repr(s)
