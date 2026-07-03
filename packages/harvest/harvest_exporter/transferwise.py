#!/usr/bin/env python3

import functools
from fractions import Fraction

from rest import http_request


@functools.cache
def exchange_rate(source: str, target: str) -> Fraction:
    data = dict(sourceCurrency=source, targetCurrency=target)
    resp = http_request(
        "https://api.transferwise.com/v3/quotes/",
        method="POST",
        data=data,
        headers={"Content-type": "application/json"},
    )
    return Fraction(resp["rate"])
