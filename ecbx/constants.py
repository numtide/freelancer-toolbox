"""Constants for ECB exchange rate operations."""

# ECB API URLs
ECB_URL_90D = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
ECB_URL_HIST = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"

# XML namespace
ECB_NAMESPACE = {"ns": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}

# Direction constants for closest rate
BEFORE = "before"
AFTER = "after"
CLOSEST = "closest"

# Default values
DEFAULT_AMOUNT = 25.0
DEFAULT_BASE_CURRENCY = "EUR"
