"""This module implement base classes for the algorithms defined in JWA."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Generic, Self, SupportsBytes, TypeVar, override

import cryptography.exceptions
from binapy import BinaPy

if TYPE_CHECKING:
    from collections.abc import Iterator

    from cryptography.hazmat.primitives import hashes


class PrivateKeyRequired(AttributeError):
    """Raised when a public key is provided for an operation that requires a private key."""


class PublicKeyRequired(AttributeError):
    """Raised when a private key is provided for an operation that requires a public key."""


class InvalidKey(ValueError):
    """Raised when an unsuitable key is provided to an algorithm."""


class BaseAlg:
    """Base class for all algorithms.

    An algorithm has a `name` and a `description`, whose reference is found in [IANA JOSE registry][IANA].

    [IANA]: https://www.iana.org/assignments/jose/jose.xhtml#web-signature-encryption-algorithms

    """

    use: str
    """Alg use ('sig' or 'enc')"""

    name: str
    """Technical name of the algorithm."""
    description: str
    """Description of the algorithm (human readable)"""
    read_only: bool = False
    """For algs that are considered insecure, set to True to allow only signature verification or
    decryption of existing data, but don't allow new signatures or encryption."""

    def __repr__(self) -> str:
        """Use the name of the alg as repr."""
        return self.name

    @classmethod
    def with_random_key(cls) -> Self:
        """Initialize an instance of this alg with a randomly-generated key."""
        return cls(cls.generate_key())  # type: ignore[call-arg, attr-defined]


class BaseSymmetricAlg(BaseAlg):
    """Base class for Symmetric algorithms (using a raw bytes key).

    Args:
        key: the key to use for cryptographic operations

    """

    def __init__(self, key: bytes) -> None:
        self.check_key(key)
        self.key = key

    @classmethod
    def check_key(cls, key: bytes) -> None:
        """Check that a given key is suitable for this alg class.

        This raises an exception if the key is not suitable.
        This method must be implemented by subclasses as required.

        Args:
          key: the key to check for this alg class

        Returns:
          Returns `None`. Raises an exception if the key is not suitable

        Raises:
            InvalidKey: if the key is not suitable for this algorithm

        """

    @classmethod
    def supports_key(cls, key: bytes) -> bool:
        """Return `True` if the given key is suitable for this alg class, or `False` otherwise.

        This is a convenience wrapper around `check_key(key)`.

        Args:
          key: the key to check for this alg class

        Returns:
          `True` if the key is suitable for this alg class, `False` otherwise

        """
        try:
            cls.check_key(key)
        except InvalidKey:
            return False
        else:
            return True


Kpriv = TypeVar("Kpriv")
Kpub = TypeVar("Kpub")


class BaseAsymmetricAlg(Generic[Kpriv, Kpub], BaseAlg):
    """Base class for asymmetric algorithms. Those can be initialised with a private or public key.

    The available cryptographic operations will depend on the alg and
    the provided key type.

    Args:
        key: the key to use.

    """

    private_key_class: type[Kpriv] | tuple[type[Kpriv], ...]
    public_key_class: type[Kpub] | tuple[type[Kpub], ...]

    def __init__(self, key: Kpriv | Kpub) -> None:
        self.check_key(key)
        self.key = key

    @classmethod
    def check_key(cls, key: Kpriv | Kpub) -> None:
        """Check that a given key is suitable for this alg class.

        This must be implemented by subclasses as required.

        Args:
          key: the key to use.

        Returns:
          Returns None. Raises an exception if the key is not suitable.

        Raises:
            Exception: if the key is not suitable for use with this alg class

        """

    @contextmanager
    def private_key_required(self) -> Iterator[Kpriv]:
        """Check if this alg is initialised with a private key, as a context manager.

        Yields:
            the private key

        Raises:
            PrivateKeyRequired: if the configured key is not private

        """
        if not isinstance(self.key, self.private_key_class):
            raise PrivateKeyRequired
        yield self.key  # type: ignore[misc]

    @contextmanager
    def public_key_required(self) -> Iterator[Kpub]:
        """Check if this alg is initialised with a public key, as a context manager.

        Yields:
            The public key

        Raises:
            PublicKeyRequired: if the configured key is private

        """
        if not isinstance(self.key, self.public_key_class):
            raise PublicKeyRequired
        yield self.key  # type: ignore[misc]

    def public_key(self) -> Kpub:
        """Return the public key matching the private key."""
        if hasattr(self.key, "public_key"):
            return self.key.public_key()  # type: ignore[no-any-return]
        raise NotImplementedError

    def public_alg(self) -> Self:
        """Return an alg instance initialised with the public key."""
        with self.private_key_required():
            return self.__class__(self.public_key())


