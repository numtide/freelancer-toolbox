"""This module contains base classes for all tokens types handled by `jwskate`."""

from __future__ import annotations

from collections import UserDict
from functools import cached_property
from typing import Any, Self

from binapy import BinaPy


class BaseCompactToken:
    """Base class for all tokens in Compact representation.

    This includes JWS, JWE, and JWT tokens.

    Args:
        value: the string or bytes representation of this JWS/JWE/JWT
        max_size: if the JWT length is larger than this value, raise a `ValueError`.
            This is to avoid JSON deserialization vulnerabilities.
            Set to 0 or negative value to accept a token of any size.

    """

    def __init__(self, value: bytes | str, *, max_size: int = 16 * 1024) -> None:
        if isinstance(value, str):
            value = value.encode("ascii")

        if 0 < max_size < len(value):
            msg = (
                f"This JWT size of {len(value)} bytes exceeds {max_size} bytes, which is abnormally big. "
                "This size limit is made to avoid potential JSON deserialization vulnerabilities or issues. "
                "You can increase this limit by passing a different `max_size` value as parameter."
            )
            raise ValueError(msg)

        value = b"".join(value.split())

        self.value = value
        self.headers: dict[str, Any]

    def __eq__(self, other: object) -> bool:
        """Check that a Jwt is equal to another.

        Works with other instances of `Jwt`, or with `str` or `bytes`.

        Args:
            other: the other token to compare with

        Returns:
            `True` if the other token has the same representation, `False` otherwise

        """
        if isinstance(other, BaseCompactToken):
            return self.value == other.value
        if isinstance(other, str):
            return self.value.decode() == other
        if isinstance(other, bytes):
            return self.value == other
        return super().__eq__(other)

    def get_header(self, name: str) -> Any:
        """Get a header from this Jwt.

        Args:
            name: the header name

        Returns:
            the header value

        """
        return self.headers.get(name)

    @cached_property
    def alg(self) -> str:
        """Get the signature algorithm (alg) from this token headers.

        Returns:
            the `alg` value
        Raises:
            AttributeError: if the `alg` header value is not a string

        """
        alg = self.get_header("alg")
        if alg is None or not isinstance(alg, str):  # pragma: no branch
            msg = "This token doesn't have a valid 'alg' header"
            raise AttributeError(msg)
        return alg  # type: ignore[no-any-return]

    @cached_property
    def kid(self) -> str:
        """Get the key id (kid) from this token headers.

        Returns:
            the `kid` value
        Raises:
            AttributeError: if the `kid` header value is not a string

        """
        kid = self.get_header("kid")
        if kid is None or not isinstance(kid, str):
            msg = "This token doesn't have a valid 'kid' header"
            raise AttributeError(msg)
        return kid  # type: ignore[no-any-return]

    @cached_property
    def typ(self) -> str:
        """Get the Type (typ) from this token's headers.

        Returns:
            the `typ` value
        Raises:
            AttributeError: if the `typ` header value is not a string

        """
        typ = self.get_header("typ")
        if typ is None or not isinstance(typ, str):  # pragma: no branch
            msg = "This token doesn't have a valid 'typ' header"
            raise AttributeError(msg)
        return typ  # type: ignore[no-any-return]

    @cached_property
    def cty(self) -> str:
        """Get the Type (typ) from this token headers.

        Returns:
            the `cty` value
        Raises:
            AttributeError: if the `cty` header value is not a string

        """
        cty = self.get_header("cty")
        if cty is None or not isinstance(cty, str):  # pragma: no branch
            msg = "This token doesn't have a valid 'cty' header"
            raise AttributeError(msg)
        return cty  # type: ignore[no-any-return]

    def __repr__(self) -> str:
        """Return the `str` representation of this token."""
        return self.value.decode()

    def __bytes__(self) -> bytes:
        """Return the `bytes` representation of this token."""
        return self.value


BaseUserDict = UserDict[str, Any]


class BaseJsonDict(BaseUserDict):
    """Base class Jwk and tokens in JSON representation."""

    @classmethod
    def from_json(cls, j: str) -> Self:
        """Initialize an object based on a string containing a JSON representation.

        Args:
          j: the JSON to parse, still serialized

        Returns:
            the resulting object

        """
        return cls(BinaPy(j).parse_from("json"))

    def to_json(self, *, compact: bool = True, **kwargs: Any) -> str:
        """Serialize the current object into a JSON representation.

        Args:
          compact: if True, don't include whitespaces or newlines in the result
          **kwargs: additional kwargs for json.dumps()

        Returns:
            a JSON representation of the current object

        """
        return BinaPy.serialize_to("json", self, compact=compact, **kwargs).decode()

    def to_dict(self) -> dict[str, Any]:
        """Transform this UserDict into an actual `dict`.

        This should only ever be required when serializing to JSON, since the default json
        serializer doesn't know how to handle UserDicts.

        """
        return {
            key: [
                dict(inner)
                if isinstance(inner, dict)
                else inner.to_dict()
                if isinstance(inner, BaseJsonDict)
                else inner
                for inner in val
            ]
            if isinstance(val, list)
            else dict(val)
            if isinstance(val, dict)
            else val.to_dict()
            if isinstance(val, BaseJsonDict)
            else val
            for key, val in self.data.items()
        }
