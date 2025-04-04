"""This module contains several utilities for algorithmic agility."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, TypeVar

from jwskate.jwa import BaseAlg

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


class UnsupportedAlg(ValueError):
    """Raised when a unsupported alg is requested."""


class ExpectedAlgRequired(ValueError):
    """Raised when the expected signature alg(s) must be provided."""


class MismatchingAlg(ValueError):
    """Raised when attempting a cryptographic operation with an unexpected algorithm.

    Signature verification or a decryption operation with an algorithm that does not match the
    algorithm specified in the key or the token.

    """

    def __init__(
        self,
        target_alg: str,
        alg: str | None = None,
        algs: Iterable[str] | None = None,
    ) -> None:
        self.target_alg = target_alg
        self.alg = alg
        self.algs = list(algs) if algs else None


T = TypeVar("T", bound=type[BaseAlg])


def select_alg_class(
    supported_algs: Mapping[str, T],
    *,
    jwk_alg: str | None = None,
    alg: str | None = None,
    strict: bool = False,
) -> T:
    """Choose the appropriate alg class to use for cryptographic operations.

    Given:
    - a mapping of supported algs names to wrapper classes
    - a preferred alg name (usually the one mentioned in a JWK)
    - and/or a user-specified alg
    this returns the wrapper class to use.

    This checks the coherency between the user specified `alg` and the `jwk_alg`, and will emit a warning
    if the user specified alg is different from the `jwk_alg`.

    Args:
      supported_algs: a mapping of supported alg names to alg wrapper
      jwk_alg: the alg from the JWK, if any
      alg: a user specified alg
      strict: if `True` and alg does not match `jwk_alg`, raise a `MismatchingAlg` exception. If `False`, warn instead.

    Returns:
      the alg to use

    Raises:
        UnsupportedAlg: if the requested `alg` is not supported
        ValueError: if `supported_algs` is empty
        MismatchingAlg: if `alg` does not match `jwk_alg`

    """
    if not supported_algs:
        msg = "No possible algorithms to choose from!"
        raise ValueError(msg)

    choosen_alg: str
    if jwk_alg is not None:
        if alg is not None:
            if jwk_alg != alg:
                if strict:
                    raise MismatchingAlg(jwk_alg, alg)
                warnings.warn(
                    f"This key has an 'alg' parameter '{jwk_alg}', which should be used for each operation,"
                    f" but requested algorithm is '{alg}'.",
                    stacklevel=3,
                )
            choosen_alg = alg
        else:
            choosen_alg = jwk_alg
    elif alg is not None:
        choosen_alg = alg
    else:
        msg = (
            "This key doesn't have an 'alg' parameter specifying which algorithm to use with that key, "
            "so you need to provide the expected signing alg(s) for each operation."
        )
        raise ExpectedAlgRequired(msg)

    try:
        return supported_algs[choosen_alg]
    except KeyError:
        msg = f"Alg '{choosen_alg}' is not supported by this key. Supported algs are: {', '.join(supported_algs)}."
        raise UnsupportedAlg(msg) from None


def select_alg_classes(
    supported_algs: Mapping[str, T],
    *,
    jwk_alg: str | None = None,
    alg: str | None = None,
    algs: Iterable[str] | None = None,
    strict: bool = False,
) -> list[T]:
    """Select several appropriate algs classes to use on cryptographic operations.

    This method is typically used to get the list of valid algorithms when checking a signature,
    when several algorithms are allowed.

    Given:

    - a mapping of supported algorithms name to wrapper classes
    - an alg parameter from a JWK
    - and/or a user-specified alg
    - and/or a user specified list of usable algs

    this returns a list of supported alg wrapper classes that matches what the user specified, or, as default,
    the alg parameter from the JWK.

    This checks the coherency between the user specified `alg` and the `jwk_alg`, and will emit a warning
    if the user specified alg is different from the `jwk_alg`.

    Args:
      supported_algs: a mapping of alg names to alg wrappers
      jwk_alg: the alg from the JWK, if any
      alg: a user specified alg to use, if any
      algs: a user specified list of algs to use, if several are allowed
      strict: if `True` and alg does not match `jwk_alg`, raise a `MismatchingAlg` exception. If `False`, warn instead.

    Returns:
      a list of possible algs to check

    Raises:
        ValueError: if both 'alg' and 'algs' parameters are used
        UnsupportedAlg: if none of the requested alg are supported

    """
    if alg and algs:
        msg = "Please use either parameter 'alg' or 'algs', not both."
        raise ValueError(msg)

    if not supported_algs:
        msg = "No possible algorithms to choose from!"
        raise ValueError(msg)

    if jwk_alg is not None and ((alg and alg != jwk_alg) or (algs and jwk_alg not in algs)):
        if strict:
            raise MismatchingAlg(jwk_alg, alg, algs)
        requested_alg = f"{alg=}" if alg else f"{algs=}"
        warnings.warn(
            f"This key has an 'alg' parameter with value {jwk_alg}, so you should use it with that alg only."
            f"You requested '{requested_alg}'.",
            stacklevel=2,
        )

    possible_algs: list[str] = []
    if alg:
        possible_algs = [alg]
    elif algs:
        possible_algs = list(algs)
    elif jwk_alg:
        possible_algs = [jwk_alg]

    if possible_algs:
        possible_supported_algs = [supported_algs[alg] for alg in possible_algs if alg in supported_algs]
        if possible_supported_algs:
            return possible_supported_algs
        msg = (
            f"None of the user-specified alg(s) are supported by this key."
            f" Supported algs are '{', '.join(possible_algs)}'."
        )
        raise UnsupportedAlg(msg)

    msg = (
        "This key doesn't have an 'alg' parameter specifying which algorithm to use with that key, "
        "so you need to provide the expected signing alg(s) for each operation."
    )
    raise ExpectedAlgRequired(msg)
