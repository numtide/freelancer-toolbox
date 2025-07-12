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

## Check Accounts

### List Check Accounts

```bash
# List all check accounts
sevdesk check-accounts list

# With pagination
sevdesk check-accounts list --limit 10 --offset 0
```

### Get Check Account Details

```bash
# Get details for a specific check account
sevdesk check-accounts get 12345
```

This displays:
- Basic account information (name, type, status)
- Current balance and currency
- Bank details (IBAN, bank server)
- Import settings
- Creation and update dates

### Create File Import Account

```bash
# Create a file import account for bank statement imports
sevdesk check-accounts create-import \
    --name "Business Bank Account" \
    --import-type CSV \
    --iban "DE89370400440532013000" \
    --accounting-number "1200"
```

### Create Clearing Account

```bash
# Create a clearing account
sevdesk check-accounts create-clearing \
    --name "PayPal Clearing Account" \
    --accounting-number "1360"
```

### Get Account Balance

```bash
# Get current balance for a check account
sevdesk check-accounts balance 12345
```

## Transactions

### List Transactions

```bash
# List all transactions
sevdesk transactions list

# List transactions for a specific check account
sevdesk transactions list --check-account-id 12345

# Filter by status (CREATED, LINKED, PRIVATE, AUTO_BOOKED, BOOKED)
sevdesk transactions list --status BOOKED

# Filter by date range
sevdesk transactions list --start-date 2024-01-01 --end-date 2024-01-31

# With pagination
sevdesk transactions list --limit 50 --offset 0
```

### Get Transaction Details

```bash
# Get details for a specific transaction
sevdesk transactions get 67890
```

This displays:
- Transaction dates (value date, entry date)
- Amount (with income/expense indicator)
- Status
- Payee/payer information (name, IBAN, BIC)
- Purpose and entry text
- Associated check account
- Enshrined status
- Linked documents

### Create Transaction

```bash
# Create a new transaction
sevdesk transactions create \
    --check-account-id 12345 \
    --value-date 2024-01-15 \
    --amount -150.50 \
    --status CREATED \
    --payee-payer-name "Office Supplies Ltd" \
    --paymt-purpose "Office supplies January" \
    --payee-payer-acct-no "DE89370400440532013001" \
    --payee-payer-bank-code "COBADEFF"
```

### Update Transaction

```bash
# Update an existing transaction
sevdesk transactions update 67890 \
    --amount -175.00 \
    --paymt-purpose "Office supplies January - corrected amount"
```

### Delete Transaction

```bash
# Delete a transaction
sevdesk transactions delete 67890
```

### Enshrine Transaction

```bash
# Enshrine (finalize) a transaction
sevdesk transactions enshrine 67890
```

## Development

Format code:

```bash
ruff format .
```

Check code:

```bash
ruff check .
mypy .
```
