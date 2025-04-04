"""This module implement JWS signatures."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any, Self, SupportsBytes

from binapy import BinaPy

from jwskate.jwk import Jwk, to_jwk
from jwskate.token import BaseJsonDict

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


class InvalidSignature(ValueError):
    """Raised when trying to validate a token with an invalid signature."""

    def __init__(self, data: SupportsBytes, key: Any, alg: str | None, algs: Iterable[str] | None) -> None:
        self.data = data
        self.key = key
        self.alg = alg
        self.algs = algs


class JwsSignature(BaseJsonDict):
    """Represent a JWS Signature.

    A JWS Signature has:

     - a protected header (as a JSON object)
     - a signature value (as raw data)
     - an unprotected header (as arbitrary JSON data)
     - optional extra JSON attributes

    """

    @classmethod
    def from_parts(
        cls,
        protected: Mapping[str, Any],
        signature: bytes,
        header: Any | None,
        **kwargs: Any,
    ) -> Self:
        """Initialize a JwsSignature based on the provided parts.

        Args:
          protected: the protected headers, as a key: value mapping
          signature: the raw signature value
          header: the unprotected header, if any
          **kwargs: extra attributes, if any

        Returns:
            A `JwsSignature` based on the provided parts.

        """
        content = dict(
            kwargs,
            protected=BinaPy.serialize_to("json", protected).to("b64u").ascii(),
            signature=BinaPy(signature).to("b64u").ascii(),
        )
        if header is not None:
            content["header"] = header
        return cls(content)

    @cached_property
    def protected(self) -> dict[str, Any]:
        """The protected header.

        Returns:
            the protected headers, as a `dict`.

        Raises:
            AttributeError: if this signature doesn't have protected headers.

        """
        protected = self.get("protected")
        if protected is None:
            msg = "This Jws JSON does not contain a 'protected' member"
            raise AttributeError(msg)
        return BinaPy(protected).decode_from("b64u").parse_from("json")  # type: ignore[no-any-return]

    @property
    def header(self) -> Any:
        """The unprotected header, unaltered.

        Returns:
            The unprotected header

        """
        return self.get("header")

    @cached_property
    def signature(self) -> bytes:
        """The raw signature.

        Returns:
            The raw signed data, unencoded

        Raises:
            AttributeError: if no 'signature' member is present

        """
        signature = self.get("signature")
        if signature is None:
            msg = "This Jws JSON does not contain a 'signature' member"
            raise AttributeError(msg)
        return BinaPy(signature).decode_from("b64u")

    @classmethod
    def sign(
        cls,
        payload: bytes,
        key: Jwk | Mapping[str, Any] | Any,
        alg: str | None = None,
        extra_protected_headers: Mapping[str, Any] | None = None,
        header: Any | None = None,
        **kwargs: Any,
    ) -> Self:
        """Sign a payload and return the generated JWS signature.

        Args:
          payload: the raw data to sign
          key: the signature key to use
          alg: the signature algorithm to use
          extra_protected_headers: additional protected headers to include, if any
          header: the unprotected header, if any.
          **kwargs: additional members to include in this signature

        Returns:
            The generated signature.

        """
        key = to_jwk(key)

        headers = dict(extra_protected_headers or {}, alg=alg)
        kid = key.get("kid")
        if kid:
            headers["kid"] = kid

        signed_part = JwsSignature.assemble_signed_part(headers, payload)
        signature = key.sign(signed_part, alg=alg)
        return cls.from_parts(protected=headers, signature=signature, header=header, **kwargs)

    @classmethod
    def assemble_signed_part(cls, headers: Mapping[str, Any], payload: bytes | str) -> bytes:
        """Assemble the protected header and payload to sign, as specified in.

        [RFC7515
        $5.1](https://datatracker.ietf.org/doc/html/rfc7515#section-5.1).

        Args:
          headers: the protected headers
          payload: the raw payload to sign

        Returns:
            the raw data to sign

        """
        return b".".join(
            (
                BinaPy.serialize_to("json", headers).to("b64u"),
                BinaPy(payload).to("b64u"),
            ),
        )

    def verify(
        self,
        payload: bytes,
        key: Jwk | Mapping[str, Any] | Any,
        *,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> bool:
        """Verify this signature against the given payload using the provided key.

        Args:
          payload: the raw payload
          key: the validation key to use
          alg: the signature alg t if only 1 is allowed
          algs: the allowed signature algs, if there are several

        Returns:
            `True` if the signature is verifier, `False` otherwise

        """
        key = to_jwk(key)
        signed_part = self.assemble_signed_part(self.protected, payload)
        return key.verify(signed_part, self.signature, alg=alg, algs=algs)
