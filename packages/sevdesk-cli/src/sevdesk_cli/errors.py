"""Error classes for SevDesk CLI."""

from __future__ import annotations


class SevDeskCLIError(Exception):
    """Base exception for SevDesk CLI errors."""


class ConfigError(SevDeskCLIError):
    """Error raised for configuration issues."""


class AuthenticationError(SevDeskCLIError):
    """Error raised for authentication issues."""
