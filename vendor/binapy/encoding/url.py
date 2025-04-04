"""This module contains helpers for the URL-encoding and decoding of data."""

from urllib.parse import quote, quote_plus, unquote, unquote_plus

from binapy import binapy_decoder, binapy_encoder


@binapy_encoder("url")
def url_encode(bp: bytes, *, safe: str = "/", plus_spaces: bool = True) -> str:
    """URL-encode some data.

    Args:
    ----
        bp: the data to encode
        safe: the characters to consider as safe, which will not be url-encoded
        plus_spaces: if `True`, spaces will be encoded as `'+'`. If `False`, they will be encoded as `'%20'`.

    Returns:
    -------
        the url-encoded result

    """
    if plus_spaces:
        return quote_plus(bp, safe=safe)
    return quote(bp, safe=safe)


@binapy_decoder("url")
def url_decode(bp: bytes, *, plus_spaces: bool = True, errors: str = "replace") -> bytes:
    """Url-decode some data.

    Args:
    ----
        bp: the data to decode
        plus_spaces: if `True`, `'+'` will be encoded as space. If `False`, they will not be decoded.
        errors: what to do with invalid characters.

    Returns:
    -------
        the url-decoded data

    See Also:
    --------
        [urllib.parse.unquote][]
        [urllib.parse.unquote_plus][]

    """
    if plus_spaces:
        return unquote_plus(bp.decode(), errors=errors).encode()
    return unquote(bp.decode(), errors=errors).encode()
