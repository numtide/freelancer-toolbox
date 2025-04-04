"""This module implements helpers for (de)serializing to/from Python `pickle` objects."""

from __future__ import annotations

import pickle
from pickle import PickleBuffer
from typing import TYPE_CHECKING, Any

from binapy import binapy_parser, binapy_serializer

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


@binapy_serializer("pickle")
def to_pickle(
    o: object,
    *,
    protocol: int | None = None,
    fix_imports: bool = True,
    buffer_callback: Callable[[PickleBuffer], Any] | None = None,
) -> bytes:
    """Serialize an object using `pickle.dumps()`."""
    return pickle.dumps(o, protocol=protocol, fix_imports=fix_imports, buffer_callback=buffer_callback)


@binapy_parser("pickle")
def from_pickle(
    bp: bytes,
    *,
    fix_imports: bool = True,
    encoding: str = "ASCII",
    errors: str = "strict",
    buffers: Iterable[object] | None = None,
) -> object:
    """Deserialize an object using `pickle.loads()`."""
    return pickle.loads(bp, fix_imports=fix_imports, encoding=encoding, errors=errors, buffers=buffers)  # noqa: S301
