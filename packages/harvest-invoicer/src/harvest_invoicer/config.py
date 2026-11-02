"""Pydantic models: the single source of truth for the app's configuration.

Config records (issuer, client, email/SMTP) are validated and normalized
through these models at the boundaries — parsing a settings form, loading
from the state DB, layering environment overrides — then materialized as
plain dicts for the rest of the app (templates, rendering) to consume.

The SMTP password is a :class:`~pydantic.SecretStr` sourced only from the
environment; it is never serialized to the DB or echoed to the browser.
The same goes for the OIDC client secret and session key (:class:`OidcSettings`),
which come from ``serve`` options / environment only.
"""

from __future__ import annotations

import json
from email.utils import parseaddr
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

DEFAULT_SUBJECT_TEMPLATE = "{company} — Invoice {number}"
DEFAULT_MESSAGE_TEMPLATE = (
    "Hi,\n\nPlease find attached invoice {number} for {total}, due {due}.\n\nThank you."
)

Encryption = Literal["starttls", "ssl", "none"]
DefaultAction = Literal["generate", "send"]


def _validate_email_shape(v: str) -> str:
    """Reject clearly-invalid addresses; an empty string means "unset".

    A structural shape check only (one ``@``, a non-empty local part and a
    non-empty whitespace-free domain), not deliverability.  It rejects the
    values the bare ``"@" in v`` test let through (``"a@"``, ``"@"``,
    ``"a@@b"``) while still accepting single-label internal domains
    (``"user@localhost"``) for local-relay setups.
    """
    if not v:
        return v
    _, addr = parseaddr(v)
    local, sep, domain = addr.partition("@")
    if (
        not sep
        or not local
        or not domain
        or "@" in domain
        or any(c.isspace() for c in addr)
    ):
        msg = "Email must be a valid address."
        raise ValueError(msg)
    return v


def parse_tax_id_label(raw: str) -> str | dict[str, str]:
    """Parse the settings-form ``tax_id_label`` field.

    The same text field accepts either a plain label or a per-language
    JSON map (``{"en": "Tax ID", "es": "Identificador fiscal"}``), so the
    map survives the settings round-trip instead of being flattened to its
    ``str`` repr.  Anything that is not a well-formed non-empty object of
    string→string is kept as the plain trimmed string.
    """
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            val = json.loads(raw)
        except ValueError:
            return raw
        if (
            isinstance(val, dict)
            and val
            and all(isinstance(k, str) and isinstance(v, str) for k, v in val.items())
        ):
            return dict(val)
    return raw


def tax_id_label_field(v: object) -> str:
    """Render a stored ``tax_id_label`` back into the settings text field.

    A per-language map is shown as its JSON so it can be edited and saved
    again; a plain string is shown verbatim.
    """
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return str(v) if v else ""


# Non-secret SMTP fields overridable from the environment, mapped to their
# variable names (used for the read-only "set via env" UI indicators).
SMTP_ENV = {
    "host": "HARVEST_INVOICER_SMTP_HOST",
    "port": "HARVEST_INVOICER_SMTP_PORT",
    "username": "HARVEST_INVOICER_SMTP_USERNAME",
    "from_address": "HARVEST_INVOICER_SMTP_FROM_ADDRESS",
    "encryption": "HARVEST_INVOICER_SMTP_ENCRYPTION",
    "reply_to": "HARVEST_INVOICER_SMTP_REPLY_TO",
}


class BankConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    iban: str = ""
    bic: str = ""


class IssuerConfig(BaseModel):
    """The issuer (your business) details shown on every invoice."""

    model_config = ConfigDict(extra="ignore")
    name: str = ""
    email: str = ""
    address_line1: str = ""
    address_line2: str = ""
    country: str = ""
    phone: str = ""
    tax_id: str = ""
    tax_id_label: str | dict[str, str] = ""
    date_format: str = ""
    number_template: str = ""
    harvest_user: str = ""
    default_bill_to: str = ""
    language: str = ""
    legal_note: str = ""
    bank: BankConfig = Field(default_factory=BankConfig)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        return _validate_email_shape(v)


class ExtraLine(BaseModel):
    model_config = ConfigDict(extra="ignore")
    concept: str
    unit_price: float
    quantity: float = 1.0


