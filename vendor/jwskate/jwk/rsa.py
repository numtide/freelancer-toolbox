"""This module implements JWK representing RSA keys."""

from __future__ import annotations

from functools import cached_property
from typing import Any, override

from binapy import BinaPy
from cryptography.hazmat.primitives.asymmetric import rsa

from jwskate import KeyTypes
from jwskate.jwa import (
    PS256,
    PS384,
    PS512,
    RS256,
    RS384,
    RS512,
    RsaEsOaep,
    RsaEsOaepSha256,
    RsaEsOaepSha384,
    RsaEsOaepSha512,
    RsaEsPcks1v1_5,
)

from .base import Jwk, JwkParameter


class RSAJwk(Jwk):
    """Represent an RSA key in JWK format.

    RSA (Rivest-Shamir-Adleman) keys have Key Type `"RSA"`.

    """

    KEY_TYPE = KeyTypes.RSA
    CRYPTOGRAPHY_PRIVATE_KEY_CLASSES = (rsa.RSAPrivateKey,)
    CRYPTOGRAPHY_PUBLIC_KEY_CLASSES = (rsa.RSAPublicKey,)

    PARAMS = {
        "n": JwkParameter(description="Modulus", is_private=False, is_required=True, kind="b64u"),
        "e": JwkParameter(description="Exponent", is_private=False, is_required=True, kind="b64u"),
        "d": JwkParameter(description="Private Exponent", is_private=True, is_required=True, kind="b64u"),
        "p": JwkParameter(description="First Prime Factor", is_private=True, is_required=False, kind="b64u"),
        "q": JwkParameter(description="Second Prime Factor", is_private=True, is_required=False, kind="b64u"),
        "dp": JwkParameter(description="First Factor CRT Exponent", is_private=True, is_required=False, kind="b64u"),
        "dq": JwkParameter(
            description="Second Factor CRT Exponent",
            is_private=True,
            is_required=False,
            kind="b64u",
        ),
        "qi": JwkParameter(description="First CRT Coefficient", is_private=True, is_required=False, kind="b64u"),
        "oth": JwkParameter(description="Other Primes Info", is_private=True, is_required=False, kind="unsupported"),
    }

    SIGNATURE_ALGORITHMS = {sigalg.name: sigalg for sigalg in [RS256, RS384, RS512, PS256, PS384, PS512]}

    KEY_MANAGEMENT_ALGORITHMS = {
        keyalg.name: keyalg
        for keyalg in [
            RsaEsPcks1v1_5,
            RsaEsOaep,
            RsaEsOaepSha256,
            RsaEsOaepSha384,
            RsaEsOaepSha512,
        ]
    }

    @property
    @override
    def is_private(self) -> bool:
        return "d" in self

    @classmethod
    @override
    def from_cryptography_key(cls, cryptography_key: Any, **kwargs: Any) -> RSAJwk:
        if isinstance(cryptography_key, rsa.RSAPrivateKey):
            priv = cryptography_key.private_numbers()  # type: ignore[attr-defined]
            pub = cryptography_key.public_key().public_numbers()
            return cls.private(
                n=pub.n,
                e=pub.e,
                d=priv.d,
                p=priv.p,
                q=priv.q,
                dp=priv.dmp1,
                dq=priv.dmq1,
                qi=priv.iqmp,
                **kwargs,
            )
        if isinstance(cryptography_key, rsa.RSAPublicKey):
            pub = cryptography_key.public_numbers()
            return cls.public(n=pub.n, e=pub.e, **kwargs)
        msg = "A RSAPrivateKey or a RSAPublicKey is required."
        raise TypeError(msg)

    @override
    def _to_cryptography_key(self) -> rsa.RSAPrivateKey | rsa.RSAPublicKey:
        if self.is_private:
            return rsa.RSAPrivateNumbers(
                self.first_prime_factor,
                self.second_prime_factor,
                self.private_exponent,
                self.first_factor_crt_exponent,
                self.second_factor_crt_exponent,
                self.first_crt_coefficient,
                rsa.RSAPublicNumbers(self.exponent, self.modulus),
            ).private_key()
        return rsa.RSAPublicNumbers(e=self.exponent, n=self.modulus).public_key()

    @classmethod
    def public(cls, *, n: int, e: int = 65537, **params: Any) -> RSAJwk:
        """Initialize a public `RsaJwk` from a modulus and an exponent.

        Args:
          n: the modulus
          e: the exponent
          **params: additional parameters to include in the `Jwk`

        Returns:
          a `RSAJwk` initialized from the provided parameters

        """
        return cls(
            dict(
                kty=cls.KEY_TYPE,
                n=BinaPy.from_int(n).to("b64u").ascii(),
                e=BinaPy.from_int(e).to("b64u").ascii(),
                **params,
            ),
        )

    @classmethod
    def private(
        cls,
        *,
        n: int,
        e: int = 65537,
        d: int,
        p: int | None = None,
        q: int | None = None,
        dp: int | None = None,
        dq: int | None = None,
        qi: int | None = None,
        **params: Any,
    ) -> RSAJwk:
        """Initialize a private `RSAJwk` from its required parameters.

        Args:
          n: the modulus
          e: the exponent
          d: the private exponent
          p: the first prime factor
          q: the second prime factor
          dp: the first factor CRT exponent
          dq: the second factor CRT exponent
          qi: the first CRT coefficient
          **params: additional parameters to include in the `Jwk`

        Returns:
            a `RSAJwk` initialized from the given parameters

        """
        return cls(
            dict(
                kty=cls.KEY_TYPE,
                n=BinaPy.from_int(n).to("b64u").ascii(),
                e=BinaPy.from_int(e).to("b64u").ascii(),
                d=BinaPy.from_int(d).to("b64u").ascii(),
                p=BinaPy.from_int(p).to("b64u").ascii() if p is not None else None,
                q=BinaPy.from_int(q).to("b64u").ascii() if q is not None else None,
                dp=BinaPy.from_int(dp).to("b64u").ascii() if dp is not None else None,
                dq=BinaPy.from_int(dq).to("b64u").ascii() if dq is not None else None,
                qi=BinaPy.from_int(qi).to("b64u").ascii() if qi is not None else None,
                **params,
            ),
        )

    @classmethod
    def from_prime_factors(cls, p: int, q: int, e: int = 65537) -> RSAJwk:
        """Initialise a `RSAJwk` from its prime factors and exponent.

        Modulus and Private Exponent are mathematically calculated based on those factors.

        Exponent is usually 65537 (default).

        Args:
            p: first prime factor
            q: second prime factor
            e: exponent

        Returns:
            a `RSAJwk`

        """
        n = p * q
        phi = (p - 1) * (q - 1)
        d = pow(e, -1, phi)
        return cls.private(n=n, e=e, d=d)

    @cached_property
    def key_size(self) -> int:
        """Key size, in bits."""
        return len(BinaPy(self.n).decode_from("b64u")) * 8

    @classmethod
    def generate(cls, key_size: int = 4096, **params: Any) -> RSAJwk:
        """Generate a new random private `RSAJwk`.

        Args:
          key_size: the key size to use for the generated key, in bits
          **params: additional parameters to include in the `Jwk`

        Returns:
          a generated `RSAJwk`

        """
        private_key = rsa.generate_private_key(65537, key_size=key_size)
        pn = private_key.private_numbers()
        return cls.private(
            n=pn.public_numbers.n,
            e=pn.public_numbers.e,
            d=pn.d,
            p=pn.p,
            q=pn.q,
            dp=pn.dmp1,
            dq=pn.dmq1,
            qi=pn.iqmp,
            **params,
        )

    @cached_property
    def modulus(self) -> int:
        """Return the modulus `n` from this `Jwk`."""
        return BinaPy(self.n).decode_from("b64u").to_int()

    @cached_property
    def exponent(self) -> int:
        """Return the public exponent `e` from this `Jwk`."""
        return BinaPy(self.e).decode_from("b64u").to_int()

    @cached_property
    def private_exponent(self) -> int:
        """Return the private exponent `d` from this `Jwk`."""
        return BinaPy(self.d).decode_from("b64u").to_int()

    @cached_property
    def prime_factors(self) -> tuple[int, int]:
        """Return the 2 prime factors `p` and `q` from this `Jwk`."""
        if "p" not in self or "q" not in self:
            p, q = rsa.rsa_recover_prime_factors(self.modulus, self.exponent, self.private_exponent)
            return (p, q) if p < q else (q, p)
        return (
            BinaPy(self.p).decode_from("b64u").to_int(),
            BinaPy(self.q).decode_from("b64u").to_int(),
        )

    @cached_property
    def first_prime_factor(self) -> int:
        """Return the first prime factor `p` from this `Jwk`."""
        return self.prime_factors[0]

    @cached_property
    def second_prime_factor(self) -> int:
        """Return the second prime factor `q` from this `Jwk`."""
        return self.prime_factors[1]

    @cached_property
    def first_factor_crt_exponent(self) -> int:
        """Return the first factor CRT exponent `dp` from this `Jwk`."""
        if "dp" in self:
            return BinaPy(self.dp).decode_from("b64u").to_int()
        return rsa.rsa_crt_dmp1(self.private_exponent, self.first_prime_factor)

    @cached_property
    def second_factor_crt_exponent(self) -> int:
        """Return the second factor CRT exponent `dq` from this `Jwk`."""
        if "dq" in self:
            return BinaPy(self.dq).decode_from("b64u").to_int()
        return rsa.rsa_crt_dmq1(self.private_exponent, self.second_prime_factor)

    @cached_property
    def first_crt_coefficient(self) -> int:
        """Return the first CRT coefficient `qi` from this `Jwk`."""
        if "qi" in self:
            return BinaPy(self.qi).decode_from("b64u").to_int()
        return rsa.rsa_crt_iqmp(self.first_prime_factor, self.second_prime_factor)

    def with_optional_private_parameters(self) -> RSAJwk:
        """Compute the optional RSA private parameters.

        This returns a new `Jwk` with those additional params included.

        The optional parameters are:

        - p: first prime factor
        - q: second prime factor
        - dp: first factor Chinese Remainder Theorem exponent
        - dq: second factor Chinese Remainder Theorem exponent
        - qi: first Chinese Remainder Theorem coefficient

        """
        if not self.is_private:
            msg = "Optional private parameters can only be computed for private RSA keys."
            raise ValueError(msg)

        jwk = dict(self)

        jwk.update(
            {
                "p": BinaPy.from_int(self.first_prime_factor).to("b64u").ascii(),
                "q": BinaPy.from_int(self.second_prime_factor).to("b64u").ascii(),
                "dp": BinaPy.from_int(self.first_factor_crt_exponent).to("b64u").ascii(),
                "dq": BinaPy.from_int(self.second_factor_crt_exponent).to("b64u").ascii(),
                "qi": BinaPy.from_int(self.first_crt_coefficient).to("b64u").ascii(),
            },
        )

        return RSAJwk(jwk)

    def without_optional_private_parameters(self) -> RSAJwk:
        """Remove the optional private parameters and return another `Jwk` instance without them."""
        jwk = dict(self)
        for param in "p", "q", "dp", "dq", "qi":
            jwk.pop(param, None)

        return RSAJwk(jwk)
