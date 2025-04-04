"""This module implements the JWS Compact format."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, Self, SupportsBytes

from binapy import BinaPy

from jwskate import JwkSet
from jwskate.jwk.base import Jwk, to_jwk
from jwskate.token import BaseCompactToken

from .signature import InvalidSignature, JwsSignature

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .json import JwsJsonFlat, JwsJsonGeneral  # pragma: no cover


class InvalidJws(ValueError):
    """Raised when an invalid Jws is parsed."""


class JwsCompact(BaseCompactToken):
    """Represents a Json Web Signature (JWS), using compact serialization, as defined in RFC7515.

    Args:
        value: the JWS token value
        max_size: maximum allowed size for the JWE token, in bytes.
            Pass a negative or 0 value to disable this check.

    """

    def __init__(self, value: bytes | str, *, max_size: int = 16 * 1024) -> None:
        super().__init__(value, max_size=max_size)

        parts = BinaPy(self.value).split(b".")

        if len(parts) != 3:
            msg = "A JWS must contain a header, a payload and a signature, separated by dots"
            raise InvalidJws(msg)

        header, payload, signature = parts

        try:
            self.headers = header.decode_from("b64u").parse_from("json")
        except ValueError as exc:
            msg = "Invalid JWS header: it must be a Base64URL-encoded JSON object"
            raise InvalidJws(msg) from exc

        try:
            self.payload = payload.decode_from("b64u")
        except ValueError as exc:
            msg = "Invalid JWS payload: it must be a Base64URL-encoded binary data (bytes)"
            raise InvalidJws(msg) from exc

        try:
            self.signature = signature.decode_from("b64u")
        except ValueError as exc:
            msg = "Invalid JWS signature: it must be a Base64URL-encoded binary data (bytes)"
            raise InvalidJws(msg) from exc

    @classmethod
    def sign(
        cls,
        payload: bytes | SupportsBytes,
        key: Jwk | Mapping[str, Any] | Any,
        alg: str | None = None,
        extra_headers: Mapping[str, Any] | None = None,
    ) -> JwsCompact:
        """Sign a payload and returns the resulting JwsCompact.

        Args:
          payload: the payload to sign
          key: the jwk to use to sign this payload
          alg: the alg to use
          extra_headers: additional headers to add to the Jws Headers

        Returns:
          the resulting token

        """
        key = to_jwk(key)

        if not isinstance(payload, bytes):
            payload = bytes(payload)

        headers = dict(extra_headers or {}, alg=alg)
        kid = key.get("kid")
        if kid:
            headers["kid"] = kid

        signed_part = JwsSignature.assemble_signed_part(headers, payload)
        signature = key.sign(signed_part, alg=alg)
        return cls.from_parts(signed_part, signature)

    @classmethod
    def from_parts(
        cls,
        signed_part: bytes | SupportsBytes | str,
        signature: bytes | SupportsBytes,
    ) -> JwsCompact:
        """Construct a JWS token based on its signed part and signature values.

        Signed part is the concatenation of the header and payload, both encoded in Base64-Url, and joined by a dot.

        Args:
          signed_part: the signed part
          signature: the signature value

        Returns:
            the resulting token

        """
        if isinstance(signed_part, str):
            signed_part = signed_part.encode("ascii")
        if not isinstance(signed_part, bytes):
            signed_part = bytes(signed_part)

        if not isinstance(signature, bytes):
            signature = bytes(signature)

        return cls(b".".join((signed_part, BinaPy(signature).to("b64u"))))

    @cached_property
    def signed_part(self) -> bytes:
        """Returns the signed part (header + payload) from this JwsCompact.

        Returns:
            the signed part

        """
        return b".".join(self.value.split(b".", 2)[:2])

    def verify_signature(
        self,
        key: Jwk | JwkSet | Mapping[str, Any] | Any,
        *,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> bool:
        """Verify the signature from this JwsCompact using a key.

        Args:
          key: the Jwk to use to validate this signature
          alg: the alg to use, if there is only 1 allowed
          algs: the allowed algs, if here are several

        Returns:
         `True` if the signature matches, `False` otherwise

        """
        key = key.get_jwk_by_kid(self.kid) if isinstance(key, JwkSet) else to_jwk(key)

        return key.verify(self.signed_part, self.signature, alg=alg, algs=algs)

    def verify(
        self,
        key: Jwk | Mapping[str, Any] | Any,
        *,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> Self:
        """Verify this JWS signature.

        This is an alternative to `.verify_signature()` that raises an exception if the signature is not
        verified.

        Args:
          key: the Jwk to use to validate this signature
          alg: the alg to use, if there is only 1 allowed
          algs: the allowed algs, if here are several

        Raises:
            InvalidSignature: if the signature does not verify

        Returns:
          The same JwsCompact

        Usage:
            ```python
            jws = JwsCompact(
                "eyJhbGciOm51bGx9.SGVsbG8gV29ybGQh.rd61m4AQ6dOqexdZC9revgictOzRd7dmHiQ5UMa9g66BhAO8crw_E_5SkydE-PNNzRkdFdq4P2YzzM1HgfnWlw"
            ).verify(
                {
                    "kty": "EC",
                    "alg": "ES256",
                    "crv": "P-256",
                    "x": "T_RLrReYRPIknDpIEjLUoy7ibAbqJDfHe03mkEjI_oU",
                    "y": "8MM4v58j8IHag6uibgC0Qn275bl9c9JR0UD0TwFgMPM",
                }
            )

            assert jws.payload == b"Hello World!"
            ```

        """
        if self.verify_signature(key, alg=alg, algs=algs):
            return self
        raise InvalidSignature(data=self, key=key, alg=alg, algs=algs)

    def flat_json(self, unprotected_header: Any = None) -> JwsJsonFlat:
        """Create a JWS in JSON flat format based on this Compact JWS.

        Args:
          unprotected_header: optional unprotected header to include in the JWS JSON

        Returns:
            the resulting token

        """
        from .json import JwsJsonFlat

        protected, payload, signature = self.value.split(b".")

        content = {
            "payload": payload.decode(),
            "protected": protected.decode(),
            "signature": signature.decode(),
        }
        if unprotected_header is not None:
            content["header"] = unprotected_header
        return JwsJsonFlat(content)

    def general_json(self, unprotected_header: Any = None) -> JwsJsonGeneral:
        """Create a JWS in JSON General format based on this JWS Compact.

        The resulting token will have a single signature which is the one from this token.

        Args:
            unprotected_header: optional unprotected header to include in the JWS JSON

        Returns:
            the resulting token

        """
        jws = self.flat_json(unprotected_header)
        return jws.generalize()

    def jws_signature(self, unprotected_header: Any = None) -> JwsSignature:
        """Return a JwsSignature based on this JWS Compact token."""
        return JwsSignature.from_parts(protected=self.headers, signature=self.signature, header=unprotected_header)