class ClientConfig(BaseModel):
    """Billing details for one client."""

    model_config = ConfigDict(extra="ignore")
    name: str = ""
    address_line1: str = ""
    address_line2: str = ""
    country: str = ""
    tax_id: str = ""
    tax_id_label: str | dict[str, str] = ""
    email: str = ""
    language: str = ""
    vat_rate: float | None = None
    extra_lines: list[ExtraLine] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        return _validate_email_shape(v)

    @field_validator("vat_rate", mode="before")
    @classmethod
    def _blank_vat_is_unset(cls, v: object) -> object:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return None
            try:
                return float(stripped)
            except ValueError as exc:
                msg = "VAT rate must be a number between 0 and 1 (e.g. 0.21)."
                raise ValueError(msg) from exc
        return v

    @field_validator("vat_rate")
    @classmethod
    def _vat_range(cls, v: float | None) -> float | None:
        if v is not None and not 0.0 <= v <= 1.0:
            msg = "VAT rate must be a number between 0 and 1 (e.g. 0.21)."
            raise ValueError(msg)
        return v


class SmtpSettings(BaseSettings):
    """SMTP/email configuration, layering environment over stored values.

    Construct with the stored (DB) config as keyword arguments; any
    ``HARVEST_INVOICER_SMTP_*`` environment variable then overrides the
    matching field.  The password comes from the environment only.
    """

    model_config = SettingsConfigDict(
        env_prefix="HARVEST_INVOICER_SMTP_",
        populate_by_name=True,
        extra="ignore",
    )

    # Transport (env-overridable via HARVEST_INVOICER_SMTP_<FIELD>)
    host: str = ""
    port: int | None = None
    username: str = ""
    from_address: str = ""
    encryption: Encryption = "starttls"
    reply_to: str = ""
    # Secret: environment only, never persisted or dumped.
    password: SecretStr = Field(default=SecretStr(""), exclude=True)
    # Stored-only (still accept an env override if someone sets one)
    from_name: str = ""
    subject_template: str = DEFAULT_SUBJECT_TEMPLATE
    message_template: str = DEFAULT_MESSAGE_TEMPLATE
    default_action: DefaultAction = "generate"

    @field_validator("from_address", "reply_to")
    @classmethod
    def _address_shape(cls, v: str) -> str:
        # These feed the From:/Reply-To: headers, so hold them to the same
        # shape check as the issuer/client addresses.
        return _validate_email_shape(v)

    @field_validator("port", mode="before")
    @classmethod
    def _blank_port_is_unset(cls, v: object) -> object:
        # Settings forms and stored records use "" for "no port"; treat any
        # blank as unset so the default-per-encryption applies.
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return None
            if not stripped.isdigit():
                msg = "Port must be a number (e.g. 587)."
                raise ValueError(msg)
            return int(stripped)
        return v

    @field_validator("encryption", "default_action", mode="before")
    @classmethod
    def _blank_choice_is_default(cls, v: object, info: ValidationInfo) -> object:
        if isinstance(v, str) and not v.strip() and info.field_name:
            return cls.model_fields[info.field_name].default
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],  # noqa: ARG003
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Environment overrides the stored (init) values.
        return (env_settings, init_settings, file_secret_settings)


# Shortest accepted session secret: it signs the login cookie, so it must not
# be guessable (``openssl rand -hex 32`` gives 64 characters).
MIN_SESSION_SECRET_LENGTH = 32

DEFAULT_OIDC_SCOPES = "openid email profile"

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


