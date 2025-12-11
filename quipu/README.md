# quipu

[Quipu](https://getquipu.com) integration for invoice generation.

This package contains:
- **quipu_api** - Python client library for the Quipu API
- **quipu-invoicer** - Generate invoices from time tracking exports

## Installation

```console
nix shell github:numtide/freelancer-toolbox#quipu-invoicer
```

## Configuration

| Variable | Description |
|----------|-------------|
| `QUIPU_APP_ID` | Quipu OAuth application ID |
| `QUIPU_APP_SECRET` | Quipu OAuth application secret |

---

## quipu-invoicer

Generate Quipu invoices from harvest-exporter or kimai-exporter JSON output.

### Usage

```console
# Generate invoice for customer
quipu-invoicer harvest.json

# With custom options
quipu-invoicer \
  --customer 5458533 \
  --invoice-number "2024-001" \
  --issue-date 2024-01-31 \
  --due-date 2024-02-28 \
  harvest.json
```

### Options

| Option | Description |
|--------|-------------|
| `--customer ID` | Quipu customer ID |
| `--invoice-number STR` | Invoice number |
| `--accounting-category ID` | Accounting category ID (default: 133) |
| `--vat-percent N` | VAT percentage (default: 0) |
| `--issue-date DATE` | Issue date (YYYY-MM-DD) |
| `--due-date DATE` | Due date (YYYY-MM-DD) |
| `--notes TEXT` | Invoice notes |

### Input Format

Expects JSON array from harvest-exporter or kimai-exporter:

```json
[
  {
    "client": "Acme Corp",
    "task": "Development",
    "rounded_hours": 40.5,
    "target_hourly_rate": 100
  }
]
```

---

## quipu_api

Python client library for the Quipu API.

### Usage

```python
from quipu_api import QuipuAPI

api = QuipuAPI(app_id="...", app_secret="...")

# Create invoice
invoice_data = {
    "data": {
        "type": "invoices",
        "attributes": {
            "kind": "income",
            "number": "2024-001",
            "issue_date": "2024-01-31",
            "due_date": "2024-02-28",
            "payment_method": "bank_transfer"
        },
        "relationships": {
            "contact": {"data": {"id": 123, "type": "contacts"}},
            "items": {"data": [...]}
        }
    }
}
api.create_invoice(invoice_data)
```

---

## See Also

- [harvest-exporter](../harvest_exporter/) - Export Harvest timesheets
- [kimai-exporter](../kimai_exporter/) - Export Kimai time entries
- [Monthly Invoicing Workflow](../docs/workflows/monthly-invoicing.md)
