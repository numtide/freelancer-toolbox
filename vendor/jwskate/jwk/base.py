"""This module contains the `Jwk` class and associated helpers.

`Jwk` provides the main interface for using or interacting with JWK keys.

Subclasses of `Jwk` will implement the specific key types, like RSA, EC, OKP, and will provide an
interface to access the specific attributes for each key type. Unless you are dealing with a
specific key type and want to access its internal, type-dependent attributes, you should only
need to use the interface from `Jwk`.

"""

from __future__ import annotations

import warnings
from collections.abc import Iterable, Mapping
from contextlib import suppress
from copy import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self, SupportsBytes

from binapy import BinaPy
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from typing_extensions import deprecated

from jwskate.jwa import (
    BaseAESEncryptionAlg,
    BaseAesGcmKeyWrap,
    BaseAesKeyWrap,
    BaseAsymmetricAlg,
    BaseEcdhEs_AesKw,
    BaseKeyManagementAlg,
    BaseRsaKeyWrap,
    BaseSignatureAlg,
    BaseSymmetricAlg,
    DirectKeyUse,
    EcdhEs,
)
from jwskate.token import BaseJsonDict

from .alg import ExpectedAlgRequired, UnsupportedAlg, select_alg_class

if TYPE_CHECKING:
    from .jwks import JwkSet  # pragma: no cover
    from .oct import SymmetricJwk


class UnsupportedKeyType(ValueError):
    """Raised when an unsupported Key Type is requested."""


class InvalidJwk(ValueError):
    """Raised when an invalid JWK is encountered."""


@dataclass(frozen=True)
class JwkParameter:
    """Describe known JWK parameters."""

    description: str
    is_private: bool
    is_required: bool
    kind: str


