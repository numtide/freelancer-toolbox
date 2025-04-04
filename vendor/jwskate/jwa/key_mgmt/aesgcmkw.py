"""This module implements AES-GCM based Key Management algorithms."""

from __future__ import annotations

from typing import TYPE_CHECKING, SupportsBytes

from jwskate.jwa.base import BaseKeyManagementAlg
from jwskate.jwa.encryption.aesgcm import BaseAESGCM

if TYPE_CHECKING:
    from binapy import BinaPy


class BaseAesGcmKeyWrap(BaseAESGCM, BaseKeyManagementAlg):
    """Base class for AES-GCM Key wrapping algorithms."""

    use = "enc"

    key_size: int
    """Required key size, in bits."""
    tag_size: int = 16
    """Authentication tag size, in bits."""
    iv_size: int = 96
    """Initialisation Vector size, in bits."""

    def wrap_key(self, plainkey: bytes | SupportsBytes, *, iv: bytes | SupportsBytes) -> tuple[BinaPy, BinaPy]:
        """Wrap a symmetric key, which is typically used as Content Encryption Key (CEK).

        This method is used by the sender of the encrypted message.

        This needs a random Initialisation Vector (`iv`) of the appropriate size,
        which you can generate using the classmethod `generate_iv()`.

        Args:
          plainkey: the key to wrap
          iv: the Initialisation Vector to use

        Returns:
          a tuple (wrapped_key, authentication_tag)

        """
        return self.encrypt(plainkey, iv=iv)

    def unwrap_key(
        self,
        cipherkey: bytes | SupportsBytes,
        *,
        tag: bytes | SupportsBytes,
        iv: bytes | SupportsBytes,
    ) -> BinaPy:
        """Unwrap a symmetric key.

        This method is used by the recipient of an encrypted message.

        This requires:
        - the same IV that was provided during encryption
        - the same Authentication Tag that was generated during encryption

        Args:
          cipherkey: the wrapped key
          tag: the authentication tag
          iv: the Initialisation Vector

        Returns:
          the unwrapped key.

        """
        return self.decrypt(cipherkey, auth_tag=tag, iv=iv)


class A128GCMKW(BaseAesGcmKeyWrap):
    """Key wrapping with AES GCM using 128-bit key."""

    name = "A128GCMKW"
    description = __doc__
    key_size = 128


class A192GCMKW(BaseAesGcmKeyWrap):
    """Key wrapping with AES GCM using 192-bit key."""

    name = "A192GCMKW"
    description = __doc__
    key_size = 192


class A256GCMKW(BaseAesGcmKeyWrap):
    """Key wrapping with AES GCM using 256-bit key."""

    name = "A256GCMKW"
    description = __doc__
    key_size = 256
