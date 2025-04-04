"""This module implements Json Web Encryption as described in [RFC7516].

[RFC7516]
: https: //www.rfc-editor.org/rfc/rfc7516

"""

from __future__ import annotations

from .compact import InvalidJwe, JweCompact

__all__ = ["InvalidJwe", "JweCompact"]
