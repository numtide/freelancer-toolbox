"""Implement support for 'dumb' ciphers such as Caesar cipher."""

from __future__ import annotations

import string

from binapy import binapy_decoder, binapy_encoder


@binapy_encoder("caesar")
def encode_caesar(
    bp: bytes,
    shift: int,
    alphabet: None | str | bytes = None,
) -> bytes:
    """Encode data with Caesar cipher.

    This shifts each character from `bp` by `shift` positions in the given `alphabet`.
    Characters from `bp` that are not in the alphabet are left as-is.
    Alphabet is usually `string.ascii_lowercase`, `string.ascii_uppercase`, but you may pass any
    alphabet, either as a `str` (which will be encoded using 'utf-8'), or as `bytes` directly.
    By default, alphabet will be auto-detected:

    - `string.ascii_uppercase` if all character from the input are uppercase letters ASCII codes
    - `string.ascii_lowercase` if all character from the input are lowercase letters ASCII codes
    - `string.ascii_letters` if all character from the input are letters (both upper and lower case) ASCII codes
    - the full ASCII range (0-127) if all characters are valid ASCII
    - the full octect range (0-255) otherwise

    Args:
        bp: input data.
        shift: number of places to shift each character in the alphabet.
        alphabet: alphabet to use. Leave `None` to try to auto-detect alphabet

    Returns:
        the result of applying Caesar-cipher with `shift` positions to `bp`.

    """
    if not alphabet:
        if all(65 <= c <= 90 for c in bp):
            alphabet = string.ascii_uppercase
        elif all(97 <= c <= 122 for c in bp):
            alphabet = string.ascii_lowercase
        elif all(65 <= c <= 90 or 97 <= c <= 122 for c in bp):
            alphabet = string.ascii_letters
        elif all(0 <= c <= 127 for c in bp):
            alphabet = bytes(range(128))
        else:
            alphabet = bytes(range(256))

    if isinstance(alphabet, str):
        alphabet = alphabet.encode()

    return bytes(alphabet[(alphabet.index(c) + shift) % len(alphabet)] if c in alphabet else c for c in bp)


@binapy_decoder("caesar")
def decode_caesar(
    bp: bytes,
    shift: int,
    alphabet: None | str | bytes = None,
) -> bytes:
    """Decode data with Caesar cipher.

    Since encoding and decoding are symmetric, this is just an alias to `encode_caesar()` with an
    opposite shift.

    """
    return encode_caesar(bp, -shift, alphabet)
