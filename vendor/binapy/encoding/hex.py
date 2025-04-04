"""Hexadecimal encoding and decoding methods."""

from binapy import binapy_checker, binapy_decoder, binapy_encoder


@binapy_decoder("hex")
def decode_hex(bp: bytes) -> bytes:
    """Decode a hexadecidemal bytes from `bp` to `bytes`.

    Args:
        bp: a hex string

    Returns:
        the hex-decoded bytes value

    """
    return bytes.fromhex(bp.decode())


@binapy_encoder("hex")
def encode_hex(bp: bytes) -> bytes:
    """Encode a `bytes` value to hexadecidemal.

    Args:
        bp: a raw bytes

    Returns:
        the hexadecimal encoded value

    """
    return bp.hex().encode()


@binapy_checker("hex")
def is_hex(bp: bytes) -> bool:
    """Check if a `bytes` value contains a valid hexadecimal string.

    Args:
        bp: a value

    Returns:
        `True` if `bp` is a valid hexadecimal string

    """
    return len(bp) % 2 == 0 and bp.isalnum() and set(bp.lower()).issubset(b"abcdef0123456789")
