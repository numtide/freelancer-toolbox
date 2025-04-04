"""This module implements RSA based Key Management algorithms."""

from __future__ import annotations

from typing import Any, Self, SupportsBytes, override

from binapy import BinaPy
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from jwskate.jwa.base import BaseAsymmetricAlg, BaseKeyManagementAlg


class BaseRsaKeyWrap(
    BaseKeyManagementAlg,
    BaseAsymmetricAlg[rsa.RSAPrivateKey, rsa.RSAPublicKey],
):
    """Base class for RSA Key Wrapping algorithms."""

    padding: Any

    name: str
    description: str

    private_key_class = rsa.RSAPrivateKey
    public_key_class = rsa.RSAPublicKey

    min_key_size: int = 2048

    @classmethod
    @override
    def with_random_key(cls) -> Self:
        return cls(rsa.generate_private_key(public_exponent=65537, key_size=cls.min_key_size))

    def wrap_key(self, plainkey: bytes) -> BinaPy:
        """Wrap a symmetric key using this algorithm.

        Args:
          plainkey: the symmetric key to wrap

        Returns:
            the wrapped key

        Raises:
            PublicKeyRequired: if this algorithm is initialized with a private key instead of a public key

        """
        if self.read_only:
            msg = "Due to security reasons, this algorithm is only usable for decryption."
            raise NotImplementedError(msg)
        with self.public_key_required() as key:
            return BinaPy(key.encrypt(plainkey, self.padding))

    def unwrap_key(self, cipherkey: bytes | SupportsBytes) -> BinaPy:
        """Unwrap a symmetric key with this alg.

        Args:
          cipherkey: the wrapped key

        Returns:
            the unwrapped clear-text key
        Raises:
            PrivateKeyRequired: if this alg is initialized with a public key instead of a private key

        """
        if not isinstance(cipherkey, bytes):
            cipherkey = bytes(cipherkey)

        with self.private_key_required() as key:
            return BinaPy(key.decrypt(cipherkey, self.padding))


class RsaEsPcks1v1_5(BaseRsaKeyWrap):  # noqa: N801
    """RSAES-PKCS1-v1_5."""

    name = "RSA1_5"
    description = __doc__
    read_only = True

    padding = padding.PKCS1v15()


class RsaEsOaep(BaseRsaKeyWrap):
    """RSAES OAEP using default parameters."""

    name = "RSA-OAEP"
    description = __doc__

    padding = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA1()),  # noqa: S303
        algorithm=hashes.SHA1(),  # noqa: S303
        label=None,
    )


class RsaEsOaepSha256(BaseRsaKeyWrap):
    """RSAES OAEP using SHA-256 and MGF1 with SHA-256."""

    name = "RSA-OAEP-256"
    description = __doc__

    padding = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )


class RsaEsOaepSha384(BaseRsaKeyWrap):
    """RSA-OAEP using SHA-384 and MGF1 with SHA-384."""

    name = "RSA-OAEP-384"
    description = __doc__

    padding = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA384()),
        algorithm=hashes.SHA384(),
        label=None,
    )


class RsaEsOaepSha512(BaseRsaKeyWrap):
    """RSA-OAEP using SHA-512 and MGF1 with SHA-512."""

    name = "RSA-OAEP-512"
    description = __doc__

    padding = padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA512()),
        algorithm=hashes.SHA512(),
        label=None,
    )
