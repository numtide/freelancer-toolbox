"""This module implements password-based Key Management Algorithms relying on PBES2."""

from __future__ import annotations

from typing import SupportsBytes

from binapy import BinaPy
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf import pbkdf2

from jwskate.jwa.base import BaseKeyManagementAlg

from .aeskw import A128KW, A192KW, A256KW, BaseAesKeyWrap


class BasePbes2(BaseKeyManagementAlg):
    """Base class for PBES2 based algorithms.

    PBES2 derives a cryptographic key from a human-provided password.

    Args:
        password: the encryption/decryption password to use

    """

    kwalg: type[BaseAesKeyWrap]
    hash_alg: hashes.HashAlgorithm

    MIN_SALT_SIZE = 8

    def __init__(self, password: SupportsBytes | bytes | str) -> None:
        if isinstance(password, str):
            password = password.encode("utf-8")
        if not isinstance(password, bytes):
            password = bytes(password)
        self.password = password

    @classmethod
    def generate_salt(cls, size: int = 12) -> BinaPy:
        """Generate a salt that is suitable for use for encryption.

        Args:
          size: size of the generated salt, in bytes

        Returns:
            the generated salt

        Raises:
            ValueError: if the salt is less than 8 bytes long

        """
        if size < cls.MIN_SALT_SIZE:
            msg = f"salts used for PBES2 must be at least {cls.MIN_SALT_SIZE} bytes long"
            raise ValueError(msg)
        return BinaPy.random(size)

    def derive(self, *, salt: bytes, count: int) -> BinaPy:
        """Derive an encryption key.

        Derivation is based on the configured password, a given salt and the number of
        PBKDF iterations.

        Args:
          salt: the generated salt
          count: number of PBKDF iterations

        Returns:
            the generated encryption/decryption key

        """
        full_salt = self.name.encode() + b"\0" + salt
        pbkdf = pbkdf2.PBKDF2HMAC(
            algorithm=self.hash_alg,
            length=self.kwalg.key_size // 8,
            salt=full_salt,
            iterations=count,
        )
        return BinaPy(pbkdf.derive(self.password))

    def wrap_key(self, plainkey: bytes, *, salt: bytes, count: int) -> BinaPy:
        """Wrap a key using this alg.

        Args:
          plainkey: the key to wrap
          salt: the salt to use
          count: the number of PBKDF iterations

        Returns:
            the wrapped key

        """
        aes_key = self.derive(salt=salt, count=count)
        return BinaPy(self.kwalg(aes_key).wrap_key(plainkey))

    def unwrap_key(self, cipherkey: bytes, *, salt: bytes, count: int) -> BinaPy:
        """Unwrap a key using this alg.

        Args:
          cipherkey: the wrapped key
          salt: the salt to use
          count: the number of PBKDF iterations

        Returns:
            the unwrapped key

        """
        aes_key = self.derive(salt=salt, count=count)
        return BinaPy(self.kwalg(aes_key).unwrap_key(cipherkey))


class Pbes2_HS256_A128KW(BasePbes2):  # noqa: N801
    """PBES2 with HMAC SHA-256 and "A128KW" wrapping."""

    name = "PBES2-HS256+A128KW"
    description = __doc__
    kwalg = A128KW
    hash_alg = hashes.SHA256()


class Pbes2_HS384_A192KW(BasePbes2):  # noqa: N801
    """PBES2 with HMAC SHA-384 and "A192KW" wrapping."""

    name = "PBES2-HS384+A192KW"
    description = __doc__
    kwalg = A192KW
    hash_alg = hashes.SHA384()


class Pbes2_HS512_A256KW(BasePbes2):  # noqa: N801
    """PBES2 with HMAC SHA-512 and "A256KW" wrapping."""

    name = "PBES2-HS512+A256KW"
    description = __doc__
    kwalg = A256KW
    hash_alg = hashes.SHA512()
