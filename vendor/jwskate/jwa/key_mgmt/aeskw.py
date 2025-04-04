"""This module implements AES based Key Management algorithms."""

from __future__ import annotations

from typing import SupportsBytes, override

from binapy import BinaPy
from cryptography.hazmat.primitives import keywrap

from jwskate.jwa.base import BaseKeyManagementAlg, BaseSymmetricAlg, InvalidKey


class BaseAesKeyWrap(BaseKeyManagementAlg, BaseSymmetricAlg):
    """Base class for AES KW algorithms."""

    key_size: int
    """Required AES key size in bits."""

    @classmethod
    @override
    def check_key(cls, key: bytes) -> None:
        """Check that a key is valid for usage with this algorithm.

        To be valid, a key must be `bytes` and be of appropriate length (128, 192 or 256 bits).

        Args:
          key: a key to check

        Raises:
            ValueError: if the key is not appropriate

        """
        if not isinstance(key, bytes) or len(key) * 8 != cls.key_size:
            msg = f"Key must be {cls.key_size} bits."
            raise InvalidKey(msg)

    @classmethod
    def generate_key(cls) -> BinaPy:
        """Generate a key of an appropriate size for this AES alg subclass."""
        return BinaPy.random_bits(cls.key_size)

    def wrap_key(self, plainkey: bytes) -> BinaPy:
        """Wrap a key.

        Args:
          plainkey: the key to wrap.

        Returns:
          BinaPy: the wrapped key.

        """
        return BinaPy(keywrap.aes_key_wrap(self.key, plainkey))

    def unwrap_key(self, cipherkey: bytes | SupportsBytes) -> BinaPy:
        """Unwrap a key.

        Args:
          cipherkey: the wrapped key.

        Returns:
          BinaPy: the unwrapped key.

        """
        if not isinstance(cipherkey, bytes):
            cipherkey = bytes(cipherkey)

        return BinaPy(keywrap.aes_key_unwrap(self.key, cipherkey))


class A128KW(BaseAesKeyWrap):
    """AES Key Wrap with default initial value using 128-bit key."""

    name = "A128KW"
    description = __doc__
    key_size = 128


class A192KW(BaseAesKeyWrap):
    """AES Key Wrap with default initial value using 192-bit key."""

    name = "A192KW"
    description = __doc__
    key_size = 192


class A256KW(BaseAesKeyWrap):
    """AES Key Wrap with default initial value using 256-bit key."""

    name = "A256KW"
    description = __doc__
    key_size = 256
