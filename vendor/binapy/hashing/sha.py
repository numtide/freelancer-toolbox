"""This module contains helper methods for the SHA family of hash methods.

Those include SHA1, SHA256, etc.

"""

import functools
import hashlib
from collections.abc import Callable, Sequence
from typing import Protocol

from binapy import binapy_checker, binapy_encoder


class ShaProtocol(Protocol):
    def digest(self) -> bytes: ...  # pragma: no cover


def sha_hash(func: Callable[[bytes], ShaProtocol], bp: bytes) -> bytes:
    """Calculate a SHA hash for a data.

    Args:
    ----
        func: the `hashlib` method to use for hashing
        bp: the data to hash

    Returns:
    -------
        the calculated hash

    """
    return func(bp).digest()


def is_sha_hash(length: int, bp: bytes) -> bool:
    """Check if a data can be a SHA hash.

    Check is made based on the data length. Since SHA algorithms produce a fixed length hash, this is an easy check.
    Note that it is not because a data is the appropriate length that it has been produced by a SHA hash!

    Args:
    ----
        length: the expected length for data to be considered a SHA hash.
        bp: the data to check

    Returns:
    -------
        `True` if data has the appropriate length

    """
    return len(bp) == length


for alg, func, length in (
    ("sha1", hashlib.sha1, 20),
    ("sha256", hashlib.sha256, 32),
    ("sha384", hashlib.sha384, 48),
    ("sha512", hashlib.sha512, 64),
):
    # see why we need to use functools: https://stackoverflow.com/questions/3431676/creating-functions-in-a-loop
    binapy_encoder(alg)(functools.partial(sha_hash, func))
    binapy_checker(alg)(functools.partial(is_sha_hash, length))


def salted_sha_hash(func: Callable[[bytes], ShaProtocol], bp: bytes, *, salt: bytes, append: bool = True) -> bytes:
    """Calculate a salted SHA.

    Args:
    ----
        func: the hash method from `hashlib` to use
        bp: the data to hash
        salt: the salt to use
        append: if `True`, salt will be appended to data. If `False`, it will be prepended.

    Returns:
    -------
        the calculated hash

    """
    salted = bp + salt if append else salt + bp
    return func(salted).digest()


def is_salted_sha_hash(bp: bytes, min_len: int, max_len: int) -> bool:
    """Check if a `bytes` value can be a salted SHA hash.

    Check is done based on the data length.

    Args:
    ----
        min_len: minimum length for data to be considered a salted SHA
        max_len: max length for data to be considered a salted SHA
        bp: the data to check

    Returns:
    -------
        `True` if `min_len < len(bp) < max_len)

    """
    return min_len < len(bp) < max_len


for alg, func, min_length, max_length in (
    ("ssha1", hashlib.sha1, 20, 40),
    ("ssha256", hashlib.sha256, 32, 64),
    ("ssha384", hashlib.sha384, 48, 96),
    ("ssha512", hashlib.sha512, 64, 128),
):
    binapy_encoder(alg)(functools.partial(salted_sha_hash, func))
    binapy_checker(alg)(functools.partial(is_salted_sha_hash, min_len=min_length, max_len=max_length))

__all__: Sequence[str] = []
