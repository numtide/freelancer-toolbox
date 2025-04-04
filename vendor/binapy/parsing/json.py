"""This module contains helpers for converting data to/from JSON."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import Any

from binapy import binapy_parser, binapy_serializer


def _default_json_encode(data: Any) -> Any:
    """A JSON encoder which handles more default types.

    - `datetime` instances are converted to UTC timestamps.
    - `Mapping`  subclasses are converted to dict
    - `Iterable` subclasses are converted to list

    Args:
        data: the data to serialize

    Returns:
        the serialized data

    """
    if isinstance(data, datetime):
        return int(data.timestamp())
    if isinstance(data, Mapping):
        return dict(data)
    if isinstance(data, Iterable):
        return list(data)
    return str(data)


@binapy_parser("json")
def to_json(bp: bytes) -> Any:
    """Parse a JSON encoded string into a Python object (usually a `dict`).

    Args:
        bp: the data to parse as JSON

    Returns:
        the resulting Python object

    """
    return json.loads(bp)


@binapy_serializer("json")
def from_json(
    data: Any,
    *,
    compact: bool = True,
    default_encoder: Callable[[Any], Any] = _default_json_encode,
    **kwargs: Any,
) -> bytes:
    """Serialize a Python value (usually a `dict`) into a JSON formatted string.

    Args:
        data: the data to serialize to JSON
        compact: if `True`, produce a JSON that is as compact as possible (no spaces or new lines).
        default_encoder: the JSON encoder to use. By default, `datetime` will be serialized as UTC timestamps.
        **kwargs: additional parameters that will be passed to `json.dumps()`

    Returns:
        the JSON encoded string

    """
    if compact:
        kwargs.setdefault("separators", (",", ":"))
        kwargs.setdefault("indent", None)
    else:
        kwargs.setdefault("separators", (", ", ": "))
        kwargs.setdefault("indent", 2)
    return json.dumps(data, default=default_encoder, **kwargs).encode()
