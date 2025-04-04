"""This module implements the Edwards-curve Digital Signature Algorithm (EdDSA)."""

from __future__ import annotations

from typing import Self, SupportsBytes, Union, override

from binapy import BinaPy
from cryptography import exceptions
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ed448, ed25519

from jwskate.jwa.base import BaseAsymmetricAlg, BaseSignatureAlg


class EdDsa(
    BaseAsymmetricAlg[
        Union[ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey],
        Union[ed25519.Ed25519PublicKey, ed448.Ed448PublicKey],
    ],
    BaseSignatureAlg,
):
    """EdDSA signature algorithms."""

    private_key_class = (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)
    public_key_class = (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)

    name = "EdDSA"
    description = __doc__

    @classmethod
    @override
    def with_random_key(cls) -> Self:
        return cls(ed25519.Ed25519PrivateKey.generate())

    @override
    def sign(self, data: bytes | SupportsBytes) -> BinaPy:
        if not isinstance(data, bytes):
            data = bytes(data)

        with self.private_key_required() as key:
            return BinaPy(key.sign(data))

    @override
    def verify(self, data: bytes | SupportsBytes, signature: bytes | SupportsBytes) -> bool:
        if not isinstance(data, bytes):
            data = bytes(data)
        if not isinstance(signature, bytes):
            signature = bytes(signature)

        with self.public_key_required() as key:
            try:
                key.verify(signature, data)
            except exceptions.InvalidSignature:
                return False
            else:
                return True


class Ed25519Dsa(
    BaseAsymmetricAlg[
        ed25519.Ed25519PrivateKey,
        ed25519.Ed25519PublicKey,
    ],
    BaseSignatureAlg,
):
    """EdDSA signature algorithm with Ed25519 curve."""

    description = __doc__
    hashing_alg = hashes.SHA256()

    private_key_class = ed25519.Ed25519PrivateKey
    public_key_class = ed25519.Ed25519PublicKey


class Ed448Dsa(
    BaseAsymmetricAlg[
        ed448.Ed448PrivateKey,
        ed448.Ed448PublicKey,
    ],
    BaseSignatureAlg,
):
    """EdDSA signature algorithm with Ed25519 curve."""

    description = __doc__
    hashing_alg = hashes.SHAKE256(114)

    private_key_class = ed448.Ed448PrivateKey
    public_key_class = ed448.Ed448PublicKey
