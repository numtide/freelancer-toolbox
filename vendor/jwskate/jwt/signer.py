"""High level JWT signing helpers.

While you can use the method `Jwt.sign()` with all parameters to generate JWT tokens, this will soon prove to be
impractical for real application usage where the issuer is static, expiration time must be a configured number of
seconds in the future, tokens must include a uniquely generated Jwt Token ID, and signing key is mostly static (but
might be renewed once in a while).

To make things easier, you should use the `JwtSigner` class, which you can pre-configure with a static issuer, private
key, and signing alg.
Once initialized, you can simply pass the token specific subject, audience and additional claims to `JwtSigner.sign()`,
and a signed Jwt will be prepared accordingly.

If you do not care about using a specific private key, you can initialize a `JwtSigner` with a randomly generated key:

```python
from jwskate import JwtSigner, ECJwk

signer = JwtSigner.with_random_key(issuer="https://myissuer.local", alg="ES256")
jwt = signer.sign(subject="myuser", audience="myapp")

# you can access the generated private key, for example if you need to persist it:
assert isinstance(signer.jwk, ECJwk) and signer.jwk.is_private
```

"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from jwskate.jwk import Jwk, to_jwk

from .base import Jwt
from .verifier import JwtVerifier

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from .signed import SignedJwt


class JwtSigner:
    """A helper class to easily sign JWTs with standardized claims.

    The standardized claims include:

       - `Ìat`: issued at date
       - `exp`: expiration date
       - `nbf`: not before date
       - `iss`: issuer identifier
       - `sub`: subject identifier
       - `aud`: audience identifier
       - `jti`: JWT token ID

    The issuer, signing keys, signing alg and default lifetime are
    defined at initialization time, so you only have to define the
    subject, audience and custom claims when calling `JwtSigner.sign()`.
    This can be used as an alternative to `Jwt.sign()` when a single
    issuer issues multiple tokens.

    Args:
        issuer: the issuer string to use as `ìss` claim for signed tokens.
        key: the private Jwk to use to sign tokens.
        alg: the signing alg to use to sign tokens.
        default_lifetime: the default lifetime, in seconds, to use for claim `exp`. This can be overridden
            when calling `.sign()`
        default_leeway: the default leeway, in seconds, to use for claim `nbf`. If None, no `nbf` claim is
            included. This can be overridden when calling `.sign()`

    """

    def __init__(
        self,
        key: Jwk | Any,
        *,
        issuer: str | None = None,
        alg: str | None = None,
        default_lifetime: int = 60,
        default_leeway: int | None = None,
    ) -> None:
        self.issuer = issuer
        self.jwk = to_jwk(key)
        self.alg = alg
        self.default_lifetime = default_lifetime
        self.default_leeway = default_leeway

    def sign(
        self,
        *,
        subject: str | None = None,
        audience: str | Iterable[str] | None = None,
        extra_claims: Mapping[str, Any] | None = None,
        extra_headers: Mapping[str, Any] | None = None,
        lifetime: int | None = None,
        leeway: int | None = None,
    ) -> SignedJwt:
        """Sign a Jwt.

        Claim 'issuer' will have the value defined at initialization time. Claim `iat`, `nbf` and `exp` will reflect
        the current time when the token is signed. `exp` includes `lifetime` seconds in the future, and `nbf`
        includes `leeway` seconds in the past.

        Args:
          subject: the subject to include in claim `sub`. (Default value = None)
          audience: the audience identifier(s) to include in claim `aud`.
          extra_claims: additional claims to include in the signed token. (Default value = None)
          extra_headers: additional headers to include in the header part. (Default value = None)
          lifetime: lifetime, in seconds, to use for the `exp` claim. If None, use the default_lifetime defined at
            initialization time.
          leeway: leeway, in seconds, to use for the `nbf` claim. If None, use the default_leeway defined at
            initialization time.

        Returns:
          the resulting signed token.

        """
        now = Jwt.timestamp()
        lifetime = lifetime or self.default_lifetime
        exp = now + lifetime
        leeway = leeway or self.default_leeway
        nbf = (now - leeway) if leeway is not None else None
        jti = self.generate_jti()
        extra_claims = extra_claims or {}
        claims = {
            key: value
            for key, value in dict(
                extra_claims,
                iss=self.issuer,
                aud=audience,
                sub=subject,
                iat=now,
                exp=exp,
                nbf=nbf,
                jti=jti,
            ).items()
            if value is not None
        }
        return Jwt.sign(claims, key=self.jwk, alg=self.alg, extra_headers=extra_headers)

    def generate_jti(self) -> str:
        """Generate Jwt Token ID (jti) values.

        Default uses UUID4. Can be overridden in subclasses.

        Returns:
            A unique value suitable for use as JWT Token ID (jti) claim.

        """
        return str(uuid.uuid4())

    @classmethod
    def with_random_key(
        cls,
        *,
        issuer: str,
        alg: str,
        default_lifetime: int = 60,
        default_leeway: int | None = None,
        kid: str | None = None,
    ) -> JwtSigner:
        """Initialize a JwtSigner with a randomly generated key.

        Args:
            issuer: the issuer identifier
            alg: the signing alg to use
            default_lifetime: lifetime for generated tokens expiration date (`exp` claim)
            default_leeway: leeway for generated tokens not before date (`nbf` claim)
            kid: key id to use for the generated key

        Returns:
            a JwtSigner initialized with a random key

        """
        jwk = Jwk.generate_for_alg(alg, kid=kid).with_kid_thumbprint()
        return cls(issuer=issuer, key=jwk, alg=alg, default_lifetime=default_lifetime, default_leeway=default_leeway)

    def verifier(
        self,
        *,
        audience: str,
        verifiers: Iterable[Callable[[SignedJwt], None]] | None = None,
        **kwargs: Any,
    ) -> JwtVerifier:
        """Return the matching `JwtVerifier`, initialized with the public key."""
        return JwtVerifier(
            issuer=self.issuer,
            jwkset=self.jwk.public_jwk().as_jwks(),
            alg=self.alg,
            audience=audience,
            verifiers=verifiers,
            **kwargs,
        )
