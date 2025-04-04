"""This module implements JWK representing Elliptic Curve keys."""

from __future__ import annotations

import warnings
from functools import cached_property
from typing import TYPE_CHECKING, Any, override

from binapy import BinaPy
from cryptography.hazmat.primitives.asymmetric import ec

from jwskate import KeyTypes
from jwskate.jwa import (
    ES256,
    ES256K,
    ES384,
    ES512,
    P_256,
    P_384,
    P_521,
    BaseECSignatureAlg,
    EcdhEs,
    EcdhEs_A128KW,
    EcdhEs_A192KW,
    EcdhEs_A256KW,
    EllipticCurve,
    secp256k1,
)

from .alg import UnsupportedAlg
from .base import Jwk, JwkParameter

if TYPE_CHECKING:
    from collections.abc import Mapping


class UnsupportedEllipticCurve(KeyError):
    """Raised when an unsupported Elliptic Curve is requested."""


class ECJwk(Jwk):
    """Represent an Elliptic Curve key in JWK format.

    Elliptic Curve keys have Key Type `"EC"`.

    """

    KEY_TYPE = KeyTypes.EC

    CRYPTOGRAPHY_PRIVATE_KEY_CLASSES = (ec.EllipticCurvePrivateKey,)

    CRYPTOGRAPHY_PUBLIC_KEY_CLASSES = (ec.EllipticCurvePublicKey,)

    PARAMS: Mapping[str, JwkParameter] = {
        "crv": JwkParameter(description="Curve", is_private=False, is_required=True, kind="name"),
        "x": JwkParameter(description="X Coordinate", is_private=False, is_required=True, kind="b64u"),
        "y": JwkParameter(description="Y Coordinate", is_private=False, is_required=True, kind="b64u"),
        "d": JwkParameter(description="ECC Private Key", is_private=True, is_required=True, kind="b64u"),
    }

    CURVES: Mapping[str, EllipticCurve] = {curve.name: curve for curve in [P_256, P_384, P_521, secp256k1]}

    SIGNATURE_ALGORITHMS: Mapping[str, type[BaseECSignatureAlg]] = {
        sigalg.name: sigalg for sigalg in [ES256, ES384, ES512, ES256K]
    }

    KEY_MANAGEMENT_ALGORITHMS: Mapping[str, type[EcdhEs]] = {
        keyalg.name: keyalg for keyalg in [EcdhEs, EcdhEs_A128KW, EcdhEs_A192KW, EcdhEs_A256KW]
    }

    @property
    @override
    def is_private(self) -> bool:
        return "d" in self

    @override
    def _validate(self) -> None:
        self.get_curve(self.crv)
        super()._validate()

    @classmethod
    def get_curve(cls, crv: str) -> EllipticCurve:
        """Get the EllipticCurve instance for a given curve identifier.

        Args:
          crv: the curve identifier

        Returns:
            the matching `EllipticCurve` instance

        Raises:
            UnsupportedEllipticCurve: if the curve identifier is not supported

        """
        curve = cls.CURVES.get(crv)
        if curve is None:
            raise UnsupportedEllipticCurve(crv)
        return curve

    @property
    def curve(self) -> EllipticCurve:
        """Get the `EllipticCurve` instance for this key.

        Returns:
            the `EllipticCurve` instance

        """
        return self.get_curve(self.crv)

    @classmethod
    def public(cls, *, crv: str, x: int, y: int, **params: str) -> ECJwk:
        """Initialize a public `ECJwk` from its public parameters.

        Args:
          crv: the curve to use
          x: the x coordinate
          y: the y coordinate
          **params: additional member to include in the Jwk

        Returns:
          an ECJwk initialized with the supplied parameters

        """
        coord_size = cls.get_curve(crv).coordinate_size
        return cls(
            dict(
                kty=cls.KEY_TYPE,
                crv=crv,
                x=BinaPy.from_int(x, length=coord_size).to("b64u").ascii(),
                y=BinaPy.from_int(y, length=coord_size).to("b64u").ascii(),
                **params,
            ),
        )

    @classmethod
    def private(cls, *, crv: str, x: int, y: int, d: int, **params: Any) -> ECJwk:
        """Initialize a private ECJwk from its private parameters.

        Args:
          crv: the curve to use
          x: the x coordinate
          y: the y coordinate
          d: the elliptic curve private key
          **params: additional members to include in the JWK

        Returns:
          an ECJwk initialized with the supplied parameters

        """
        coord_size = cls.get_curve(crv).coordinate_size
        return cls(
            dict(
                kty=cls.KEY_TYPE,
                crv=crv,
                x=BinaPy.from_int(x, length=coord_size).to("b64u").ascii(),
                y=BinaPy.from_int(y, length=coord_size).to("b64u").ascii(),
                d=BinaPy.from_int(d, length=coord_size).to("b64u").ascii(),
                **params,
            ),
        )

    @classmethod
    @override
    def generate(cls, *, crv: str | None = None, alg: str | None = None, **kwargs: Any) -> ECJwk:
        curve: EllipticCurve = P_256

        if crv is None and alg is None:
            msg = (
                "No Curve identifier (crv) or Algorithm identifier (alg) have been provided "
                "when generating an Elliptic Curve JWK. So there is no hint to determine which curve to use. "
                "You must explicitly pass an 'alg' or 'crv' parameter to select the appropriate Curve."
            )
            raise ValueError(msg)
        if crv:
            curve = cls.get_curve(crv)
        elif alg:
            if alg in cls.SIGNATURE_ALGORITHMS:
                curve = cls.SIGNATURE_ALGORITHMS[alg].curve
            elif alg in cls.KEY_MANAGEMENT_ALGORITHMS:
                warnings.warn(
                    "No Curve identifier (crv) specified when generating an Elliptic Curve Jwk for Key Management. "
                    "Curve 'P-256' is used by default. You should explicitly pass a 'crv' parameter "
                    "to select the appropriate Curve and avoid this warning.",
                    stacklevel=2,
                )
            else:
                raise UnsupportedAlg(alg)

        key = ec.generate_private_key(curve.cryptography_curve)
        pn = key.private_numbers()  # type: ignore[attr-defined]
        x = pn.public_numbers.x
        y = pn.public_numbers.y
        d = pn.private_value

        return cls.private(
            crv=curve.name,
            alg=alg,
            x=x,
            y=y,
            d=d,
            **kwargs,
        )

    @classmethod
    @override
    def from_cryptography_key(cls, cryptography_key: Any, **kwargs: Any) -> ECJwk:
        public_numbers: ec.EllipticCurvePublicNumbers
        if isinstance(cryptography_key, ec.EllipticCurvePrivateKey):
            public_numbers = cryptography_key.public_key().public_numbers()
        elif isinstance(cryptography_key, ec.EllipticCurvePublicKey):
            public_numbers = cryptography_key.public_numbers()
        else:
            msg = "A EllipticCurvePrivateKey or a EllipticCurvePublicKey is required."
            raise TypeError(msg)

        for crv in EllipticCurve.instances.values():
            if crv.cryptography_curve.name == cryptography_key.curve.name:
                break
        else:
            msg = f"Unsupported Curve {cryptography_key.curve.name}"
            raise NotImplementedError(msg)

        x = BinaPy.from_int(public_numbers.x, length=crv.coordinate_size).to("b64u").ascii()
        y = BinaPy.from_int(public_numbers.y, length=crv.coordinate_size).to("b64u").ascii()
        parameters = {"kty": KeyTypes.EC, "crv": crv.name, "x": x, "y": y, **kwargs}
        if isinstance(cryptography_key, ec.EllipticCurvePrivateKey):
            pn = cryptography_key.private_numbers()  # type: ignore[attr-defined]
            d = BinaPy.from_int(pn.private_value, length=crv.coordinate_size).to("b64u").ascii()
            parameters["d"] = d

        return cls(parameters)

    @override
    def _to_cryptography_key(
        self,
    ) -> ec.EllipticCurvePrivateKey | ec.EllipticCurvePublicKey:
        if self.is_private:
            return ec.EllipticCurvePrivateNumbers(
                private_value=self.ecc_private_key,
                public_numbers=ec.EllipticCurvePublicNumbers(
                    x=self.x_coordinate,
                    y=self.y_coordinate,
                    curve=self.curve.cryptography_curve,
                ),
            ).private_key()
        return ec.EllipticCurvePublicNumbers(
            x=self.x_coordinate,
            y=self.y_coordinate,
            curve=self.curve.cryptography_curve,
        ).public_key()

    @property
    def coordinate_size(self) -> int:
        """The coordinate size to use with the key curve.

        This is 32, 48, or 66 bits.

        """
        return self.curve.coordinate_size

    @cached_property
    def x_coordinate(self) -> int:
        """Return the *x coordinate*, parameter `x` from this `ECJwk`."""
        return BinaPy(self.x).decode_from("b64u").to_int()

    @cached_property
    def y_coordinate(self) -> int:
        """Return the *y coordinate*, parameter `y` from this `ECJwk`."""
        return BinaPy(self.y).decode_from("b64u").to_int()

    @cached_property
    def ecc_private_key(self) -> int:
        """Return the *ECC private key*, parameter `d` from this `ECJwk`."""
        return BinaPy(self.d).decode_from("b64u").to_int()

    @override
    def supported_signing_algorithms(self) -> list[str]:
        return [name for name, alg in self.SIGNATURE_ALGORITHMS.items() if alg.curve == self.curve]

    @override
    def supported_key_management_algorithms(self) -> list[str]:
        return list(self.KEY_MANAGEMENT_ALGORITHMS)

    @override
    def supported_encryption_algorithms(self) -> list[str]:
        return list(self.ENCRYPTION_ALGORITHMS)
