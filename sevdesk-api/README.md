# sevDesk API Python Client

A Python client library for interacting with the sevDesk API.

## Installation

```bash
pip install sevdesk-api
```

## Usage

```python
from sevdesk_api import SevDeskAPI

# Initialize the API client
api = SevDeskAPI(api_token="your-api-token")

# Check connection
if api.check_connection():
    print("Connected to sevDesk!")

# Get vouchers
vouchers = api.vouchers.get_vouchers(status=1000)  # Get paid vouchers

# Download a voucher document
if vouchers["objects"]:
    voucher = vouchers["objects"][0]
    if voucher.get("document"):
        document_id = voucher["document"]["id"]
        download = api.vouchers.download_voucher_document(document_id)
        
        # Save to file
        with open(download.filename, "wb") as f:
            f.write(download.content)
```

## Features

- Support for contacts, invoices, vouchers, and transactions
- Document download support
