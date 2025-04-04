"""This module contains helpers for compressing/decompressing data using `zlib`."""

import zlib

from binapy import binapy_decoder, binapy_encoder


@binapy_encoder("zlib")
def compress_zlib(bp: bytes, level: int = 6) -> bytes:
    """Compress some data using `zlib`.

    Args:
        bp: the data to compress
        level: the compression level to use

    Returns:
        the compressed data

    """
    return zlib.compress(bp, level)


@binapy_decoder("zlib")
def decompress_zlib(bp: bytes) -> bytes:
    """Decompress some data using zlib.

    Args:
        bp: the data to decompress

    Returns:
        the decompressed data

    """
    return zlib.decompress(bp)


@binapy_encoder("deflate")
def compress_deflate(bp: bytes, level: int = -1) -> bytes:
    """Compress data using DEFLATE.

    Notably, this is the algorithm used to compress `SAMLRequest` when using the Redirect Binding.

    Args:
        bp: the data to compress
        level: the compression level

    Returns:
        the compressed data.

    """
    return zlib.compress(bp, level=level)[2:-4]  # removes the 2 bytes zlib header and the final 4 bytes Adler checksum


@binapy_decoder("deflate")
def decompress_deflate(bp: bytes, bufsize: int = zlib.DEF_BUF_SIZE) -> bytes:
    """Decompress some data using DEFLATE.

    This is the algorithm used to compress `SAMLRequest` when using the Redirect Binding.

    Args:
        bp: the date to decompress
        bufsize: the buffer size to use

    Returns:
        the decompressed data

    """
    return zlib.decompress(bp, wbits=-15, bufsize=bufsize)
