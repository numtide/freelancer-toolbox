"""This module implements the JWS JSON flat and general formats."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any

from binapy import BinaPy

from jwskate.token import BaseJsonDict

from .compact import JwsCompact
from .signature import JwsSignature

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from jwskate.jwk.base import Jwk


class JwsJsonFlat(JwsSignature):
    """Represent a JWS with a single signature in JSON flat format."""

    @cached_property
    def payload(self) -> bytes:
        """The JWS payload, decoded.

        Returns:
            The raw JWS payload.

        """
        payload = self.get("payload")
        if payload is None:
            msg = "This Jws JSON does not contain a 'payload' member"
            raise AttributeError(msg)
        return BinaPy(payload).decode_from("b64u")

    @cached_property
    def jws_signature(self) -> JwsSignature:
        """The JWS signature.

        Returns:
            The JWS signature.

        """
        content = {
            "protected": self["protected"],
            "signature": self["signature"],
        }
        header = self.get("header")
        if header:
            content["header"] = self.header
        return JwsSignature(content)

    @classmethod
    def sign(
        cls,
        payload: bytes,
        key: Jwk | Mapping[str, Any] | Any,
        alg: str | None = None,
        extra_protected_headers: Mapping[str, Any] | None = None,
        header: Any | None = None,
        **kwargs: Any,
    ) -> JwsJsonFlat:
        """Signs a payload into a JWS in JSON flat format.

        Args:
            payload: the data to sign.
            key: the key to use
            alg: the signature alg to use
            extra_protected_headers: additional protected headers to include
            header: the unprotected header to include
            **kwargs: extra attributes to include in the JWS

        Returns:
            The JWS with the payload, signature, header and extra claims.

        """
        signature = super().sign(payload, key, alg, extra_protected_headers, header, **kwargs)
        signature["payload"] = BinaPy(payload).to("b64u").ascii()
        return cls(signature)

    def generalize(self) -> JwsJsonGeneral:
        """Create a JWS in JSON general format from this JWS in JSON flat.

        Returns:
            A JwsJsonGeneral with the same payload and signature.

        """
        content = self.copy()
        protected = content.pop("protected")
        header = content.pop("header", None)
        signature = content.pop("signature")
        jws_signature = {"protected": protected, "signature": signature}
        if header is not None:
            jws_signature["header"] = header
        content["signatures"] = [jws_signature]
        return JwsJsonGeneral(content)

    def signed_part(self) -> bytes:
        """Return the signed part from this JWS, as bytes.

        This is a concatenation of the protected header and the payload, separated by a dot (`.`).

        Returns:
            The signed data part.

        """
        return JwsSignature.assemble_signed_part(self.protected, self.payload)

    def compact(self) -> JwsCompact:
        """Create a JWS in compact format from this JWS JSON.

        Returns:
            A `JwsCompact` with the same payload and signature.

        """
        return JwsCompact.from_parts(self.signed_part(), self.signature)

    def verify_signature(
        self,
        key: Jwk | Mapping[str, Any] | Any,
        *,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> bool:
        """Verify this JWS signature with a given key.

        Args:
            key: the key to use to validate this signature.
            alg: the signature alg, if only 1 is allowed.
            algs: the allowed signature algs, if there are several.

        Returns:
            `True` if the signature is verified, `False` otherwise.

        """
        return self.jws_signature.verify(self.payload, key, alg=alg, algs=algs)


class JwsJsonGeneral(BaseJsonDict):
    """Represents a JWS in JSON general format (possibly with multiple signatures)."""

    @cached_property
    def payload(self) -> bytes:
        """The raw signed data.

        Returns:
            The signed data.

        """
        payload = self.get("payload")
        if payload is None:
            msg = "This Jws JSON does not contain a 'payload' member"
            raise AttributeError(msg)
        return BinaPy(payload).decode_from("b64u")

    @classmethod
    def sign(
        cls,
        payload: bytes,
        *signature_parameters: (
            tuple[
                Jwk | Mapping[str, Any],
                str,
                Mapping[str, Any] | None,
                Mapping[str, Any] | None,
            ]
            | tuple[
                Jwk | Mapping[str, Any],
                str,
                Mapping[str, Any] | None,
            ]
            | tuple[
                Jwk | Mapping[str, Any],
                str,
            ]
            | Jwk
            | Mapping[str, Any]
        ),
    ) -> JwsJsonGeneral:
        """Sign a payload with several keys and return the resulting JWS in JSON general format.

        Args:
            payload: the data to sign
            *signature_parameters: each of those parameter can be:

                - a `(jwk, alg, extra_protected_headers, header)` tuple
                - a `(jwk, alg, extra_protected_headers)` tuple,
                - a `(jwk, alg)` tuple,
                - a `jwk`

                with:

                - `jwk` being a `Jwk` key,
                - `alg` being the signature algorithm to use,
                - `extra_protected_headers` a mapping of extra protected headers and values to include,
                - `header` the raw unprotected header to include in the signature.

        Returns:
            the generated signatures in JSON General format.

        """
        jws = cls({"payload": BinaPy(payload).to("b64u").ascii()})
        for parameters in signature_parameters:
            jws.add_signature(*parameters)
        return jws

    @cached_property
    def signatures(self) -> list[JwsSignature]:
        """The list of `JwsSignature` from this JWS.

        Returns:
            The list of signatures from this JWS.

        """
        signatures = self.get("signatures")
        if signatures is None:
            msg = "This Jws JSON does not contain a 'signatures' member"
            raise AttributeError(msg)
        return [JwsSignature(sig) for sig in signatures]

    def add_signature(
        self,
        key: Jwk | Mapping[str, Any] | Any,
        alg: str | None = None,
        extra_protected_headers: Mapping[str, Any] | None = None,
        header: Mapping[str, Any] | None = None,
    ) -> JwsJsonGeneral:
        """Add a new signature in this JWS.

        Args:
            key: the private key to use
            alg: the signature algorithm
            extra_protected_headers: additional headers to include, as a {key: value} mapping
            header: the raw unprotected header to include in the signature

        Returns:
            the same JWS with the new signature included.

        """
        self.setdefault("signatures", [])
        self["signatures"].append(JwsSignature.sign(self.payload, key, alg, extra_protected_headers, header))
        return self

    def signed_part(
        self,
        signature_chooser: Callable[[list[JwsSignature]], JwsSignature] = lambda sigs: sigs[0],
    ) -> bytes:
        """Return the signed part from a given signature.

        The signed part is a concatenation of the protected header from a specific signature, then the payload,
        separated by a dot (`.`).

        You can select the specific signature with the `signature_chooser` parameter.
        By default, the first signature is selected.

        Args:
            signature_chooser: a callable that takes the list of signatures from this JWS as parameter,
                and returns the chosen signature.

        Returns:
            The raw signed part from the chosen signature.

        """
        signature = signature_chooser(self.signatures)
        return JwsSignature.assemble_signed_part(signature.protected, self.payload)

    def compact(
        self,
        signature_chooser: Callable[[list[JwsSignature]], JwsSignature] = lambda sigs: sigs[0],
    ) -> JwsCompact:
        """Create a compact JWS from a specific signature from this JWS.

        Args:
            signature_chooser: a callable that takes the list of signatures from this JWS as parameter
                and returns the choosen signature.

        Returns:
            A JwsCompact with the payload and the chosen signature from this JWS.

        """
        signature = signature_chooser(self.signatures)
        return JwsCompact.from_parts(
            JwsSignature.assemble_signed_part(signature.protected, self.payload),
            signature.signature,
        )

    def flatten(
        self,
        signature_chooser: Callable[[list[JwsSignature]], JwsSignature] = lambda sigs: sigs[0],
    ) -> JwsJsonFlat:
        """Create a JWS in JSON flat format from a specific signature from this JWS.

        Args:
            signature_chooser:  a callable that takes the list of signatures from this JWS as parameter
                and returns the choosen signature.

        Returns:
            A JwsJsonFlat with the payload and the chosen signature from this JWS.

        """
        signature = signature_chooser(self.signatures)
        return JwsJsonFlat.from_parts(
            payload=self["payload"],
            protected=signature.protected,
            header=signature.header,
            signature=signature.signature,
        )

    def verify_signature(
        self,
        key: Jwk | Mapping[str, Any] | Any,
        *,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> bool:
        """Verify the signatures from this JWS.

        It tries to validate each signature with the given key, and returns `True` if at least one signature verifies.

        Args:
            key: the public key to use
            alg: the signature algorithm to use, if only 1 is allowed.
            algs: the allowed signature algorithms, if there are several.

        Returns:
            `True` if any of the signature verifies with the given key, `False` otherwise.

        """
        return any(signature.verify(self.payload, key, alg=alg, algs=algs) for signature in self.signatures)
