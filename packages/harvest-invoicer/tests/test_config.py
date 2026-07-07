"""Tests for the pydantic configuration models."""

from __future__ import annotations

import pytest
from harvest_invoicer.config import (
    ClientConfig,
    IssuerConfig,
    SmtpSettings,
    friendly_error,
    smtp_env_raw,
)
from pydantic import ValidationError


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
