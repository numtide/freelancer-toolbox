"""This module contains helpers for Base64, and other encodings based on the `base64` module."""

import base64
import string

from binapy import binapy_checker, binapy_decoder, binapy_encoder


@binapy_encoder("b64")
def encode_b64(bp: bytes) -> bytes:
    """Encode data using Base64.

    Args:
        bp: the data to encode

    Returns:
        the encoded data

    """
    return base64.b64encode(bp)


@binapy_decoder("b64")
def decode_b64(bp: bytes, *, strict: bool = True) -> bytes:
    """Decode data using Base64.

    Args:
    ----
        bp: the data to decode
        strict: if `True` (default), raise a `ValueError` if the data contains invalid characters for Base64.
            If `False`, ignore those characters.

    Returns:
    -------
        the decoded data

    """
    if strict and not is_b64(bp):
        msg = "not a base64"
        raise ValueError(msg)
    return base64.b64decode(bp)


@binapy_checker("b64")
def is_b64(bp: bytes) -> bool:
    """Check if a data is valid Base64 encoded data.

    Checks include:
    - size must be a multiple of 4
    - characters must be alphanumeric or + or /
    - padding must be done with `=` and be of the appropriate size to pad to a multiple of 4

    Args:
        bp: the data to check

    Returns:
        `True` if data is valid Base64, `False` otherwise.

    """
    if len(bp) % 4:
        return False
    payload_len = len(bp.rstrip(b"="))
    padding_size = 4 - (payload_len % 4)
    return set(bp.rstrip(b"=")).issubset(bytes(string.ascii_letters + string.digits + "+/", encoding="ascii")) and (
        padding_size == 4  # which means no padding
        or ((padding_size == 1 and bp.endswith(b"=")) or ((padding_size == 2) and bp.endswith(b"==")))
    )


@binapy_encoder("b64u")
def encode_b64u(bp: bytes) -> bytes:
    """Encode data using Base64-url.

    Args:
        bp: the data to encode

    Returns:
        the encoded data

    """
    return base64.urlsafe_b64encode(bp).rstrip(b"=")


@binapy_decoder("b64u")
def decode_b64u(bp: bytes, *, strict: bool = True) -> bytes:
    """Decode data using Base64-url.

    Args:
        bp: the data to decode
        strict: if `True` (default), raise a `ValueError` if the data contains invalid characters for Base64-url.
           If `False`, ignore those characters.

    Returns:
        the decoded data

    """
    if strict and not is_b64u(bp):
        msg = "not a base64u"
        raise ValueError(msg)
    data = bp
    padding_len = len(data) % 4
    if padding_len:
        data = data + b"=" * padding_len
    return base64.urlsafe_b64decode(data)


@binapy_checker("b64u")
def is_b64u(bp: bytes) -> bool:
    """Check if a data is valid Base64-url encoded data.

    Args:
        bp: the data to check

    Returns:
        `True` if data contains only valid Base64-url, `False` otherwise

    """
    return set(bp.rstrip(b"=")).issubset(bytes(string.ascii_letters + string.digits + "-_", encoding="ascii"))


@binapy_encoder("b32")
def encode_b32(bp: bytes) -> bytes:
    """Encode data using Base32.

    Args:
        bp: the data to encode

    Returns:
        the encoded data

    """
    return base64.b32encode(bp)


@binapy_decoder("b32")
def decode_b32(bp: bytes) -> bytes:
    """Decode data using Base32.

    Args:
        bp: the data to decode

    Returns:
        the decoded data

    """
    return base64.b32decode(bp)
