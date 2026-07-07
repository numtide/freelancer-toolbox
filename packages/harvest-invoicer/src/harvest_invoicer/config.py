"""Pydantic models: the single source of truth for the app's configuration.

Config records (issuer, client, email/SMTP) are validated and normalized
through these models at the boundaries — parsing a settings form, loading
from the state DB, layering environment overrides — then materialized as
plain dicts for the rest of the app (templates, rendering) to consume.

The SMTP password is a :class:`~pydantic.SecretStr` sourced only from the
environment; it is never serialized to the DB or echoed to the browser.
"""

from __future__ import annotations

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
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
    tax_id_label: str = ""
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
        if v and "@" not in v:
            msg = "Email must be a valid address."
            raise ValueError(msg)
        return v


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
    tax_id_label: str = ""
    email: str = ""
    language: str = ""
    vat_rate: float | None = None
    extra_lines: list[ExtraLine] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, v: str) -> str:
        if v and "@" not in v:
            msg = "Email must be a valid address (missing '@')."
            raise ValueError(msg)
        return v

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
