"""This module implements HMAC based signature algorithms."""

from __future__ import annotations

from typing import SupportsBytes, override

from binapy import BinaPy
from cryptography.hazmat.primitives import hashes, hmac

from jwskate.jwa.base import BaseSignatureAlg, BaseSymmetricAlg


class BaseHMACSigAlg(BaseSymmetricAlg, BaseSignatureAlg):
    """Base class for HMAC signature algorithms."""

    mac: type[hmac.HMAC] = hmac.HMAC
    min_key_size: int

    @classmethod
    def generate_key(cls) -> BinaPy:
        """Generate a key of an appropriate size for this HMAC alg subclass."""
        return BinaPy.random_bits(cls.min_key_size)

    @override
    def sign(self, data: bytes | SupportsBytes) -> BinaPy:
        if not isinstance(data, bytes):
            data = bytes(data)

        if self.read_only:
            raise NotImplementedError
        m = self.mac(self.key, self.hashing_alg)
        m.update(data)
        signature = m.finalize()
        return BinaPy(signature)

    @override
    def verify(self, data: bytes | SupportsBytes, signature: bytes | SupportsBytes) -> bool:
        if not isinstance(data, bytes):
            data = bytes(data)

        if not isinstance(signature, bytes):
            signature = bytes(signature)

        candidate_signature = self.sign(data)
        return candidate_signature == signature


class HS256(BaseHMACSigAlg):
    """HMAC using SHA-256."""

    name = "HS256"
    description = __doc__
    hashing_alg = hashes.SHA256()
    min_key_size = 256


class HS384(BaseHMACSigAlg):
    """HMAC using SHA-384."""

    name = "HS384"
    description = __doc__
    hashing_alg = hashes.SHA384()
    min_key_size = 384


class HS512(BaseHMACSigAlg):
    """HMAC using SHA-512."""

    name = "HS512"
    description = __doc__
    hashing_alg = hashes.SHA512()
    min_key_size = 512


class HS1(BaseHMACSigAlg):
    """HMAC using SHA-1."""

    name = "HS1"
    description = __doc__
    read_only = True
    min_key_size = 160
    hashing_alg = hashes.SHA1()  # noqa: S303
