"""Helpers for the Shake Hash family."""

import functools
import hashlib
from collections.abc import Callable, Sequence
from typing import Protocol

from binapy import binapy_encoder


class ShakeProtocol(Protocol):
    def digest(self, length: int) -> bytes: ...  # pragma: no cover


def shake_hash(func: Callable[[bytes], ShakeProtocol], bp: bytes, length: int) -> bytes:
    """Calculate a Shake hash for a data.

    Args:
    ----
        func: the `hashlib` method to use for hashing
        bp: the data to hash
        length: the desired hash length

    Returns:
    -------
        the calculated hash

    """
    if length % 8:
        msg = "Shake-128 hash length is a number of bits and must be a multiple of 8"
        raise ValueError(msg)
    return func(bp).digest(length // 8)


for alg, func in (
    ("shake128", hashlib.shake_128),
    ("shake256", hashlib.shake_256),
):
    binapy_encoder(alg)(functools.partial(shake_hash, func))


def salted_shake_hash(
    func: Callable[[bytes], ShakeProtocol],
    bp: bytes,
    length: int,
    *,
    salt: bytes,
    append: bool = True,
) -> bytes:
    """Calculate a salted SHA.

    Args:
    ----
        func: the hash method from `hashlib` to use
        bp: the data to hash
        length: the desired hash length
        salt: the salt to use
        append: if `True`, salt will be appended to data. If `False`, it will be prepended.

    Returns:
    -------
        the calculated hash

    """
    if length % 8:
        msg = "Shake-128 hash length is a number of bits and must be a multiple of 8"
        raise ValueError(msg)

    salted = bp + salt if append else salt + bp
    return func(salted).digest(length // 8)


for alg, func in (
    ("sshake128", hashlib.shake_128),
    ("sshake256", hashlib.shake_256),
):
    binapy_encoder(alg)(functools.partial(salted_shake_hash, func))

__all__: Sequence[str] = []
