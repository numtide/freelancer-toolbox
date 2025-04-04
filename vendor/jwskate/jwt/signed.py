"""This module contains classes and utilities to generate and validate signed JWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import cached_property
from typing import TYPE_CHECKING, Any, Self

from binapy import BinaPy

from jwskate import JwkSet
from jwskate.jwe import JweCompact
from jwskate.jwk import Jwk, to_jwk
from jwskate.jws import InvalidSignature

from .base import InvalidJwt, Jwt

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from types import EllipsisType


class ExpiredJwt(ValueError):
    """Raised when trying to validate an expired JWT token."""


class InvalidClaim(ValueError):
    """Raised when trying to validate a JWT with unexpected claims."""


class SignedJwt(Jwt):
    """Represent a Signed Json Web Token (JWT), as defined in RFC7519.

    A signed JWT contains a JSON object as payload, which represents claims.

    To sign a JWT, use [Jwt.sign][jwskate.jwt.Jwt.sign].

    Args:
        value: the token value.
        max_size: maximum allowed size for the JWE token, in bytes.
            Pass a negative or 0 value to disable this check.

    """

    def __init__(self, value: bytes | str, *, max_size: int = 16 * 1024) -> None:
        super().__init__(value, max_size=max_size)

        parts = BinaPy(self.value).split(b".")
        if len(parts) != 3:
            msg = "A JWT must contain a header, a payload and a signature, separated by dots"
            raise InvalidJwt(
                msg,
                value,
            )

        header, payload, signature = parts
        try:
            self.headers = header.decode_from("b64u").parse_from("json")
        except ValueError as exc:
            msg = "Invalid JWT header: it must be a Base64URL-encoded JSON object"
            raise InvalidJwt(msg) from exc

        try:
            self.claims = payload.decode_from("b64u").parse_from("json")
        except ValueError as exc:
            msg = "Invalid JWT payload: it must be a Base64URL-encoded JSON object"
            raise InvalidJwt(msg) from exc

        try:
            self.signature = signature.decode_from("b64u")
        except ValueError as exc:
            msg = "Invalid JWT signature: it must be a Base64URL-encoded binary data (bytes)"
            raise InvalidJwt(msg) from exc

    @cached_property
    def signed_part(self) -> bytes:
        """Return the actual signed data from this token.

        The signed part is composed of the header and payload, encoded in Base64-Url, joined by a dot.

        Returns:
          the signed part as bytes

        """
        return b".".join(self.value.split(b".", 2)[:2])

    def verify_signature(
        self,
        key: Jwk | JwkSet | Mapping[str, Any] | Any,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> bool:
        """Verify this JWT signature using a given key and algorithm(s).

        Args:
          key: the private Jwk to use to verify the signature
          alg: the alg to use to verify the signature, if only 1 is allowed
          algs: the allowed signature algs, if there are several

        Returns:
            `True` if the token signature is verified, `False` otherwise

        """
        key = key.get_jwk_by_kid(self.kid) if isinstance(key, JwkSet) else to_jwk(key)

        return key.verify(data=self.signed_part, signature=self.signature, alg=alg, algs=algs)

    def verify(self, key: Jwk | Any, *, alg: str | None = None, algs: Iterable[str] | None = None) -> Self:
        """Convenience method to verify the signature inline.

        Returns `self` on success, raises an exception on failure.

        Raises:
            InvalidSignature: if the signature does not verify.

        Return:
            the same `SignedJwt`, if the signature is verified.

        Usage:
            ```python
            jwt = SignedJwt(
                "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJURVNUIn0.tIUFZqEZD12odEyBWscuxc4USspdYfJKhxPN0JXVMK97SUM69HrU5MGgocyyBbx1x9yIAkV7rNjcviqwGoVvsQ"
            ).verify(
                {
                    "kty": "EC",
                    "alg": "ES256",
                    "crv": "P-256",
                    "x": "T_RLrReYRPIknDpIEjLUoy7ibAbqJDfHe03mkEjI_oU",
                    "y": "8MM4v58j8IHag6uibgC0Qn275bl9c9JR0UD0TwFgMPM",
                }
            )

            # you can now do your business with this verified JWT:
            assert jwt.claims == {"sub": "TEST"}
            ```

        """
        if self.verify_signature(key, alg=alg, algs=algs):
            return self
        raise InvalidSignature(data=self, key=key, alg=alg, algs=algs)

    def is_expired(self, leeway: int = 0) -> bool | None:
        """Check if this token is expired, based on its `exp` claim.

        Args:
            leeway: additional number of seconds for leeway.

        Returns:
            `True` if the token is expired, `False` if it's not, `None` if there is no `exp` claim.

        """
        exp = self.expires_at
        if exp is None:
            return None
        return exp < (datetime.now(UTC) + timedelta(seconds=leeway))

    @cached_property
    def expires_at(self) -> datetime | None:
        """Get the *Expires At* (`exp`) date from this token.

        Returns:
          a `datetime` initialized from the `exp` claim, or `None` if there is no `exp` claim

        Raises:
            AttributeError: if the `exp` claim cannot be parsed to a date

        """
        exp = self.get_claim("exp")
        if not exp:
            return None
        try:
            exp_dt = Jwt.timestamp_to_datetime(exp)
        except (TypeError, OSError):
            msg = "invalid `exp `claim"
            raise AttributeError(msg, exp) from None
        else:
            return exp_dt

    @cached_property
    def issued_at(self) -> datetime | None:
        """Get the *Issued At* (`iat`) date from this token.

        Returns:
          a `datetime` initialized from the `iat` claim, or `None` if there is no `iat` claim

        Raises:
            AttributeError: if the `iss` claim cannot be parsed to a date

        """
        iat = self.get_claim("iat")
        if not iat:
            return None
        try:
            iat_dt = Jwt.timestamp_to_datetime(iat)
        except (TypeError, OSError):
            msg = "invalid `iat `claim"
            raise AttributeError(msg, iat) from None
        else:
            return iat_dt

    @cached_property
    def not_before(self) -> datetime | None:
        """Get the *Not Before* (nbf) date from this token.

        Returns:
          a `datetime` initialized from the `nbf` claim, or `None` if there is no `nbf` claim

        Raises:
            AttributeError: if the `nbf` claim cannot be parsed to a date

        """
        nbf = self.get_claim("nbf")
        if not nbf:
            return None
        try:
            nbf_dt = Jwt.timestamp_to_datetime(nbf)
        except (TypeError, OSError):
            msg = "invalid `nbf `claim"
            raise AttributeError(msg, nbf) from None
        else:
            return nbf_dt

    @cached_property
    def issuer(self) -> str | None:
        """Get the *Issuer* (`iss`) claim from this token.

        Returns:
          the issuer, as `str`, or `None` if there is no `ìss` claim

        Raises:
            AttributeError: if the `ìss` claim value is not a string

        """
        iss = self.get_claim("iss")
        if iss is None or isinstance(iss, str):
            return iss
        msg = "iss has an unexpected type"
        raise AttributeError(msg, type(iss))

    @cached_property
    def audiences(self) -> list[str]:
        """Get the *Audience(s)* (`aud`) claim from this token.

        If this token has a single audience, this will return a `list` anyway.

        Returns:
            the list of audiences from this token, from the `aud` claim.

        Raises:
            AttributeError: if the audience is an unexpected type

        """
        aud = self.get_claim("aud")
        if aud is None:
            return []
        if isinstance(aud, str):
            return [aud]
        if isinstance(aud, list):
            return aud
        msg = "aud has an unexpected type"
        raise AttributeError(msg, type(aud))

    @cached_property
    def subject(self) -> str | None:
        """Get the *Subject* (`sub`) from this token.

        Returns:
          the subject, as `str`, or `None` if there is no `sub` claim

        Raises:
            AttributeError: if the `sub` value is not a string

        """
        sub = self.get_claim("sub")
        if sub is None or isinstance(sub, str):
            return sub
        msg = "sub has an unexpected type"
        raise AttributeError(msg, type(sub))

    @cached_property
    def jwt_token_id(self) -> str | None:
        """Get the *JWT Token ID* (`jti`) from this token.

        Returns:
          the token identifier, as `str`, or `None` if there is no `jti` claim

        Raises:
          AttributeError: if the `jti` value is not a string

        """
        jti = self.get_claim("jti")
        if jti is None or isinstance(jti, str):
            return jti
        msg = "jti has an unexpected type"
        raise AttributeError(msg, type(jti))

    def get_claim(self, key: str, default: Any = None) -> Any:
        """Get a claim by name from this Jwt.

        Args:
          key: the claim name.
          default: a default value if the claim is not found

        Returns:
          the claim value if found, or `default` if not found

        """
        return self.claims.get(key, default)

    def __getitem__(self, item: str) -> Any:
        """Allow access to claim by name with subscription.

        Args:
          item: the claim name

        Returns:
         the claim value

        """
        value = self.get_claim(item)
        if value is None:
            raise KeyError(item)
        return value

    def __getattr__(self, item: str) -> Any:
        """Allow claim access as attributes.

        Args:
            item: the claim name

        Returns:
            the claim value

        """
        value = self.get_claim(item)
        if value is None:
            raise AttributeError(item)
        return value

    def __str__(self) -> str:
        """Return the Jwt serialized value, as `str`.

        Returns:
            the serialized token value.

        """
        return self.value.decode()

    def __bytes__(self) -> bytes:
        """Return the Jwt serialized value, as `bytes`.

        Returns:
            the serialized token value.

        """
        return self.value

    def validate(
        self,
        key: Jwk | Mapping[str, Any] | Any,
        *,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
        issuer: str | None = None,
        audience: None | str = None,
        check_exp: bool = True,
        **kwargs: Any,
    ) -> None:
        """Validate a `SignedJwt` signature and expected claims.

        This verifies the signature using the provided `jwk` and `alg`, then checks the token issuer, audience and
        expiration date.
        This can also check custom claims using extra `kwargs`, whose values can be:

        - a static value (`str`, `int`, etc.): the value from the token will be compared "as-is".
        - a callable, taking the claim value as parameter: if that callable returns `True`, the claim is considered
        as valid.

        Args:
          key: the signing key to use to verify the signature.
          alg: the signature alg to use to verify the signature.
          algs: allowed signature algs, if several
          issuer: the expected issuer for this token.
          audience: the expected audience for this token.
          check_exp: ìf `True` (default), check that the token is not expired.
          **kwargs: additional claims to check

        Returns:
          Raises exceptions if any validation check fails.

        Raises:
          InvalidSignature: if the signature is not valid
          InvalidClaim: if a claim doesn't validate
          ExpiredJwt: if the expiration date is passed

        """
        self.verify(key, alg=alg, algs=algs)

        if issuer is not None and self.issuer != issuer:
            msg = "Unexpected issuer"
            raise InvalidClaim(msg, "iss", self.issuer)

        if audience is not None and (self.audiences is None or audience not in self.audiences):
            msg = "Unexpected audience"
            raise InvalidClaim(msg, "aud", self.audiences)

        if check_exp:
            expired = self.is_expired()
            if expired is True:
                msg = f"This token expired at {self.expires_at}"
                raise ExpiredJwt(msg)
            if expired is None:
                msg = "This token does not contain an 'exp' claim."
                raise InvalidClaim(msg, "exp")

        for claim_name, value in kwargs.items():
            claim = self.get_claim(claim_name)
            if callable(value):
                if not value(claim):
                    raise InvalidClaim(
                        claim_name,
                        f"value of claim '{claim_name}' doesn't validate with the provided validator",
                        claim,
                    )
            elif claim != value:
                raise InvalidClaim(claim_name, f"unexpected value for claim {key}", claim)

    def encrypt(
        self,
        key: Any,
        enc: str,
        alg: str | None = None,
        extra_headers: Mapping[str, Any] | None = None,
    ) -> JweCompact:
        """Encrypt this JWT into a JWE.

        The result is an encrypted (outer) JWT containing a signed (inner) JWT.

        Arguments:
            key: the encryption key to use
            enc: the encryption alg to use
            alg: the key management alg to use
            extra_headers: additional headers to include in the outer JWE.

        """
        extra_headers = dict(extra_headers) if extra_headers else {}
        extra_headers.setdefault("cty", "JWT")

        return JweCompact.encrypt(self, key, enc=enc, alg=alg, extra_headers=extra_headers)

    def unprotect(
        self,
        *,
        alg: str = "none",
        typ: str | None | EllipsisType = ...,
        extra_headers: Mapping[str, Any] | None = None,
    ) -> SignedJwt:
        """Return a new Jwt with the same payload but without signature.

        The JWT `alg` header will be set to `"none"` by default. You may change this by passing a `alg` parameter,
        which can be useful for security testing or Capture-the-Flag scenarios.

        Args:
            alg: the `alg` value to set as header
            typ: the `typ` value to set as header. Defaults to the same `typ` as in the original token.
            extra_headers: additional headers to include in the unprotected JWT.

        """
        if typ is ...:
            typ = self.typ
        return self.unprotected(self.claims, alg=alg, typ=typ, extra_headers=extra_headers)
