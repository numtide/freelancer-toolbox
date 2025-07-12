# SevDesk CLI

Command-line interface for the SevDesk API.

## Installation

```bash
pip install -e .
```

## Configuration

You can configure the CLI using environment variables, command-line arguments, or a config file.

### Environment Variables

- `SEVDESK_URL`: The SevDesk API URL (default: https://my.sevdesk.de/api/v1/)
- `SEVDESK_API_TOKEN`: Your SevDesk API token

### Config File

Create a config file at `~/.config/sevdesk-cli/config.json`:

```json
{
    "url": "https://my.sevdesk.de/api/v1/",
    "token_command": "pass show sevdesk/api-token"
}
```

## Usage

### List Vouchers

```bash
# List all vouchers
sevdesk vouchers list

# List only unpaid vouchers
sevdesk vouchers list --status 100

# List vouchers within a date range
sevdesk vouchers list --start-date 2024-01-01 --end-date 2024-01-31

# Limit results
sevdesk vouchers list --limit 10 --offset 0
```

### Get Voucher Details

```bash
sevdesk vouchers get 12345
```

This displays:
- Basic voucher information (description, type, status, dates)
- Financial information (net, tax, gross amounts)
- Supplier information (if available)
- All positions with their names, account/category IDs, and amounts

### Create Voucher

Create a voucher with positions using command line arguments:

```bash
sevdesk vouchers create \
    --credit-debit D \
    --tax-type default \
    --voucher-type VOU \
    --status DRAFT \
    --description "Office supplies invoice" \
    --supplier-name "Office Depot" \
    --position "Printer Paper" 5 10.00 19 \
    --position "Ink Cartridge" 2 25.00 19 \
    --position "USB Cable" 1 15.00 19
```

Or using a JSON file for positions:

```bash
# positions.json
[
    {
        "name": "Printer Paper",
        "quantity": 5,
        "price": 10.00,
        "tax_rate": 19,
        "net": true
    },
    {
        "name": "Ink Cartridge",
        "quantity": 2,
        "price": 25.00,
        "tax_rate": 19,
        "net": true
    }
]

sevdesk vouchers create \
    --credit-debit D \
    --tax-type default \
    --voucher-type VOU \
    --status DRAFT \
    --description "Office supplies invoice" \
    --supplier-name "Office Depot" \
    --positions-json positions.json
```


## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Format code:

```bash
ruff format .
```

Check code:

```bash
ruff check .
mypy .
```