class BaseSignatureAlg(BaseAlg):
    """Base class for signature algorithms."""

    use = "sig"
    hashing_alg: hashes.HashAlgorithm

    def sign(self, data: bytes | SupportsBytes) -> BinaPy:
        """Sign arbitrary data, return the signature.

        Args:
          data: raw data to sign

        Returns:
          the raw signature

        """
        raise NotImplementedError

    def verify(self, data: bytes | SupportsBytes, signature: bytes | SupportsBytes) -> bool:
        """Verify a signature against some data.

        Args:
          data: the raw data to verify
          signature: the raw signature

        Returns:
          `True` if the signature matches, `False` otherwise.

        """
        raise NotImplementedError


class BaseAESEncryptionAlg(BaseSymmetricAlg):
    """Base class for AES encryption algorithms."""

    use = "enc"

    key_size: int
    tag_size: int
    iv_size: int

    @classmethod
    def check_key(cls, key: bytes) -> None:
        """Check that a key is suitable for this algorithm.

        Args:
          key: the key to check

        Raises:
            InvalidKey: if the key is not suitable

        """
        if len(key) * 8 != cls.key_size:
            msg = f"This key size of {len(key) * 8} bits doesn't match the expected key size of {cls.key_size} bits"
            raise InvalidKey(msg)

    @classmethod
    def generate_key(cls) -> BinaPy:
        """Generate a key of an appropriate size for this AES alg subclass.

        Returns:
            a random AES key

        """
        return BinaPy.random_bits(cls.key_size)

    @classmethod
    def generate_iv(cls) -> BinaPy:
        """Generate an Initialisation Vector of the appropriate size.

        Returns:
            a random IV

        """
        return BinaPy.random_bits(cls.iv_size)

    def encrypt(
        self,
        plaintext: bytes | SupportsBytes,
        *,
        iv: bytes | SupportsBytes,
        aad: bytes | SupportsBytes | None = None,
    ) -> tuple[BinaPy, BinaPy]:
        """Encrypt arbitrary data, with optional Authenticated Encryption.

        This needs as parameters:

        - the raw data to encrypt (`plaintext`)
        - a given random Initialisation Vector (`iv`) of the appropriate size
        - optional Additional Authentication Data (`aad`)

        And returns a tuple `(ciphered_data, authentication_tag)`.

        Args:
          plaintext: the data to encrypt
          iv: the Initialisation Vector to use
          aad: the Additional Authentication Data

        Returns:
          a tuple of ciphered data and authentication tag

        """
        raise NotImplementedError

    def decrypt(
        self,
        ciphertext: bytes | SupportsBytes,
        *,
        iv: bytes | SupportsBytes,
        auth_tag: bytes | SupportsBytes,
        aad: bytes | SupportsBytes | None = None,
    ) -> BinaPy:
        """Decrypt and verify a ciphertext with Authenticated Encryption.

        This needs:

        - the raw encrypted Data (`ciphertext`) and Authentication Tag (`auth_tag`) that were produced by encryption,
        - the same Initialisation Vector (`iv`) and optional Additional Authentication Data that were provided for
        encryption.

        Returns the resulting clear text data.

        Args:
          ciphertext: the data to decrypt
          iv: the Initialisation Vector to use. Must be the same one used during encryption
          auth_tag: the authentication tag
          aad: the Additional Authentication Data. Must be the same one used during encryption

        Returns:
          the deciphered data

        """
        raise NotImplementedError

    @classmethod
    @override
    def with_random_key(cls) -> Self:
        """Initialize this alg with a random key.

        Returns:
            a subclass of `BaseAESEncryptionAlg` initialized with a randomly generated key

        """
        return cls(cls.generate_key())


class BaseKeyManagementAlg(BaseAlg):
    """Base class for Key Management algorithms."""

    use = "enc"


class MismatchingAuthTag(cryptography.exceptions.InvalidTag):
    """Raised during decryption, when the Authentication Tag doesn't match the expected value."""
