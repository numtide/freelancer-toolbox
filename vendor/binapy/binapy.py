"""Main module."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import suppress
from functools import wraps
from typing import (
    Any,
    ClassVar,
    Literal,
    Self,
    SupportsBytes,
    SupportsIndex,
    TypeVar,
    cast,
    overload,
)


class BinaPy(bytes):
    """A helper class for binary data manipulation.

    This subclass of `bytes` exposes various binary data manipulation methods. Since this is
    a `bytes` subclass, you can use instances of `BinaPy` anywhere you can use `bytes`. BinaPy
    allows (re)encoding of data using `encode_to(<format>)`, decoding using
    `decode_from(<format>)`, parsing using `parse_from(<format>)`, and serialisation using
    `serialize_to(<format>)`.

    Actual transformations into formats such as Base64, JSON, etc. are implemented using
    Extensions. Those extensions are registered using the decorators `binapy_encoder`,
    `binapy_decoder`, `binapy_checker`, `binapy_serializer`, and `binapy_parser`.

    """

    def __new__(
        cls,
        value: bytes | str | int | SupportsBytes = b"",
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> Self:
        """Override base method to accept a string with a default encoding of "utf-8".

        See Also:
            [`bytes` constructor](https://docs.python.org/3/library/stdtypes.html#bytes) and
            [`str.encode()`](https://docs.python.org/3/library/stdtypes.html#str.encode)

        Args:
            value: a `bytes` or a `str`
            encoding: if value is a `str`, specify the encoding to use to encode this str to bytes
            errors: 'strict', 'ignore', 'replace', 'xmlcharrefreplace', or 'backslashreplace'

        """
        if isinstance(value, str):
            obj = bytes.__new__(cls, value, encoding=encoding, errors=errors)
        else:
            obj = bytes.__new__(cls, value)
        return obj

    @classmethod
    def from_int(
        cls,
        i: int,
        *,
        length: int | None = None,
        byteorder: Literal["little", "big"] = "big",
        signed: bool = False,
    ) -> BinaPy:
        """Convert an `int` to a `BinaPy`.

        This is a wrapper around [int.to_bytes()](https://docs.python.org/3/library/stdtypes.html#int.to_bytes) and
        takes the same parameters.

        Args:
            i: the integer to convert to BinaPy
            length: the length of the integer, in bytes.
              If omitted,default to the minimal length that fits the given integer.
            byteorder: "little" or "big" (defaults to "big")
            signed: determines whether two's complement is used to represent the integer.

        Returns:
            a BinaPy with the binary representation of the given integer

        """
        if length is None:
            length = (i.bit_length() + 7) // 8

        data = i.to_bytes(length, byteorder, signed=signed)
        return cls(data)

    def ascii(self) -> str:
        """Decode this BinaPy to a str.

        This makes sure that only ascii characters are part of the result.

        Returns:
            a str with only ASCII chars

        """
        return self.decode("ascii")

    def re_match(self, pattern: str, encoding: str = "ascii") -> str:
        """Decode this binary value to a string, then match it to a regex.

        Decoding is done using the encoding defined in `encoding` (default to "ascii").
        The decoded value is then matched with the regular expression `pattern`.

        If the match is successful, return the decoded string. Raise a `ValueError` otherwise.

        Args:
            pattern: the regular expression pattern to match
            encoding: the encoding to use to decode the binary value to a string

        Returns:
            the decoded, matching `str`

        Raises:
            ValueError: if the decoded str does not match `pattern`

        """
        res = self.decode(encoding)
        if re.match(pattern, res):
            return res
        msg = f"This value does not match pattern {pattern}"
        raise ValueError(msg)

    def text(self, encoding: str = "ascii") -> str:
        r"""Decode this BinaPy to a str, and check that the result is printable.

        Printable characters are characters from the range `[a-zA-Z0-9!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ]`.

        Args:
            encoding: the encoding to use to decode the binary data

        Returns:
            the decoded text

        """
        return self.re_match(r'^[a-zA-Z0-9!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~ ]*$', encoding)

    def urlsafe(self) -> str:
        r"""Convert this BinaPy to a str, and check that it contains only url-safe characters.

        Url-safe characters are `[A-Za-z0-9_.\\-~]`.

        Returns:
                 a str with only URL-safe chars

        """
        return self.re_match(r"^[A-Za-z0-9_.\-~]$")

    def alphanumeric(self) -> str:
        """Check that this BinaPy contains only alphanumeric characters.

        Returns:
                 a str with only alphanumeric chars

        """
        return self.re_match(r"^[a-zA-Z]$")

    def to_int(self, *, byteorder: Literal["little", "big"] = "big", signed: bool = False) -> int:
        """Convert this BinaPy to an `int`.

        This is a wrapper around
        [int.from_bytes()](https://docs.python.org/3/library/stdtypes.html#int.from_bytes) and takes
        the same parameters.

        Args:
            byteorder: "little" or "big" (defaults to "big")
            signed: determines whether two's complement is used to represent the integer. Default to False.

        Returns:
            an integer based on this BinaPy binary value

        """
        return int.from_bytes(self, byteorder, signed=signed)

    @classmethod
    def from_binary_string(cls, s: str, *, byteorder: Literal["little", "big"] = "big", signed: bool = False) -> BinaPy:
        """Initialize a BinaPy based on a binary string (containing only 0 and 1).

        The string may contain spaces or tabs characters which will be ignored.

        Args:
            s: a binary string
            byteorder: byte order to use
            signed: True if 2 complement is used to represent negative values

        Returns:
            a BinaPy

        """
        s = s.replace(" ", "").replace("\t", "")
        return cls(int(s, 2).to_bytes((len(s) + 7) // 8, byteorder=byteorder, signed=signed))

    def to_binary_string(
        self,
        *,
        byteorder: Literal["little", "big"] = "big",
        signed: bool = False,
        pad: bool = True,
    ) -> str:
        """Return a string containing this BinaPy value in binary representation.

        Args:
            byteorder: byte order to use
            signed: `True` if 2 complement is used to represent negative values
            pad: if `True`, left pad the result with 0 to make length a multiple of 8

        Returns:
            a string with containing only 0 and 1

        """
        binary = format(self.to_int(byteorder=byteorder, signed=signed), "b")
        if pad and len(binary) % 8:
            d = len(binary) // 8
            return binary.rjust(8 * d + 8, "0")
        return binary

    @classmethod
    def random(cls, length: int) -> BinaPy:
        """Return a BinaPy containing `length` random bytes.

        Args:
            length: number of bytes to generate

        Returns:
            a BinaPy with randomly generated data

        """
        return cls(secrets.token_bytes(length))

    @classmethod
    def random_bits(cls, length: int) -> BinaPy:
        """Return a BinaPy containing `length` random bits. Same as random(length//8).

        Length must be a multiple of 8.

        Args:
            length: number of bits to randomly generate

        Returns:
            a BinaPy with randomly generated data

        """
        return cls(secrets.token_bytes(length // 8))

    @overload
    def __getitem__(self, index: SupportsIndex) -> int: ...  # pragma: no cover

    @overload
    def __getitem__(self, slice: slice) -> BinaPy: ...  # pragma: no cover

    def __getitem__(self, slice: slice | SupportsIndex) -> int | BinaPy:  # noqa: A002
        """Override the base method so that slicing returns a BinaPy instead of just bytes.

        Args:
            slice: a slice or index

        Returns:
            A BinaPy

        """
        if isinstance(slice, int):
            return super().__getitem__(slice)
        return self.__class__(super().__getitem__(slice))

    def char_at(self, index: int) -> str:
        """Return the character at the given index.

        Slicing a standard bytes returns an int. Sometimes what you really want is a single char string.

        Args:
            index: the index of the desired character

        Returns:
            the single character at the given index

        """
        return chr(self[index])

    def __add__(
        self,
        other: object,
    ) -> BinaPy:
        """Override base method so that addition returns a BinaPy instead of bytes.

        Args:
            other: bytes or BinaPy to add

        Returns:
            a BinaPy

        """
        if isinstance(other, bytes):
            return self.__class__(super().__add__(other))
        raise NotImplementedError

    def __radd__(self, other: bytes) -> BinaPy:
        """Override base method so that right addition returns a BinaPy instead of bytes.

        Args:
            other: bytes or BinaPy to radd

        Returns:
            a BinaPy

        """
        return self.__class__(other.__add__(self))

    def split(self, sep: bytes | None = None, maxsplit: int = -1) -> list[BinaPy]:  # type: ignore[override]
        """Override base method to return a BinaPy instead of bytes.

        Args:
            sep: a separator
            maxsplit: the maximum number of splits

        Returns:
            a BinaPy

        """
        return [self.__class__(b) for b in super().split(sep, maxsplit)]

    def split_at(self, *pos: int) -> tuple[BinaPy, ...]:
        """Split this BinaPy at one or more integer positions.

        Args:
            *pos: indexes where to cut the BinaPy

        Returns:
            a tuple of `len(pos) + 1` instances of BinaPy

        """
        spos = sorted(pos)
        return tuple(self.__class__(self[start:end]) for start, end in zip([0, *spos], [*spos, len(self)], strict=False))

    cut_at = split_at  # for backward compatibility

    extensions: ClassVar[dict[str, dict[str, Callable[..., Any]]]] = {}
    """Extension registry."""

    @classmethod
    def _get_extension_methods(cls, name: str) -> dict[str, Callable[..., Any]]:
        extension = cls.extensions.get(name)
        if extension is None:
            msg = f"Extension {name} not found"
            raise NotImplementedError(msg)
        return extension

    @classmethod
    def _get_checker(cls, extension_name: str) -> Callable[..., bool]:
        extension_methods = cls._get_extension_methods(extension_name)
        method = extension_methods.get("check")
        if method is None:
            msg = f"Extension '{extension_name}' does not have a checker method"
            raise NotImplementedError(msg)
        return method

    @classmethod
    def _get_decoder(cls, extension_name: str) -> Callable[..., BinaPy]:
        extension_methods = cls._get_extension_methods(extension_name)
        method = extension_methods.get("decode")
        if method is None:
            msg = f"Extension '{extension_name}' does not have a decode method"
            raise NotImplementedError(msg)
        return method

    @classmethod
    def _get_encoder(cls, extension_name: str) -> Callable[..., BinaPy]:
        extension_methods = cls._get_extension_methods(extension_name)
        method = extension_methods.get("encode")
        if method is None:
            msg = f"Extension '{extension_name}' does not have an encode method"
            raise NotImplementedError(msg)
        return method

    @classmethod
    def _get_parser(cls, extension_name: str) -> Callable[..., Any]:
        extension_methods = cls._get_extension_methods(extension_name)
        method = extension_methods.get("parse")
        if method is None:
            msg = f"Extension '{extension_name}' does not have a parse method"
            raise NotImplementedError(msg)
        return method

    @classmethod
    def _get_serializer(cls, extension_name: str) -> Callable[..., BinaPy]:
        extension_methods = cls._get_extension_methods(extension_name)
        method = extension_methods.get("serialize")
        if method is None:
            msg = f"Extension '{extension_name}' does not have a serialize method"
            raise NotImplementedError(msg)
        return method

    def encode_to(self, name: str, *args: Any, **kwargs: object) -> BinaPy:
        """Encode data from this BinaPy according to the format `name`.

        Args:
            name: format to use
            *args: additional position parameters for the extension encoder method
            **kwargs: additional keyword parameters for the extension encoder method

        Returns:
            the resulting data

        """
        encoder = self._get_encoder(name)

        return encoder(self, *args, **kwargs)

    def to(self, name: str, *args: object, **kwargs: object) -> BinaPy:
        """Alias for `encode_to()`.

        Args:
            name: same as `encode_to()`
            *args:  same as `encode_to()`
            **kwargs:  same as `encode_to()`

        Returns:
            same as `encode_to()`

        """
        return self.encode_to(name, *args, **kwargs)

    def decode_from(self, name: str, *args: Any, **kwargs: Any) -> BinaPy:
        """Decode data from this BinaPy according to the format `name`.

        Args:
            name: format name to use
            *args: additional position parameters for the extension decoder method
            **kwargs: additional keyword parameters for the extension decoder method

        Returns:
            the resulting data

        """
        decoder = self._get_decoder(name)

        return decoder(self, *args, **kwargs)

    def check(self, name: str, *, decode: bool = False, raise_on_error: bool = False) -> bool:
        """Check that this BinaPy conforms to a given format extension.

        Args:
            name: the name of the extension to check
            decode: if `True`, and the given extension does not have a checker method,
                try to decode this BinaPy using the decoder method to check if that works.
            raise_on_error: if `True`, exceptions from the checker method, if any,
                will be raised instead of returning `False`.

        Returns:
            a boolean, that is True if this BinaPy conforms to the given extension format, False otherwise.

        """
        # raises an exception in case the extension does not exist
        self._get_extension_methods(name)

        try:
            checker = self._get_checker(name)
            try:
                return checker(self)
            except InvalidExtensionMethodError:
                raise
            except Exception as exc:
                if raise_on_error:
                    raise exc from exc
                return False
        except NotImplementedError:
            # if checker is not implemented and decode is True, try to decode instead
            if decode:
                decoder = self._get_decoder(name)
                try:
                    decoder(self)
                except Exception as exc:
                    if raise_on_error:
                        raise exc from exc
                    return False
                else:
                    return True
            else:
                raise
        return False

    def check_all(self, *, decode: bool = False) -> list[str]:
        """Check if this BinaPy conforms to any of the registered format extensions.

        Returns:
             a list of format extensions that this BinaPy can be decoded from.

        Args:
            decode: if `True`, for extensions that don't have a checker method,
                try to decode this BinaPy using the decoder method to check if that works.

        """

        def get_results() -> Iterator[str]:
            for name in self.extensions:
                with suppress(NotImplementedError):
                    success = self.check(name, decode=decode)
                    if success is True:
                        yield name

        return list(get_results())

    def parse_from(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Parse data from this BinaPy, based on a given format extension.

        Args:
            name: name of the extension to use
            *args: additional position parameters for the extension decoder method
            **kwargs: additional keyword parameters for the extension decoder method

        Returns:
            the result from parsing this BinaPy

        """
        parser = self._get_parser(name)

        return parser(self, *args, **kwargs)

    @classmethod
    def serialize_to(cls, name: str, *args: Any, **kwargs: Any) -> BinaPy:
        """Serialize (dump) data to a BinaPy, based on a given extension format.

        Args:
            name: name of the extension to use
            *args: additional position parameters
                for the extension decoder method (which includes the data to serialize)
            **kwargs: additional keyword parameters for the extension decoder method

        Returns:
            a BinaPy, resulting from serialization of the data

        """
        serializer = cls._get_serializer(name)

        return serializer(*args, **kwargs)

    @classmethod
    def register_extension(cls, name: str, feature: str, func: Callable[..., Any]) -> None:
        """Register a new feature for the given extension name.

        Args:
            name: the extension name
            feature: name of the feature to register ("encode", "decode", etc.)
            func: the method implementing the feature

        """
        ext_dict = cls.extensions.setdefault(name, {})
        ext_dict[feature] = func


F = TypeVar("F", bound=Callable[..., Any])


class InvalidExtensionMethodError(ValueError):
    """Raised when an extension method returns invalid data."""


def binapy_encoder(name: str) -> Callable[[F], F]:
    """Declare new encoders for BinaPy.

    This is a method decorator. Encoders do convert a BinaPy into another BinaPy using a given format/extension.

    Args:
    ----
        name: name of the extension

    Returns:
    -------
        a method decorator

    Usage:
        To declare a special "double-encoding" which just copy the data twice:

        ```python
        from binapy import binapy_encoder


        @binapy_encoder("double")
        def double_encode(data: bytes) -> bytes:
            return data * 2


        assert BinaPy(b"abc").to("double") == b"abcabc"
        ```

    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> BinaPy:
            raw_result = func(*args, **kwargs)
            if not isinstance(raw_result, bytes | bytearray | str):
                msg = f"extension {name} encoder method did not return binary data"
                raise InvalidExtensionMethodError(msg)
            return BinaPy(raw_result)

        BinaPy.register_extension(name, "encode", wrapper)
        return cast(F, wrapper)

    return decorator


def binapy_decoder(name: str) -> Callable[[F], F]:
    """Declare a new decoder for BinaPy.

    This is a method decorator. Decoders do convert BinaPy data from a given format into another BinaPy.

    Args:
    ----
        name: name of the extension

    Returns:
    -------
        a method decorator

    Usage:
        The matching decoder for the special "double-encoding" we created with `binapy_encoder()`:

        ```python
        from binapy import binapy_decoder


        @binapy_decoder("double")
        def double_decode(data: bytes) -> bytes:
            if len(data) % 2 or data[: len(data) // 2] != data[len(data) // 2 :]:
                raise ValueError("This is not a double-encoded data!")
            return data[: len(data) // 2]


        assert BinaPy(b"abcabc").decode_from("double") == b"abc"
        ```

    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> BinaPy:
            raw_result = func(*args, **kwargs)
            if not isinstance(raw_result, bytes | bytearray):
                msg = f"extension {name} decoder method did not return binary data"
                raise InvalidExtensionMethodError(msg)
            return BinaPy(raw_result)

        BinaPy.register_extension(name, "decode", wrapper)
        return cast(F, wrapper)

    return decorator


def binapy_checker(name: str) -> Callable[[F], F]:
    """Declare a new checker for BinaPy.

    This is a decorator. Checker checks that some data is valid for a given format/extension.

    Args:
    ----
        name: name of the extension

    Returns:
    -------
        a method decorator

    Usage:
        The matching checker for the special "double-encoding" we created with `binapy_encoder()`:

        ```python
        from binapy import binapy_checker


        @binapy_checker("double")
        def double_check(data: bytes) -> bytes:
            return len(data) % 2 == 0 and data[: len(data) // 2] == data[len(data) // 2 :]


        assert BinaPy(b"abcabc").check("double")
        ```

    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> bool:
            raw_result = func(*args, **kwargs)

            if not isinstance(raw_result, bool):
                msg = f"extension {name} checker method did not return boolean data"
                raise InvalidExtensionMethodError(msg)
            return raw_result

        BinaPy.register_extension(name, "check", wrapper)
        return cast(F, wrapper)

    return decorator


def binapy_serializer(name: str) -> Callable[[F], F]:
    """Declare a new serializer for BinaPy.

    This is a method decorator. Serializers do convert Python objects into BinaPy.
    For example, a JSON serializer will convert a Python `dict` into a serialized JSON value.

    Args:
    ----
        name: extension name to use

    Returns:
    -------
        a method decorator

    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> BinaPy:
            raw_result = func(*args, **kwargs)
            if not isinstance(raw_result, bytes | bytearray):
                msg = f"extension {name} serializer method did not return binary data"
                raise InvalidExtensionMethodError(msg)
            return BinaPy(raw_result)

        BinaPy.register_extension(name, "serialize", wrapper)
        return cast(F, wrapper)

    return decorator


def binapy_parser(name: str) -> Callable[[F], F]:
    """Declare a new parser for BinaPy.

    This is a method decorator. Parsers do convert BinaPy into Python objects.
    For example, a JSON parser will convert a BinaPy into a dict, by parsing the JSON formatted string from a BinaPy.

    Args:
    ----
        name: the extension name to use

    Returns:
    -------
        a method decorator

    """

    def decorator(func: Callable[..., Any]) -> Any:
        BinaPy.register_extension(name, "parse", func)
        return func

    return decorator
