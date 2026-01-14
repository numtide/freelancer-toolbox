"""ECB Exchange Rate Tools."""

from .cli import cli
from .store import ExchangeRateStore

__all__ = ["ExchangeRateStore", "cli"]

__version__ = "0.1.0"
