"""This module exposes all the Signature algorithms available from `jwskate`."""

from __future__ import annotations

from .ec import ES256, ES256K, ES384, ES512, BaseECSignatureAlg
from .eddsa import Ed448Dsa, Ed25519Dsa, EdDsa
from .hmac import HS256, HS384, HS512, BaseHMACSigAlg
from .rsa import PS256, PS384, PS512, RS256, RS384, RS512, BaseRSASigAlg

__all__ = [
    "ES256",
    "ES256K",
    "ES384",
    "ES512",
    "HS256",
    "HS384",
    "HS512",
    "PS256",
    "PS384",
    "PS512",
    "RS256",
    "RS384",
    "RS512",
    "BaseECSignatureAlg",
    "BaseHMACSigAlg",
    "BaseRSASigAlg",
    "Ed448Dsa",
    "Ed25519Dsa",
    "EdDsa",
]