class Jwk(BaseJsonDict):
    """Represents a Json Web Key (JWK), as specified in RFC7517.

    A JWK is a JSON object that represents a cryptographic key.  The
    members of the object represent properties of the key, also called
    parameters, which are name and value pairs.

    Just like a parsed JSON object, a `Jwk` is a `dict`, so
    you can do with a `Jwk` anything you can do with a `dict`. In
    addition, all keys parameters are exposed as attributes. There are
    subclasses of `Jwk` for each specific Key Type, but unless you are
    dealing with specific parameters for a given key type, you shouldn't
    have to use the subclasses directly since they all present a common
    interface for cryptographic operations.

    Args:
        params: one of

            - a `dict` parsed from a JWK
            - a JSON JWK
            - a `cryptography key`
            - another `Jwk`
            - a `str` containing the JSON representation of a JWK
            - a raw `bytes`
        include_kid_thumbprint: if `True`, and there is no `kid` in the provided params,
            generate a kid based on the key thumbprint. Default to `False`.
            *DEPRECATED: Use `with_kid_thumbprint()`.*

    """

    @classmethod
    def generate_for_alg(cls, alg: str, **kwargs: Any) -> Jwk:
        """Generate a key for usage with a specific `alg` and return the resulting `Jwk`.

        Args:
            alg: a signature or key management algorithm identifier
            **kwargs: specific parameters, depending on the key type, or additional members to include in the `Jwk`

        Returns:
            the generated `Jwk`

        """
        for jwk_class in Jwk.__subclasses__():
            with suppress(UnsupportedAlg):
                jwk_class.get_jwa_wrapper(alg)
                return jwk_class.generate(alg=alg, **kwargs)

        raise UnsupportedAlg(alg)

    @classmethod
    def generate_for_kty(cls, kty: str, **kwargs: Any) -> Jwk:
        """Generate a key with a specific type and return the resulting `Jwk`.

        Args:
          kty: key type to generate
          **kwargs: specific parameters depending on the key type, or additional members to include in the `Jwk`

        Returns:
            the resulting `Jwk`

        Raises:
            UnsupportedKeyType: if the specified key type (`kty`) is not supported

        """
        warnings.warn(
            "Use 'generate' instead (https://github.com/guillp/jwskate/pull/38#issuecomment-2568152368).",
            DeprecationWarning,
            stacklevel=2,
        )
        for jwk_class in Jwk.__subclasses__():
            if kty == jwk_class.KEY_TYPE:
                return jwk_class.generate(**kwargs)
        msg = "Unsupported Key Type:"
        raise UnsupportedKeyType(msg, kty)

    PARAMS: Mapping[str, JwkParameter]

    KEY_TYPE: ClassVar[str]

    CRYPTOGRAPHY_PRIVATE_KEY_CLASSES: ClassVar[tuple[type[Any], ...]]
    CRYPTOGRAPHY_PUBLIC_KEY_CLASSES: ClassVar[tuple[type[Any], ...]]

    SIGNATURE_ALGORITHMS: Mapping[str, type[BaseSignatureAlg]] = {}
    KEY_MANAGEMENT_ALGORITHMS: Mapping[str, type[BaseKeyManagementAlg]] = {}
    ENCRYPTION_ALGORITHMS: Mapping[str, type[BaseAESEncryptionAlg]] = {}

    IANA_HASH_FUNCTION_NAMES: Mapping[str, str] = {
        # IANA registered names to binapy hash name
        "sha-1": "sha1",
        "sha-224": "sha224",
        "sha-256": "sha256",
        "sha-384": "sha384",
        "sha-512": "sha512",
        "shake128": "shake128",
        "shake256": "shake256",
    }

    def __new__(cls, key: Jwk | Mapping[str, Any] | Any, **kwargs: Any) -> Self:
        """Overridden `__new__` to make the Jwk constructor smarter.

        The `Jwk` constructor will accept:

            - a `dict` with the parsed `Jwk` content
            - another `Jwk`, which will be used as-is instead of creating a copy
            - an instance from a `cryptography` public or private key class

        Args:
            key: the source for key materials
            **kwargs: additional members to include in the Jwk

        """
        if cls is Jwk:
            if isinstance(key, Jwk):
                return cls.from_cryptography_key(key.cryptography_key, **kwargs)
            if isinstance(key, Mapping):
                kty: str | None = key.get("kty")
                if kty is None:
                    msg = "A Json Web Key must have a Key Type (kty)"
                    raise InvalidJwk(msg)

                for jwk_class in Jwk.__subclasses__():
                    if kty == jwk_class.KEY_TYPE:
                        return super().__new__(jwk_class)  # type: ignore[return-value]

                msg = "Unsupported Key Type"
                raise InvalidJwk(msg, kty)

            if isinstance(key, str):
                return cls.from_json(key)

            return cls.from_cryptography_key(key, **kwargs)
        return super().__new__(cls)

    def __init__(self, params: Mapping[str, Any] | Any, *, include_kid_thumbprint: bool = False) -> None:
        if isinstance(params, dict):  # this is to avoid double init due to the __new__ above
            super().__init__({key: val for key, val in params.items() if val is not None})
            self._validate()
            if self.get("kid") is None and include_kid_thumbprint:
                self["kid"] = self.thumbprint()

        try:
            self.cryptography_key = self._to_cryptography_key()
        except Exception as exc:
            raise InvalidJwk(params) from exc

    @classmethod
    def get_jwa_wrapper(cls, alg: str) -> type[BaseSignatureAlg | BaseKeyManagementAlg | BaseAESEncryptionAlg]:
        """Given an alg identifier, return the matching JWA wrapper.

        Args:
            alg: an alg identifier

        Returns:
            the matching JWA wrapper

        """
        alg_class: type[BaseSignatureAlg | BaseKeyManagementAlg | BaseAESEncryptionAlg] | None

        alg_class = cls.SIGNATURE_ALGORITHMS.get(alg)
        if alg_class is not None:
            return alg_class

        alg_class = cls.KEY_MANAGEMENT_ALGORITHMS.get(alg)
        if alg_class is not None:
            return alg_class

        alg_class = cls.ENCRYPTION_ALGORITHMS.get(alg)
        if alg_class is not None:
            return alg_class

        raise UnsupportedAlg(alg)

    @property
    def is_private(self) -> bool:
        """Return `True` if the key is private, `False` otherwise."""
        return True

    @property
    def is_public(self) -> bool:
        """Return `True` if the key is *not private* and *not symmetric*, `False` otherwise."""
        return not self.is_private and not self.is_symmetric

    @property
    def is_symmetric(self) -> bool:
        """Return `True` if the key is symmetric, `False` otherwise."""
        return False

    def __getattr__(self, param: str) -> Any:
        """Allow access to key parameters as attributes.

        This is a convenience to allow `jwk.param` instead of `jwk['param']`.

        Args:
            param: the parameter name to access

        Return:
            the param value

        Raises:
            AttributeError: if the param is not found

        """
        value = self.get(param)
        if value is None:
            raise AttributeError(param)
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        """Override base method to avoid modifying cryptographic key attributes.

        Args:
            key: name of the attribute to set
            value: value to set

        Raises:
            RuntimeError: when trying to modify cryptographic attributes

        """
        # don't allow modifying private attributes after the key has been initialized
        if key in self.PARAMS and hasattr(self, "cryptography_key"):
            msg = "JWK key attributes cannot be modified."
            raise RuntimeError(msg)
        super().__setitem__(key, value)

    @property
    def kty(self) -> str:
        """Return the Key Type.

        Returns:
            the key type

        """
        return self.KEY_TYPE

    @property
    def alg(self) -> str | None:
        """Return the configured key alg, if any.

        Returns:
            the key alg

        """
        alg = self.get("alg")
        if alg is not None and not isinstance(alg, str):  # pragma: no branch
            msg = f"Invalid alg type {type(alg)}"
            raise TypeError(msg, alg)
        return alg

    @property
    def kid(self) -> str:
        """Return the JWK key ID (kid).

        If the kid is not explicitly set, the RFC7638 key thumbprint is returned.

        """
        kid = self.get("kid")
        if kid is not None and not isinstance(kid, str):  # pragma: no branch
            msg = f"invalid kid type {type(kid)}"
            raise TypeError(msg, kid)
        if kid is None:
            return self.thumbprint()
        return kid

    @property
    def use(self) -> str | None:
        """Return the key use.

        If no `alg` parameter is present, this returns the `use` parameter from this JWK. If an
        `alg` parameter is present, the use is deduced from this alg. To check for the presence of
        the `use` parameter, use `jwk.get('use')`.

        """
        if self.alg:
            return self.get_jwa_wrapper(self.alg).use
        return self.get("use")

    @property
    def key_ops(self) -> tuple[str, ...]:
        """Return the key operations.

        If no `alg` parameter is present, this returns the `key_ops` parameter from this JWK. If an
        `alg` parameter is present, the key operations are deduced from this alg. To check for the
        presence of the `key_ops` parameter, use `jwk.get('key_ops')`.

        """
        key_ops: tuple[str, ...]
        if self.use == "sig":
            if self.is_symmetric:
                key_ops = ("sign", "verify")
            elif self.is_private:
                key_ops = ("sign",)
            else:
                key_ops = ("verify",)
        elif self.use == "enc":
            if self.is_symmetric:
                if self.alg:
                    alg_class = self.get_jwa_wrapper(self.alg)
                    if issubclass(alg_class, BaseKeyManagementAlg):
                        key_ops = ("wrapKey", "unwrapKey")
                    elif issubclass(alg_class, BaseAESEncryptionAlg):
                        key_ops = ("encrypt", "decrypt")
                else:
                    key_ops = ("wrapKey", "unwrapKey", "encrypt", "decrypt")
            elif self.is_private:
                key_ops = ("unwrapKey",)
            else:
                key_ops = ("wrapKey",)
        else:
            key_ops = self.get("key_ops", ())

        return tuple(key_ops)

    def thumbprint(self, hashalg: str = "sha-256") -> str:
        """Return the key thumbprint as specified by RFC 7638.

        Args:
          hashalg: A hash function (defaults to SHA256)

        Returns:
            the calculated thumbprint

        """
        alg = self.IANA_HASH_FUNCTION_NAMES.get(hashalg)
        if not alg:
            msg = f"Unsupported hash alg {hashalg}"
            raise ValueError(msg)

        t = {"kty": self.get("kty")}
        for name, param in self.PARAMS.items():
            if param.is_required and not param.is_private:
                t[name] = self.get(name)

        return BinaPy.serialize_to("json", t, separators=(",", ":"), sort_keys=True).to(alg).to("b64u").ascii()

    def thumbprint_uri(self, hashalg: str = "sha-256") -> str:
        """Return the JWK thumbprint URI for this key.

        Args:
            hashalg: the IANA registered name for the hash alg to use

        Returns:
             the JWK thumbprint URI for this `Jwk`

        """
        thumbprint = self.thumbprint(hashalg)
        return f"urn:ietf:params:oauth:jwk-thumbprint:{hashalg}:{thumbprint}"

    def check(
        self,
        *,
        is_private: bool | None = None,
        is_symmetric: bool | None = None,
        kty: str | None = None,
    ) -> Jwk:
        """Check this key for type, privateness and/or symmetricness.

        This raises a `ValueError` if the key is not as expected.

        Args:
            is_private:

                - if `True`, check if the key is private,
                - if `False`, check if it is public,
                - if `None`, do nothing
            is_symmetric:

                - if `True`, check if the key is symmetric,
                - if `False`, check if it is asymmetric,
                - if `None`, do nothing
            kty: the expected key type, if any

        Returns:
            this key, if all checks passed

        Raises:
            ValueError: if any check fails

        """
        if is_private is not None:
            if is_private and not self.is_private:
                msg = "This key is public while a private key is expected."
                raise ValueError(msg)
            if not is_private and self.is_private:
                msg = "This key is private while a public key is expected."
                raise ValueError(msg)

        if is_symmetric is not None:
            if is_symmetric and not self.is_symmetric:
                msg = "This key is asymmetric while a symmetric key is expected."
                raise ValueError(msg)
            if not is_symmetric and self.is_symmetric:
                msg = "This key is symmetric while an asymmetric key is expected."
                raise ValueError(msg)

        if kty is not None and self.kty != kty:
            msg = f"This key has kty={self.kty} while a kty={kty} is expected."
            raise ValueError(msg)

        return self

    def _validate(self) -> None:
        """Validate the content of this `Jwk`.

        It checks that all required parameters are present and well-formed.
        If the key is private, it sets the `is_private` flag to `True`.

        Raises:
            TypeError: if the key type doesn't match the subclass
            InvalidJwk: if the JWK misses required members or has invalid members

        """
        if self.get("kty") != self.KEY_TYPE:
            msg = f"This key 'kty' {self.get('kty')} doesn't match this Jwk subclass intended 'kty' {self.KEY_TYPE}!"
            raise TypeError(msg)

        jwk_is_private = False
        for name, param in self.PARAMS.items():
            value = self.get(name)

            if param.is_private and value is not None:
                jwk_is_private = True

            if not param.is_private and param.is_required and value is None:
                msg = f"Missing required public param {param.description} ({name})"
                raise InvalidJwk(msg)

            if value is None:
                continue

            if param.kind == "b64u":
                if not isinstance(value, str):
                    msg = f"Parameter {param.description} ({name}) must be a string with a Base64URL-encoded value"
                    raise InvalidJwk(msg)
                if not BinaPy(value).check("b64u"):
                    msg = f"Parameter {param.description} ({name}) must be a Base64URL-encoded value"
                    raise InvalidJwk(msg)
            elif param.kind == "unsupported":
                if value is not None:  # pragma: no cover
                    msg = f"Unsupported JWK param '{name}'"
                    raise InvalidJwk(msg)
            elif param.kind == "name":
                continue
            else:
                msg = f"Unsupported param '{name}' type '{param.kind}'"
                raise AssertionError(msg)  # pragma: no cover

        # if at least one of the supplied parameter was private, then all required private parameters must be provided
        if jwk_is_private:
            for name, param in self.PARAMS.items():
                value = self.get(name)
                if param.is_private and param.is_required and value is None:
                    msg = f"Missing required private param {param.description} ({name})"
                    raise InvalidJwk(msg)

        # if key is used for signing, it must be private
        for op in self.get("key_ops", []):
            if op in ("sign", "unwrapKey") and not self.is_private:
                msg = f"Key Operation is '{op}' but the key is public"
                raise InvalidJwk(msg)

    def signature_class(self, alg: str | None = None) -> type[BaseSignatureAlg]:
        """Return the appropriate signature algorithm class to use with this key.

        The returned class is a `BaseSignatureAlg` subclass.

        If this key doesn't have an `alg` parameter, you must supply one as parameter to this method.

        Args:
            alg: the algorithm identifier, if not already present in this Jwk

        Returns:
            the appropriate `BaseSignatureAlg` subclass

        """
        return select_alg_class(self.SIGNATURE_ALGORITHMS, jwk_alg=self.alg, alg=alg)

    def encryption_class(self, alg: str | None = None) -> type[BaseAESEncryptionAlg]:
        """Return the appropriate encryption algorithm class to use with this key.

        The returned class is a subclass of `BaseAESEncryptionAlg`.

        If this key doesn't have an `alg` parameter, you must supply one as parameter to this method.

        Args:
            alg: the algorithm identifier, if not already present in this Jwk

        Returns:
            the appropriate `BaseAESEncryptionAlg` subclass

        """
        return select_alg_class(self.ENCRYPTION_ALGORITHMS, jwk_alg=self.alg, alg=alg)

    def key_management_class(self, alg: str | None = None) -> type[BaseKeyManagementAlg]:
        """Return the appropriate key management algorithm class to use with this key.

        If this key doesn't have an `alg` parameter, you must supply one as parameter to this method.

        Args:
            alg: the algorithm identifier, if not already present in this Jwk

        Returns:
            the appropriate `BaseKeyManagementAlg` subclass

        """
        return select_alg_class(self.KEY_MANAGEMENT_ALGORITHMS, jwk_alg=self.alg, alg=alg)

    def signature_wrapper(self, alg: str | None = None) -> BaseSignatureAlg:
        """Initialize a  key management wrapper with this key.

        This returns an instance of a `BaseSignatureAlg` subclass.

        If this key doesn't have an `alg` parameter, you must supply one as parameter to this method.

        Args:
            alg: the algorithm identifier, if not already present in this Jwk

        Returns:
            a `BaseSignatureAlg` instance initialized with the current key

        """
        alg_class = self.signature_class(alg)
        if issubclass(alg_class, BaseSymmetricAlg):
            return alg_class(self.key)
        if issubclass(alg_class, BaseAsymmetricAlg):
            return alg_class(self.cryptography_key)
        raise UnsupportedAlg(alg)  # pragma: no cover

    def encryption_wrapper(self, alg: str | None = None) -> BaseAESEncryptionAlg:
        """Initialize an encryption wrapper with this key.

        This returns an instance of a `BaseAESEncryptionAlg` subclass.

        If this key doesn't have an `alg` parameter, you must supply one as parameter to this method.

        Args:
            alg: the algorithm identifier, if not already present in this Jwk

        Returns:
            a `BaseAESEncryptionAlg` instance initialized with the current key

        """
        alg_class = self.encryption_class(alg)
        if issubclass(alg_class, BaseSymmetricAlg):
            return alg_class(self.key)
        if issubclass(alg_class, BaseAsymmetricAlg):  # pragma: no cover
            return alg_class(self.cryptography_key)  # pragma: no cover
        raise UnsupportedAlg(alg)  # pragma: no cover

    def key_management_wrapper(self, alg: str | None = None) -> BaseKeyManagementAlg:
        """Initialize a key management wrapper with this key.

        This returns an instance of a `BaseKeyManagementAlg` subclass.

        If this key doesn't have an `alg` parameter, you must supply one as parameter to this method.

        Args:
            alg: the algorithm identifier, if not already present in this Jwk

        Returns:
            a `BaseKeyManagementAlg` instance initialized with the current key

        """
        alg_class = self.key_management_class(alg)
        if issubclass(alg_class, BaseSymmetricAlg):
            return alg_class(self.key)
        if issubclass(alg_class, BaseAsymmetricAlg):
            return alg_class(self.cryptography_key)
        raise UnsupportedAlg(alg)  # pragma: no cover

    def supported_signing_algorithms(self) -> list[str]:
        """Return the list of Signature algorithms that can be used with this key.

        Returns:
          a list of supported algs

        """
        return list(self.SIGNATURE_ALGORITHMS)

    def supported_key_management_algorithms(self) -> list[str]:
        """Return the list of Key Management algorithms that can be used with this key.

        Returns:
            a list of supported algs

        """
        return list(self.KEY_MANAGEMENT_ALGORITHMS)

    def supported_encryption_algorithms(self) -> list[str]:
        """Return the list of Encryption algorithms that can be used with this key.

        Returns:
            a list of supported algs

        """
        return list(self.ENCRYPTION_ALGORITHMS)

    def sign(self, data: bytes | SupportsBytes, alg: str | None = None) -> BinaPy:
        """Sign data using this Jwk, and return the generated signature.

        Args:
          data: the data to sign
          alg: the alg to use (if this key doesn't have an `alg` parameter)

        Returns:
          the generated signature

        """
        wrapper = self.signature_wrapper(alg)
        signature = wrapper.sign(data)
        return BinaPy(signature)

    def verify(
        self,
        data: bytes | SupportsBytes,
        signature: bytes | SupportsBytes,
        *,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> bool:
        """Verify a signature using this `Jwk`, and return `True` if valid.

        Args:
          data: the data to verify
          signature: the signature to verify
          alg: the allowed signature alg, if there is only one
          algs: the allowed signature algs, if there are several

        Returns:
          `True` if the signature matches, `False` otherwise

        """
        if not self.is_symmetric and self.is_private:
            warnings.warn(
                "You are trying to validate a signature with a private key. "
                "Signatures should always be verified with a public key.",
                stacklevel=2,
            )
            public_jwk = self.public_jwk()
        else:
            public_jwk = self
        if algs is None and alg:
            algs = [alg]
        for candidate_alg in algs or (None,):
            wrapper = public_jwk.signature_wrapper(candidate_alg)
            if wrapper.verify(data, signature):
                return True

        return False

    def sender_key(
        self,
        enc: str,
        *,
        alg: str | None = None,
        cek: bytes | None = None,
        epk: Jwk | None = None,
        **headers: Any,
    ) -> tuple[SymmetricJwk, BinaPy, Mapping[str, Any]]:
        """Produce a Content Encryption Key, to use for encryption.

        This method is meant to be used by encrypted token senders.
        Recipients should use the matching method `Jwk.recipient_key()`.

        Returns a tuple with 3 items:

        - the clear text CEK, as a `SymmetricJwk` instance.
        Use this key to encrypt your message, but do not communicate this key to anyone!
        - the encrypted CEK, as bytes. You must send this to your recipient.
        This may be `None` for Key Management algs which derive a CEK instead of generating one.
        - extra headers depending on the Key Management algorithm, as a dict of name to values.
        You must send those to your recipient as well.

        For algorithms that rely on a randomly generated CEK, such as RSAES or AES, you can provide that CEK instead
        of letting `jwskate` generate a safe, unique random value for you.
        Likewise, for algorithms that rely on an ephemeral key, you can provide an EPK that you generated yourself,
        instead of letting `jwskate` generate an appropriate value for you.
        Only do this if you know what you are doing!

        Args:
          enc: the encryption algorithm to use with the CEK
          alg: the Key Management algorithm to use to produce the CEK
          cek: CEK to use (leave `None` to have an adequate random value generated automatically)
          epk: EPK to use (leave `None` to have an adequate ephemeral key generated automatically)
          **headers: additional headers to include for the CEK derivation

        Returns:
          a tuple (cek, wrapped_cek, additional_headers_map)

        Raises:
            UnsupportedAlg: if the requested alg identifier is not supported

        """
        from jwskate import SymmetricJwk

        if not self.is_symmetric and self.is_private:
            warnings.warn(
                "You are using a private key for sender key wrapping. "
                "Key wrapping should always be done using the recipient public key.",
                stacklevel=2,
            )
            key_alg_wrapper = self.public_jwk().key_management_wrapper(alg)
        else:
            key_alg_wrapper = self.key_management_wrapper(alg)

        enc_alg_class = select_alg_class(SymmetricJwk.ENCRYPTION_ALGORITHMS, alg=enc)

        cek_headers: dict[str, Any] = {}

        if isinstance(key_alg_wrapper, BaseRsaKeyWrap | BaseAesKeyWrap):
            if cek:
                enc_alg_class.check_key(cek)
            else:
                cek = enc_alg_class.generate_key()
            wrapped_cek = key_alg_wrapper.wrap_key(cek)

        elif isinstance(key_alg_wrapper, EcdhEs):
            epk = epk or Jwk.from_cryptography_key(key_alg_wrapper.generate_ephemeral_key())
            cek_headers = {"epk": epk.public_jwk()}
            if isinstance(key_alg_wrapper, BaseEcdhEs_AesKw):
                if cek:
                    enc_alg_class.check_key(cek)
                else:
                    cek = enc_alg_class.generate_key()
                wrapped_cek = key_alg_wrapper.wrap_key_with_epk(
                    cek,
                    epk.cryptography_key,
                    alg=key_alg_wrapper.name,
                    **headers,
                )
            else:
                cek = key_alg_wrapper.sender_key(
                    epk.cryptography_key,
                    alg=enc_alg_class.name,
                    key_size=enc_alg_class.key_size,
                    **headers,
                )
                wrapped_cek = BinaPy(b"")

        elif isinstance(key_alg_wrapper, BaseAesGcmKeyWrap):
            if cek:
                enc_alg_class.check_key(cek)
            else:
                cek = enc_alg_class.generate_key()
            iv = key_alg_wrapper.generate_iv()
            wrapped_cek, tag = key_alg_wrapper.wrap_key(cek, iv=iv)
            cek_headers = {
                "iv": iv.to("b64u").ascii(),
                "tag": tag.to("b64u").ascii(),
            }

        elif isinstance(key_alg_wrapper, DirectKeyUse):
            cek = key_alg_wrapper.direct_key(enc_alg_class)
            wrapped_cek = BinaPy(b"")
        else:
            msg = f"Unsupported Key Management Alg {key_alg_wrapper}"
            raise UnsupportedAlg(msg)  # pragma: no cover

        return SymmetricJwk.from_bytes(cek), wrapped_cek, cek_headers

    def recipient_key(
        self,
        wrapped_cek: bytes | SupportsBytes,
        enc: str,
        *,
        alg: str | None = None,
        **headers: Any,
    ) -> SymmetricJwk:
        """Produce a Content Encryption Key, to use for decryption.

        This method is meant to be used by encrypted token recipient.
        Senders should use the matching method `Jwk.sender_key()`.

        Args:
          wrapped_cek: The wrapped CEK.
          enc: The encryption algorithm to use with the CEK.
          alg: The Key Management algorithm to use to unwrap the CEK.
          **headers: Additional headers used to decrypt the CEK (e.g. "epk" for ECDH algs, "iv", "tag" for AES-GCM algs)

        Returns:
          The clear-text CEK.

        Raises:
            UnsupportedAlg: If the requested alg identifier is not supported.

        """
        from jwskate import SymmetricJwk

        if not self.is_symmetric and not self.is_private:
            msg = (
                "You are using a public key for recipient key unwrapping. "
                "Key unwrapping must always be done using the recipient private key."
            )
            raise ValueError(msg)

        key_alg_wrapper = self.key_management_wrapper(alg)
        enc_alg_class = select_alg_class(SymmetricJwk.ENCRYPTION_ALGORITHMS, alg=enc)

        if isinstance(key_alg_wrapper, BaseRsaKeyWrap):
            cek = key_alg_wrapper.unwrap_key(wrapped_cek)

        elif isinstance(key_alg_wrapper, EcdhEs):
            epk = headers.get("epk")
            if epk is None:
                msg = "No EPK in the headers!"
                raise ValueError(msg)
            epk_jwk = Jwk(epk)
            if epk_jwk.is_private:
                msg = "The EPK present in the header is private."
                raise ValueError(msg)
            epk = epk_jwk.cryptography_key
            if isinstance(key_alg_wrapper, BaseEcdhEs_AesKw):
                cek = key_alg_wrapper.unwrap_key_with_epk(wrapped_cek, epk, alg=key_alg_wrapper.name)
            else:
                cek = key_alg_wrapper.recipient_key(
                    epk,
                    alg=enc_alg_class.name,
                    key_size=enc_alg_class.key_size,
                    **headers,
                )

        elif isinstance(key_alg_wrapper, BaseAesKeyWrap):
            cek = key_alg_wrapper.unwrap_key(wrapped_cek)

        elif isinstance(key_alg_wrapper, BaseAesGcmKeyWrap):
            iv = headers.get("iv")
            if iv is None:
                msg = "No 'iv' in headers!"
                raise ValueError(msg)
            iv = BinaPy(iv).decode_from("b64u")
            tag = headers.get("tag")
            if tag is None:
                msg = "No 'tag' in headers!"
                raise ValueError(msg)
            tag = BinaPy(tag).decode_from("b64u")
            cek = key_alg_wrapper.unwrap_key(wrapped_cek, tag=tag, iv=iv)

        elif isinstance(key_alg_wrapper, DirectKeyUse):
            cek = key_alg_wrapper.direct_key(enc_alg_class)

        else:
            msg = f"Unsupported Key Management Alg {key_alg_wrapper}"
            raise UnsupportedAlg(msg)  # pragma: no cover

        return SymmetricJwk.from_bytes(cek)

    def public_jwk(self) -> Jwk:
        """Return the public Jwk associated with this key.

        Returns:
          a Jwk with the public key

        """
        if not self.is_private:
            return self

        params = {name: self.get(name) for name, param in self.PARAMS.items() if not param.is_private}

        if "key_ops" in self:
            key_ops = list(self.key_ops)
            if "sign" in key_ops:
                key_ops.remove("sign")
                key_ops.append("verify")
            if "unwrapKey" in key_ops:
                key_ops.remove("unwrapKey")
                key_ops.append("wrapKey")
        else:
            key_ops = None

        return Jwk(
            dict(
                kty=self.kty,
                kid=self.get("kid"),
                alg=self.get("alg"),
                use=self.get("use"),
                key_ops=key_ops,
                **params,
            ),
        )

    def as_jwks(self) -> JwkSet:
        """Return a JwkSet with this key as single element.

        Returns:
            a JwsSet with this single key

        """
        from .jwks import JwkSet

        return JwkSet(keys=(self,))

    @classmethod
    def from_cryptography_key(cls, cryptography_key: Any, **kwargs: Any) -> Self:
        """Initialize a Jwk from a key from the `cryptography` library.

        The input key can be any private or public key supported by cryptography.

        Args:
          cryptography_key: a `cryptography` key instance
          **kwargs: additional members to include in the Jwk (e.g. kid, use)

        Returns:
            the matching `Jwk` instance

        Raises:
            TypeError: if the key type is not supported

        """
        for jwk_class in cls.__subclasses__():
            for cryptography_class in (
                jwk_class.CRYPTOGRAPHY_PRIVATE_KEY_CLASSES + jwk_class.CRYPTOGRAPHY_PUBLIC_KEY_CLASSES
            ):
                if isinstance(cryptography_key, cryptography_class):
                    return jwk_class.from_cryptography_key(cryptography_key, **kwargs)

        msg = f"Unsupported Jwk class for this Key Type: {type(cryptography_key).__name__}"
        raise TypeError(msg)

    def _to_cryptography_key(self) -> Any:
        """Return a key from the `cryptography` library that matches this Jwk.

        This is implemented by subclasses.

        Returns:
            a `cryptography`key instance initialized from the current key

        """
        raise NotImplementedError

    @classmethod
    def from_pem(
        cls,
        pem: bytes | str,
        password: bytes | str | None = None,
        **kwargs: Any,
    ) -> Jwk:
        """Load a `Jwk` from a PEM encoded private or public key.

        Args:
          pem: the PEM encoded data to load
          password: the password to decrypt the PEM, if required. Should be bytes.
              If it is a string, it will be encoded with UTF-8.
          **kwargs: additional members to include in the `Jwk` (e.g. `kid`, `use`)

        Returns:
            a `Jwk` instance from the loaded key

        """
        pem = pem.encode() if isinstance(pem, str) else pem
        password = password.encode("UTF-8") if isinstance(password, str) else password

        try:
            cryptography_key = serialization.load_pem_private_key(pem, password)
        except ValueError as private_exc:
            try:
                cryptography_key = serialization.load_pem_public_key(pem)

            except ValueError:
                msg = "The provided data is not a private or a public PEM encoded key."
                raise ValueError(msg) from private_exc
            if password is not None:
                msg = (
                    "A public key was loaded from PEM, while a password was provided for decryption. "
                    "Only private keys are encrypted using a password."
                )
                raise ValueError(msg) from None

        return cls.from_cryptography_key(cryptography_key, **kwargs)

    def to_pem(self, password: bytes | str | None = None) -> str:
        """Serialize this key to PEM format.

        For private keys, you can provide a password for encryption. This password should be `bytes`. A `str` is also
        accepted, and will be encoded to `bytes` using UTF-8 before it is used as encryption key.

        Args:
          password: password to use to encrypt the PEM.

        Returns:
            the PEM serialized key

        """
        password = password.encode("UTF-8") if isinstance(password, str) else password

        if self.is_private:
            encryption: serialization.KeySerializationEncryption
            encryption = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
            return self.cryptography_key.private_bytes(  # type: ignore[no-any-return]
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                encryption,
            ).decode()

        if password:
            msg = "Public keys cannot be encrypted when serialized."
            raise ValueError(msg)
        return self.cryptography_key.public_bytes(  # type: ignore[no-any-return]
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    @classmethod
    def from_der(
        cls,
        der: bytes,
        password: bytes | str | None = None,
        **kwargs: Any,
    ) -> Jwk:
        """Load a `Jwk` from a DER encoded key."""
        password = password.encode("UTF-8") if isinstance(password, str) else password

        try:
            cryptography_key = serialization.load_der_private_key(der, password)
        except ValueError as private_exc:
            try:
                cryptography_key = serialization.load_der_public_key(der)
            except ValueError:
                msg = "The provided data is not a private or a public DER encoded key."
                raise ValueError(msg) from private_exc
            if password is not None:
                msg = (
                    "A public key was loaded from DER, while a password was provided for decryption. "
                    "Only private keys are encrypted using a password."
                )
                raise ValueError(msg) from None

        return cls.from_cryptography_key(cryptography_key, **kwargs)

    def to_der(self, password: bytes | str | None = None) -> BinaPy:
        """Serialize this key to DER encoding.

        For private keys, you can provide a password for encryption. This password should be bytes. A `str` is also
        accepted, and will be encoded to `bytes` using UTF-8 before it is used as encryption key.

        Args:
          password: password to use to encrypt the PEM. Should be bytes.
            If it is a string, it will be encoded to bytes with UTF-8.

        Returns:
            the DER serialized key

        """
        password = password.encode("UTF-8") if isinstance(password, str) else password

        if self.is_private:
            encryption: serialization.KeySerializationEncryption
            encryption = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
            return BinaPy(
                self.cryptography_key.private_bytes(
                    serialization.Encoding.DER,
                    serialization.PrivateFormat.PKCS8,
                    encryption,
                ),
            )

        if password:
            msg = "Public keys cannot be encrypted when serialized."
            raise ValueError(msg)
        return BinaPy(
            self.cryptography_key.public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ),
        )

    @classmethod
    def from_x509_cert(
        cls,
        cert: x509.Certificate,
        *,
        include_x5t: bool = False,
        include_x5t_s256: bool = False,
    ) -> Self:
        """Load a Public Key from a `cryptography` X509 `Certificate` instance.

        You may include the certificate thumbprint in the resulting `Jwk`:
        - set `include_x5t` to `True` to include a `x5t` parameter (hashed with SHA1)
        - set `include_x5t_s256` to `True` to include a `x5t#S256` parameter (hashed with SHA256)

        Args:
            cert: a `cryptography` `Certificate` instance
            include_x5t: if `True`, include a `x5t` parameter
            include_x5t_s256: if `True`, include a `x5t#256` parameter

        Returns:
            a `Jwk` instance initialized with the Certificate public key

        """
        extra = {}
        if include_x5t:
            extra["x5t"] = BinaPy(cert.fingerprint(hashes.SHA1())).to("b64u").ascii()  # noqa: S303
        if include_x5t_s256:
            extra["x5t#S256"] = BinaPy(cert.fingerprint(hashes.SHA256())).to("b64u").ascii()
        return cls.from_cryptography_key(cert.public_key(), **extra)

    @classmethod
    def from_x509_pem(cls, x509_pem: str | bytes, *, include_x5t: bool = False, include_x5t_s256: bool = False) -> Self:
        """Read the public key from a X509 certificate, PEM formatted."""
        if isinstance(x509_pem, str):
            x509_pem = x509_pem.encode()

        cert = x509.load_pem_x509_certificate(x509_pem)
        return cls.from_x509_cert(cert, include_x5t=include_x5t, include_x5t_s256=include_x5t_s256)

    @classmethod
    def from_x509_der(cls, x509_der: bytes, *, include_x5t: bool = False, include_x5t_s256: bool = False) -> Self:
        """Read the public key from a X509 certificate, DER formatted."""
        cert = x509.load_der_x509_certificate(x509_der)
        return cls.from_x509_cert(cert, include_x5t=include_x5t, include_x5t_s256=include_x5t_s256)

    @classmethod
    @deprecated("Use from_x509_pem() instead")
    def from_x509(cls, x509_pem: str | bytes) -> Self:
        """Deprecated.

        Use Jwk.from_x509_pem() instead.

        """
        return cls.from_x509_pem(x509_pem)

    @classmethod
    def from_pkcs12(cls, p12: bytes, password: bytes | str | None) -> Self:
        """Read a private key from a PKCS12 data, password-protected.

        PKCS12 typically contain a private key and one or more associated certificates.
        This will only read a single private key and return the matching `Jwk`.
        PKCS12 files are binary, and usually have a `.p12` or `.pfx` extension.

        PKCS12 files are typically protected with a password, which you must provide
        as parameter to this method. If you provide a password as a `str`, it will be
        encoded with UTF-8 before being used for decryption, just like OpenSSL>1.1.0
        expects. If your PKCS12 file and password were generated with OpenSSL<=1.1.0,
        you must provide the password as `bytes`, encoded with either 'ASCII' or 'ISO8859-1'

        See:
            https://www.openssl.org/docs/man3.0/man7/passphrase-encoding.html#:~:text=PKCS#12

        Args:
            p12: the raw PKCS12 binary data
            password: the decryption password, if any.

        Returns:
            A `Jwk` instance with the private key read from the PKCS12 data

        """
        if isinstance(password, str):
            password = password.encode("UTF-8")
        key, _, _ = pkcs12.load_key_and_certificates(p12, password)
        return cls.from_cryptography_key(key)

    @classmethod
    def generate(cls, *, alg: str | None = None, kty: str | None = None, **kwargs: Any) -> Jwk:
        """Generate a Private Key and return it as a `Jwk` instance.

        This method is implemented by subclasses for specific Key Types and returns an instance of that subclass.

        Args:
            alg: intended algorithm to use with the generated key
            kty: key type identifier
            **kwargs: specific parameters depending on the type of key, or additional members to include in the `Jwk`

        Returns:
            a `Jwk` instance with a generated key

        """
        if alg:
            key = cls.generate_for_alg(alg=alg, **kwargs)
            if kty is not None and key.kty != kty:
                msg = f"Incompatible `{alg=}` and `{kty=}` parameters. `{alg=}` points to `kty='{key.kty}'`."
                raise ValueError(msg)
            return key
        if kty:
            return cls.generate_for_kty(kty=kty, **kwargs)
        msg = (
            "You must provide a hint for jwskate to know what kind of key it must generate. "
            "You can either provide an 'alg' identifier as keyword parameter, and/or a 'kty'."
        )
        raise ValueError(msg)

    def copy(self) -> Jwk:
        """Create a copy of this key.

        Returns:
            a copy of this key, with the same value

        """
        return Jwk(copy(self.data))

    def with_kid_thumbprint(self, *, force: bool = False) -> Jwk:
        """Include the JWK thumbprint as `kid`.

        If key already has a `kid` (Key ID):

        - if `force` is `True`, this erases the previous "kid".
        - if `force` is `False` (default), do nothing.

        Args:
            force: whether to overwrite a previously existing kid

        Returns:
            a copy of this Jwk, with a `kid` attribute.

        """
        jwk = self.copy()
        if self.get("kid") is not None and not force:
            return jwk
        jwk["kid"] = self.thumbprint()
        return jwk

    def with_usage_parameters(
        self,
        alg: str | None = None,
        *,
        with_alg: bool = True,
        with_use: bool = True,
        with_key_ops: bool = True,
    ) -> Jwk:
        """Copy this Jwk and add the `use` and `key_ops` parameters.

        The returned jwk `alg` parameter will be the one passed as parameter to this method,
        or as default the one declared as `alg` parameter in this Jwk.

        The `use` (Public Key Use) param is deduced based on this `alg` value.

        The `key_ops` (Key Operations) param is deduced based on the key `use` and if the key is public, private,
        or symmetric.

        Args:
            alg: the alg to use, if not present in this Jwk
            with_alg: whether to include an `alg` parameter
            with_use: whether to include a `use` parameter
            with_key_ops: whether to include a `key_ops` parameter

        Returns:
            a Jwk with the same key, with `alg`, `use` and `key_ops` parameters.

        """
        alg = alg or self.alg

        if not alg:
            msg = "An algorithm is required to set the usage parameters"
            raise ExpectedAlgRequired(msg)

        self.get_jwa_wrapper(alg)  # raises an exception if alg is not supported

        jwk = self.copy()
        if with_alg:
            jwk["alg"] = alg
        if with_use:
            jwk["use"] = jwk.use
        if with_key_ops:
            jwk["key_ops"] = jwk.key_ops

        return jwk

    def minimize(self) -> Jwk:
        """Strip out any optional or non-standard parameter from that key.

        This will remove `alg`, `use`, `key_ops`, optional parameters from RSA keys, and other
        unknown parameters.

        """
        jwk = self.copy()
        for key in self.keys():
            if key == "kty" or (key in self.PARAMS and self.PARAMS[key].is_required):
                continue
            del jwk[key]

        return jwk

    def __eq__(self, other: object) -> bool:
        """Compare JWK keys, ignoring optional/informational fields."""
        other = to_jwk(other)
        return super(Jwk, self.minimize()).__eq__(other.minimize())


def to_jwk(
    key: Any,
    *,
    kty: str | None = None,
    is_private: bool | None = None,
    is_symmetric: bool | None = None,
) -> Jwk:
    """Convert any supported kind of key to a `Jwk`.

    This optionally checks if that key is private or symmetric.

    The key can be any type supported by Jwk:
    - a `cryptography` key instance
    - a bytes, to initialize a symmetric key
    - a JWK, as a dict or as a JSON formatted string
    - an existing Jwk instance
    If the supplied param is already a Jwk, it is left untouched.

    Args:
        key: the key material
        kty: the expected key type
        is_private: if `True`, check if the key is private, if `False`, check if it is public, if `None`, do nothing
        is_symmetric: if `True`, check if the key is symmetric, if `False`, check if it is asymmetric,
            if `None`, do nothing

    Returns:
        a Jwk key

    """
    jwk = key if isinstance(key, Jwk) else Jwk(key)
    return jwk.check(kty=kty, is_private=is_private, is_symmetric=is_symmetric)
