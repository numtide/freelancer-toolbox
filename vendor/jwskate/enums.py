"""This module contains enums for the various identifiers used in JWA and JWK.

See [IANA JOSE](https://www.iana.org/assignments/jose/jose.xhtml).

"""

from __future__ import annotations


class SignatureAlgs:
    """Identifiers for Signature algorithms."""

    RS256 = "RS256"
    RS384 = "RS384"
    RS512 = "RS512"
    ES256 = "ES256"
    ES256k = "ES256k"
    ES384 = "ES384"
    ES512 = "ES512"
    PS256 = "PS256"
    PS384 = "PS384"
    PS512 = "PS512"
    EdDSA = "EdDSA"

    HS256 = "HS256"
    HS384 = "HS384"
    HS512 = "HS512"

    ALL_SYMMETRIC = {HS256, HS384, HS512}
    ALL_ASYMMETRIC = {
        RS256,
        RS384,
        RS512,
        ES256,
        ES256k,
        ES384,
        ES512,
        PS256,
        PS384,
        PS512,
        EdDSA,
    }
    ALL = ALL_ASYMMETRIC | ALL_SYMMETRIC


class EncryptionAlgs:
    """Identifiers for Encryption algorithms."""

    A128CBC_HS256 = "A128CBC-HS256"
    A192CBC_HS384 = "A192CBC-HS384"
    A256CBC_HS512 = "A256CBC-HS512"
    A128GCM = "A128GCM"
    A192GCM = "A192GCM"
    A256GCM = "A256GCM"

    ALL_AESCBC_HMAC = {A128CBC_HS256, A192CBC_HS384, A256CBC_HS512}
    ALL_AESGCM = {A128GCM, A192GCM, A256GCM}

    ALL = ALL_AESGCM | ALL_AESCBC_HMAC


class KeyManagementAlgs:
    """Identifiers for Key Management algorithms."""

    RSA1_5 = "RSA1_5"
    RSA_OAEP = "RSA-OAEP"
    RSA_OAEP_256 = "RSA-OAEP-256"
    RSA_OAEP_384 = "RSA-OAEP-384"
    RSA_OAEP_512 = "RSA-OAEP-512"
    ECDH_ES = "ECDH-ES"
    ECDH_ES_A128KW = "ECDH-ES+A128KW"
    ECDH_ES_A192KW = "ECDH-ES+A192KW"
    ECDH_ES_A256KW = "ECDH-ES+A256KW"

    A128KW = "A128KW"
    A192KW = "A192KW"
    A256KW = "A256KW"
    A128GCMKW = "A128GCMKW"
    A192GCMKW = "A192GCMKW"
    A256GCMKW = "A256GCMKW"
    dir = "dir"

    PBES2_HS256_A128KW = "PBES2-HS256+A128KW"
    PBES2_HS384_A192KW = "PBES2-HS384+A192KW"
    PBES2_HS512_A256KW = "PBES2-HS512+A256KW"

    ALL_AES = {A128KW, A192KW, A256KW}
    ALL_AESGCM = {A128GCMKW, A192GCMKW, A256GCMKW}
    ALL_SYMMETRIC = {
        A128KW,
        A192KW,
        A256KW,
        A128GCMKW,
        A192GCMKW,
        A256GCMKW,
        dir,
    }
    ALL_ASYMMETRIC = {
        RSA1_5,
        RSA_OAEP,
        RSA_OAEP_256,
        RSA_OAEP_384,
        RSA_OAEP_512,
        ECDH_ES,
        ECDH_ES_A128KW,
        ECDH_ES_A192KW,
        ECDH_ES_A256KW,
    }
    ALL_PASSWORD_BASED = {
        PBES2_HS256_A128KW,
        PBES2_HS384_A192KW,
        PBES2_HS512_A256KW,
    }
    ALL_KEY_BASED = ALL_ASYMMETRIC | ALL_SYMMETRIC
    ALL = ALL_ASYMMETRIC | ALL_SYMMETRIC | ALL_PASSWORD_BASED


class KeyTypes:
    """Identifiers for Key Types (kty)."""

    OCT = "oct"
    RSA = "RSA"
    EC = "EC"
    OKP = "OKP"
