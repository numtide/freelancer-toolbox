"""This module implements AES-CBC with HMAC-SHA based Encryption algorithms."""

from __future__ import annotations

from typing import SupportsBytes

from binapy import BinaPy
from cryptography.hazmat.primitives import ciphers, constant_time, hashes, hmac, padding
from cryptography.hazmat.primitives.ciphers import algorithms, modes

from jwskate.jwa.base import BaseAESEncryptionAlg, MismatchingAuthTag


class BaseAesCbcHmacSha2(BaseAESEncryptionAlg):
    """Implements the family of AES-CBC with HMAC-SHA encryption algorithms."""

    mac_key_size: int
    """Required key size for the Hash algorithm, in bits."""

    aes_key_size: int
    """Required key size for the AES algorithm, in bits."""

    iv_size: int = 128
    """Initialization Vector size for the AES algorithm, in bits."""

    hash_alg: hashes.HashAlgorithm
    """Hash algorithm to use."""

    def __init__(self, key: bytes) -> None:
        """Initialize this wrapper with the given key.

        Args:
            key: the key to use for encryption and decryption.

        """
        super().__init__(key)
        self.mac_key = self.key[: self.mac_key_size // 8]
        self.aes_key = self.key[self.mac_key_size // 8 :]
        self.padding = padding.PKCS7(algorithms.AES.block_size)

    def mac(
        self,
        ciphertext: bytes | SupportsBytes,
        *,
        iv: bytes | SupportsBytes,
        aad: bytes | SupportsBytes | None = None,
    ) -> BinaPy:
        """Produce a Message Authentication Code for the given `ciphertext`, `iv` and `aad`.

        Args:
          ciphertext: the ciphertext
          iv: the Initialization Vector
          aad: the Additional Authenticated data

        Returns:
          the resulting MAC.

        """
        if not isinstance(ciphertext, bytes):
            ciphertext = bytes(ciphertext)
        if not isinstance(iv, bytes):
            iv = bytes(iv)
        if aad is None:  # pragma: no branch
            aad = b""
        elif not isinstance(aad, bytes):
            aad = bytes(aad)

        al = BinaPy.from_int(len(aad) * 8, length=8, byteorder="big", signed=False)
        hasher = hmac.HMAC(self.mac_key, self.hash_alg)

        for param in (aad, iv, ciphertext, al):
            hasher.update(param)
        digest = hasher.finalize()
        mac = digest[: self.tag_size]
        return BinaPy(mac)

    def encrypt(
        self,
        plaintext: bytes | SupportsBytes,
        *,
        iv: bytes | SupportsBytes,
        aad: bytes | SupportsBytes | None = None,
    ) -> tuple[BinaPy, BinaPy]:
        """Encrypt and MAC the given `plaintext`.

        This requires a given Initialization Vector (`iv`).
        An optional Additional Authenticated Data can be passed as parameter `aad`.

        Args:
          plaintext: the plain data to encrypt
          iv: the Initialization Vector
          aad: the Additional Authenticated Data, if any

        Returns:
          a tuple (encrypted_data, authentication_tag)

        """
        if not isinstance(plaintext, bytes):
            plaintext = bytes(plaintext)
        if not isinstance(iv, bytes):
            iv = bytes(iv)
        if aad is None:
            aad = b""
        elif not isinstance(aad, bytes):
            aad = bytes(aad)

        if len(iv) * 8 != self.iv_size:
            msg = f"Invalid IV size, must be {self.iv_size} bits"
            raise ValueError(msg)

        cipher = ciphers.Cipher(algorithms.AES(self.aes_key), modes.CBC(iv)).encryptor()
        padder = self.padding.padder()
        padded_text = padder.update(plaintext) + padder.finalize()
        ciphertext = cipher.update(padded_text) + cipher.finalize()
        mac = self.mac(ciphertext, iv=iv, aad=aad)
        return BinaPy(ciphertext), BinaPy(mac)

    def decrypt(
        self,
        ciphertext: bytes | SupportsBytes,
        *,
        iv: bytes | SupportsBytes,
        auth_tag: bytes | SupportsBytes,
        aad: bytes | SupportsBytes | None = None,
    ) -> BinaPy:
        """Decrypt and authenticate a given ciphertext.

        If the text was encrypted with an authentication tag, an Additional Authenticated Data must be supplied
        (as produced by `encrypt()`).

        Args:
          ciphertext: the ciphertext
          auth_tag: the authentication tag
          iv: the Initialization Vector
          aad: the Additional Authenticated Data, if any

        Returns:
          the decrypted data

        """
        if not isinstance(ciphertext, bytes):
            ciphertext = bytes(ciphertext)
        if not isinstance(iv, bytes):
            iv = bytes(iv)
        if not isinstance(auth_tag, bytes):
            auth_tag = bytes(auth_tag)
        if aad is None:  # pragma: no branch
            aad = b""
        elif not isinstance(aad, bytes):
            aad = bytes(aad)

        if len(iv) * 8 != self.iv_size:
            msg = f"Invalid IV size, must be {self.iv_size} bits"
            raise ValueError(msg)

        mac = self.mac(ciphertext, iv=iv, aad=aad)
        if not constant_time.bytes_eq(mac, auth_tag):
            raise MismatchingAuthTag

        cipher = ciphers.Cipher(algorithms.AES(self.aes_key), modes.CBC(iv)).decryptor()
        padded_text = cipher.update(ciphertext) + cipher.finalize()
        unpadder = self.padding.unpadder()
        return BinaPy(unpadder.update(padded_text) + unpadder.finalize())


class A128CBC_HS256(BaseAesCbcHmacSha2):  # noqa: N801
    """AES_128_CBC_HMAC_SHA_256."""

    name = "A128CBC-HS256"
    description = __doc__
    mac_key_size = 128
    aes_key_size = 128
    key_size = mac_key_size + aes_key_size
    tag_size = 16
    hash_alg = hashes.SHA256()


class A192CBC_HS384(BaseAesCbcHmacSha2):  # noqa: N801
    """AES_192_CBC_HMAC_SHA_384."""

    name = "A192CBC-HS384"
    description = __doc__
    mac_key_size = 192
    aes_key_size = 192
    key_size = mac_key_size + aes_key_size
    tag_size = 24
    hash_alg = hashes.SHA384()


class A256CBC_HS512(BaseAesCbcHmacSha2):  # noqa: N801
    """AES_256_CBC_HMAC_SHA_512."""

    name = "A256CBC-HS512"
    description = __doc__
    mac_key_size = 256
    aes_key_size = 256
    key_size = mac_key_size + aes_key_size
    tag_size = 32
    hash_alg = hashes.SHA512()