class OidcSettings(BaseModel):
    """OpenID Connect login for a server deployment (``serve --oidc-*``).

    Present only when an issuer is configured; without it the editor is the
    local, unauthenticated app.  Validation fails closed: a session secret
    is required, and an empty allow-list is an error unless
    ``allow_any_user`` says otherwise.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    issuer: str
    client_id: str
    # Empty for a public (PKCE-only) client.
    client_secret: SecretStr = SecretStr("")
    scopes: str = DEFAULT_OIDC_SCOPES
    # Verified email addresses, matched case-insensitively.
    allowed_emails: frozenset[str] = frozenset()
    # Exact ``sub`` claims, for accounts without a usable email.
    allowed_subjects: frozenset[str] = frozenset()
    allow_any_user: bool = False
    session_secret: SecretStr
    # Externally visible origin (https://invoicer.example.com).  Required:
    # the redirect and post-logout URIs are built from it alone, never from
    # request headers; the CSRF guard also accepts its host.
    public_url: str = ""
    # Mark the session cookie Secure even when the request looks like http.
    secure_cookies: bool = False
    # Absolute login lifetime: a session older than this needs a new login.
    session_lifetime_hours: int = Field(default=12, ge=1, le=720)

    @field_validator("issuer")
    @classmethod
    def _issuer_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        parts = urlsplit(v)
        # Plain http only for a provider on this machine (development).
        local = parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS
        if not parts.hostname or not (parts.scheme == "https" or local):
            msg = "OIDC issuer must be an https:// URL."
            raise ValueError(msg)
        return v

    @field_validator("client_id")
    @classmethod
    def _client_id_set(cls, v: str) -> str:
        if not v.strip():
            msg = "OIDC client ID is required (--oidc-client-id)."
            raise ValueError(msg)
        return v.strip()

    @field_validator("scopes")
    @classmethod
    def _openid_scope(cls, v: str) -> str:
        scopes = v.split()
        if "openid" not in scopes:
            msg = "OIDC scopes must include 'openid'."
            raise ValueError(msg)
        return " ".join(scopes)

    @field_validator("allowed_emails", mode="before")
    @classmethod
    def _normalize_emails(cls, v: object) -> object:
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(e).strip().lower() for e in v if str(e).strip())
        return v

    @field_validator("allowed_subjects", mode="before")
    @classmethod
    def _normalize_subjects(cls, v: object) -> object:
        if isinstance(v, (list, tuple, set, frozenset)):
            return frozenset(str(e).strip() for e in v if str(e).strip())
        return v

    @field_validator("session_secret")
    @classmethod
    def _session_secret_strength(cls, v: SecretStr) -> SecretStr:
        secret = v.get_secret_value()
        if not secret:
            msg = (
                "OIDC login requires a session secret (--session-secret, "
                "HARVEST_INVOICER_SESSION_SECRET or HARVEST_INVOICER_SESSION_SECRET_FILE)."
            )
            raise ValueError(msg)
        if len(secret) < MIN_SESSION_SECRET_LENGTH:
            msg = (
                f"The session secret must be at least {MIN_SESSION_SECRET_LENGTH} "
                "characters (e.g. `openssl rand -hex 32`)."
            )
            raise ValueError(msg)
        return v

    @field_validator("public_url")
    @classmethod
    def _public_origin(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            msg = (
                "OIDC login requires the public URL (--public-url or "
                "HARVEST_INVOICER_PUBLIC_URL), e.g. https://invoicer.example.com."
            )
            raise ValueError(msg)
        parts = urlsplit(v)
        # Plain http only for the editor on this machine (development).
        local = parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS
        if (
            not (parts.scheme == "https" or local)
            or not parts.hostname
            or parts.path
            or parts.query
            or parts.fragment
        ):
            msg = (
                "Public URL must be an https:// origin like "
                "https://invoicer.example.com."
            )
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _allow_list_required(self) -> Self:
        if not (self.allowed_emails or self.allowed_subjects or self.allow_any_user):
            msg = (
                "OIDC login needs an allow-list (--oidc-allowed-email / "
                "--oidc-allowed-subject); pass --oidc-allow-any-user to admit "
                "every account the provider authenticates."
            )
            raise ValueError(msg)
        return self


def smtp_env_raw(field: str) -> str:
    """The raw environment value for an SMTP field ('' if unset)."""
    import os  # noqa: PLC0415

    var = SMTP_ENV.get(field)
    return os.environ.get(var, "").strip() if var else ""


def friendly_error(exc: ValidationError) -> str:
    """A readable one-line message from a pydantic validation error.

    Custom validators raise self-descriptive messages, so the field name is
    only prefixed for pydantic's own (type) errors to keep context.
    """
    for err in exc.errors():
        msg = str(err.get("msg", "invalid")).removeprefix("Value error, ")
        if err.get("type") == "value_error":  # our custom, self-descriptive msgs
            return msg
        loc = ".".join(str(p) for p in err.get("loc", ()))
        return f"{loc}: {msg}" if loc else msg
    return "Invalid configuration."
