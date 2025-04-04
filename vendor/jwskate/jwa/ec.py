"""This module contains classes that describe Elliptic Curves as described in RFC7518."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from cryptography.hazmat.primitives.asymmetric import ec


@dataclass
class EllipticCurve:
    """A descriptive class for Elliptic Curves.

    Elliptic Curves have a name, a `cryptography.ec.EllipticCurve`, and a coordinate size.

    """

    name: str
    """Curve name as defined in [IANA JOSE](https://www.iana.org/assignments/jose/jose.xhtml#web-
    key-elliptic-curve).

    This name will appear in `alg` or `enc` fields in JOSE headers.
    """

    cryptography_curve: ec.EllipticCurve
    """`cryptography` curve instance."""

    coordinate_size: int
    """Coordinate size, in bytes."""

    instances: ClassVar[dict[str, EllipticCurve]] = {}
    """Registry of subclasses, in a {name: instance} mapping."""

    def __post_init__(self) -> None:
        """Automatically register subclasses in the instance registry."""
        self.instances[self.name] = self


P_256: EllipticCurve = EllipticCurve(
    name="P-256",
    cryptography_curve=ec.SECP256R1(),
    coordinate_size=32,
)
"""P-256 curve."""

P_384: EllipticCurve = EllipticCurve(
    name="P-384",
    cryptography_curve=ec.SECP384R1(),
    coordinate_size=48,
)
"""P-384 curve."""

P_521: EllipticCurve = EllipticCurve(
    name="P-521",
    cryptography_curve=ec.SECP521R1(),
    coordinate_size=66,
)
"""P-521 curve."""

secp256k1: EllipticCurve = EllipticCurve(
    name="secp256k1",
    cryptography_curve=ec.SECP256K1(),
    coordinate_size=32,
)
"""[secp256k1 curve](https://www.rfc-editor.org/rfc/rfc8812.html)"""
