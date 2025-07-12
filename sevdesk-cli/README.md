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

### Tax Rules

#### List Tax Rules

```bash
# List all available tax rules
sevdesk tax-rules list
```

This displays:
- Tax rule ID
- Tax rule code (e.g., VORST_ABZUGSF_AUFW)
- Tax rule name/description
- Usage hints for common scenarios

### Accounting Types (Booking Accounts)

#### List Accounting Types

```bash
# List all accounting types
sevdesk accounting-types list

# With pagination
sevdesk accounting-types list --limit 20 --offset 0
```

This displays:
- Account ID and number
- Account name and description
- Type (Debit/Expense or Credit/Income)
- SKR number (if available)
- Status (Active/Inactive)

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

Create a voucher with positions using key=value format:

```bash
# Minimal syntax with defaults (qty=1, tax=19, asset=false, tax-type=eu)
sevdesk vouchers create \
    --credit-debit D \
    --voucher-type VOU \
    --status DRAFT \
    --description "Office supplies invoice" \
    --supplier-name "Office Depot" \
    --position "name='Printer Paper' price=10.00 skr=6815" \
    --position "name='USB Cable' price=15.00 skr=6815"

# With explicit tax rule for deductible expenses
sevdesk vouchers create \
    --credit-debit D \
    --voucher-type VOU \
    --status DRAFT \
    --tax-rule VORST_ABZUGSF_AUFW \
    --description "Office supplies invoice" \
    --supplier-name "Office Depot" \
    --position "name='Printer Paper' price=10.00 skr=6815" \
    --position "name='USB Cable' price=15.00 skr=6815"

# Full syntax with all parameters
sevdesk vouchers create \
    --credit-debit D \
    --tax-rule VORST_ABZUGSF_AUFW \
    --voucher-type VOU \
    --status DRAFT \
    --description "Mixed purchase invoice" \
    --supplier-name "Tech Store" \
    --position "name='Office supplies' qty=5 price=10.00 tax=19 skr=6815 asset=false" \
    --position "name='Laptop' qty=1 price=1200.00 tax=19 skr=0670 asset=true" \
    --position "name='Software License' price=99.00 tax=19 skr=5880 text='1 year subscription'"
```

Position parameters:
- **Required**: `name`, `price`, `skr` (SKR account number)
- **Optional**: 
  - `qty` or `quantity` (default: 1)
  - `tax` or `tax_rate` (default: 19)
  - `asset` or `is_asset` (default: false)
  - `text` (additional description)
  - `net` (whether price is net or gross, default: true)
- You can find available SKR numbers using: `sevdesk accounting-types list`

Or using a JSON file for positions:

```bash
# positions.json
[
    {
        "name": "Printer Paper",
        "quantity": 5,
        "price": 10.00,
        "tax_rate": 19,
        "net": true,
        "accounting_type_skr": "5400",
        "is_asset": false
    },
    {
        "name": "Ink Cartridge",
        "quantity": 2,
        "price": 25.00,
        "tax_rate": 19,
        "net": true,
        "accounting_type_skr": "5400",
        "is_asset": false
    }
]

sevdesk vouchers create \
    --credit-debit D \
    --voucher-type VOU \
    --status DRAFT \
    --description "Office supplies invoice" \
    --supplier-name "Office Depot" \
    --positions-json positions.json
```

### Update Voucher

```bash
# Update an existing voucher
sevdesk vouchers update 12345 \
    --description "Updated description" \
    --voucher-date 2024-01-20 \
    --pay-date 2024-02-20 \
    --supplier-name "New Supplier Name"
```

Note: Status updates are not supported via the update command. Use the Factory/saveVoucher endpoint for status changes.

### Book Voucher (Mark as Paid)

To mark a voucher as paid, you need to book it with a check account transaction. **Important: The voucher must be in UNPAID status (not DRAFT) before it can be booked.**

```bash
# First, ensure the voucher is in UNPAID status
# If creating a new voucher, use --status UNPAID instead of DRAFT
# For existing DRAFT vouchers, you need to update them first

# Create a transaction for the payment
sevdesk transactions create \
    --check-account-id 12345 \
    --value-date 2025-07-12 \
    --amount -451.00 \
    --payee-payer-name "Office World GmbH" \
    --paymt-purpose "Payment for invoice #119608101"

# Then book the voucher with the transaction
sevdesk vouchers book 119608101 67890

# Or specify a partial amount
sevdesk vouchers book 119608101 67890 --amount 200.00
```

This links the payment transaction to the voucher and changes its status to PAID.

**Note**: Due to SevDesk API restrictions:
- Vouchers can only be created with status DRAFT (50) or UNPAID (100)
- Vouchers cannot be directly set to PAID status
- A voucher must be in UNPAID status before it can be booked with a transaction

### Unbook Voucher (Reset to Unpaid)

To unbook a voucher that has been paid, resetting it back to unpaid status:

```bash
# This will unlink any payments and reset status to UNPAID (100)
sevdesk vouchers unbook 119608101
```

### Reset Voucher Status

To reset a voucher to a different status:

```bash
# Reset to draft status (from UNPAID or PAID)
sevdesk vouchers reset 119608101 draft

# Reset to open/unpaid status (from PAID only)
sevdesk vouchers reset 119608101 open
```

**Note about status changes**:
- `reset draft`: Can be used on UNPAID (100) or PAID (1000) vouchers
- `reset open`: Can only be used on PAID (1000) vouchers
- To change from DRAFT to UNPAID, create/update the voucher with `--status UNPAID`

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
    --entry-date 2024-01-15 \
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

### Link Transaction

```bash
# Link a transaction to a voucher
sevdesk transactions link 67890 12345

# Link a transaction to an invoice
sevdesk transactions link 67890 54321 --type invoice
```

### Unlink Transaction

```bash
# Unlink a transaction from any linked documents
sevdesk transactions unlink 67890
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
