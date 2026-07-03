# sevdesk-invoicer

SevDesk integration tools for invoice generation, bank imports, and tax estimation.

This package contains three tools:
- **sevdesk-invoicer** - Generate invoices from time tracking exports
- **sevdesk-wise-importer** - Import Wise bank transactions
- **sevdesk-tax-estimator** - Calculate remaining tax payments (Germany)

## Installation

```console
nix shell github:numtide/freelancer-toolbox#sevdesk-invoicer
```

## Configuration

| Variable | Description |
|----------|-------------|
| `SEVDESK_API_TOKEN` | API token from [SevDesk User Management](https://my.sevdesk.de/#/admin/userManagement) |

---

## sevdesk-invoicer

Generate SevDesk invoices from harvest-exporter or kimai-exporter JSON output.

### Usage

```console
# Generate invoice for customer ID 1234
sevdesk-invoicer --customer "1234" harvest.json

# With custom payment terms
sevdesk-invoicer --customer "1234" --days-until-payment 14 harvest.json

# Specify payment method
sevdesk-invoicer --customer "1234" --payment-method 5678 harvest.json
```

### Options

| Option | Description |
|--------|-------------|
| `--customer ID` | SevDesk customer ID (find in contacts) |
| `--payment-method ID` | Payment method ID (from SevDesk) |
| `--days-until-payment N` | Days until payment due (default: 30) |

### Input Format

Expects JSON array from harvest-exporter or kimai-exporter:

```json
[
  {
    "client": "Acme Corp",
    "task": "Development",
    "rounded_hours": 40.5,
    "target_currency": "EUR",
    "target_hourly_rate": 100,
    "target_cost": 4050,
    "start_date": "20240101",
    "end_date": "20240131",
    "agency": "numtide"
  }
]
```

### Output

Creates a draft invoice in SevDesk and prints the URL:

```
Invoice created successfully: https://my.sevdesk.de/fi/detail/type/RE/id/12345
```

---

## sevdesk-wise-importer

Import Wise bank transactions into SevDesk check accounts.

### Setup

1. Download transaction CSV from Wise (Transactions tab)
2. Note your account IBAN/number for each currency

### Usage

```console
# Import EUR and USD accounts
sevdesk-wise-importer \
  --add-account "BE00 0000 0000 0000" EUR \
  --add-account 8000000000 USD \
  --import-state wise-import-state.json \
  transaction-history.csv
```

### Options

| Option | Description |
|--------|-------------|
| `--add-account IBAN CURRENCY` | Map account number to currency |
| `--import-state FILE` | Track imported transactions (prevents duplicates) |
| `--ignore-currency CODE` | Skip transactions in this currency |
| `--import-neutral SRC TGT` | Import neutral (exchange) transactions |
| `--dry-run` | Preview without importing |

### Dry Run

Preview what would be imported:

```console
sevdesk-wise-importer --dry-run \
  --add-account "BE00 0000 0000 0000" EUR \
  transaction-history.csv
```

---

## sevdesk-tax-estimator

Calculate remaining tax payments for German freelancers.

### Prerequisites

- Monthly harvest export files in a folder
- Wise statement exports in a folder

### Usage

```console
sevdesk-tax-estimator \
  --harvest-folder harvest/2024 \
  --wise-folder statements/2024 \
  --tax-office-name "Finanzamt Berlin Finanzkasse"
```

### Options

| Option | Description |
|--------|-------------|
| `--harvest-folder PATH` | Folder with monthly harvest JSON exports |
| `--wise-folder PATH` | Folder with Wise statement JSON files |
| `--tax-office-name NAME` | Tax office name as it appears in Wise |
| `--calculated-tax AMOUNT` | Pre-calculated tax (skip interactive prompt) |
| `--estimated-expenses AMOUNT` | Expenses from SevDesk (skip interactive prompt) |

### Interactive Mode

If not all options are provided, the tool prompts for:
1. Total expenses from SevDesk
2. Calculated tax from [BMF Tax Calculator](https://www.bmf-steuerrechner.de/)

### Output

```
Revenue:            | 75000.00
Expenses:           | 15000.00
Net income:         | 60000.00
Payed taxes:        | 12000.00
Calculated taxes:   | 18000.00
--------------------|----------
Taxes left to pay:  | 6000.00
```

---

## See Also

- [sevdesk-cli](../sevdesk-cli/) - CLI for SevDesk operations
- [sevdesk-api](../sevdesk-api/) - Python API client
- [harvest-exporter](../harvest_exporter/) - Export Harvest timesheets
- [wise-exporter](../wise-exporter/) - Export Wise statements
- [Monthly Invoicing Workflow](../docs/workflows/monthly-invoicing.md)
- [Tax Preparation Workflow](../docs/workflows/tax-preparation.md)
