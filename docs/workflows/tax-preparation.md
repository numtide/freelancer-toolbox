# Tax Preparation Workflow

This guide covers year-end tax preparation for German freelancers using SevDesk.

See also: [Germany Country Guide](../countries/germany.md)

## Overview

```
Harvest exports (all months)     Wise bank statements
         |                              |
         v                              v
    harvest folder/              wise-exporter
         |                              |
         +-------+          +-----------+
                 |          |
                 v          v
           sevdesk-tax-estimator
                    |
                    v
            Tax liability estimate
```

## Prerequisites

### Environment Variables

```bash
# SevDesk
export SEVDESK_API_TOKEN="your-api-token"

# Wise (for bank statement export)
export WISE_API_TOKEN="your-api-token"
export WISE_PRIVATE_KEY="path/to/private-key.pem"  # For 2FA
export WISE_PROFILE="your-profile-id"
```

## Step 1: Gather Harvest Exports

Throughout the year, save your monthly Harvest exports:

```console
mkdir -p harvest/2024

# Export each month
for month in {1..12}; do
  harvest-exporter --month $month --format json > harvest/2024/harvest-$month.json
done
```

Or if you've been saving them monthly, ensure they're organized:

```
harvest/
└── 2024/
    ├── harvest-1.json
    ├── harvest-2.json
    ├── ...
    └── harvest-12.json
```

## Step 2: Export Wise Statements

Download bank statements for the tax year:

```console
mkdir -p statements/2024

# Export for the full year
wise-exporter --year 2024 > statements/2024/wise-statements.json
```

Or export month by month:

```console
for month in {1..12}; do
  wise-exporter --month $month --year 2024 > statements/2024/wise-$month.json
done
```

## Step 3: Calculate Tax Estimate

The tax estimator aggregates:
- Revenue from Harvest exports
- Tax payments already made (from Wise statements)
- Expenses from SevDesk

Run the estimator:

```console
sevdesk-tax-estimator \
  --tax-office-name 'Finanzamt Berlin Finanzkasse' \
  --harvest-folder harvest/2024 \
  --wise-folder statements/2024
```

Output shows:
- Total revenue for the year
- Pre-tax payments already made (Vorauszahlungen)
- Estimated remaining tax liability

## Step 4: Calculate Working Days

For German income tax, you can claim deductions per working day. Generate this from Harvest:

1. Export your time report from [Harvest Reports](https://app.harvestapp.com/reports)
2. Run the calculator:

```console
working-days-calculator report.csv
```

Output:

```
Working days: 171 from 2024-01-12 00:00:00 to 2024-12-29 00:00:00
```

Use this number for your "Entfernungspauschale" (commuting allowance) or home office deduction.

## Year-End Checklist

### Documents to Gather

- [ ] All monthly Harvest/Kimai exports
- [ ] Bank statements (Wise, business account)
- [ ] Expense receipts (stored in Paperless or SevDesk)
- [ ] Health insurance payment confirmations
- [ ] Pension/retirement contribution confirmations
- [ ] Professional liability insurance receipts
- [ ] Office/equipment purchases

### SevDesk Tasks

- [ ] All invoices marked as paid
- [ ] All expenses categorized
- [ ] Bank transactions matched
- [ ] VAT reports submitted (quarterly)

### Tax Filing

- [ ] EÜR (Einnahmen-Überschuss-Rechnung) prepared
- [ ] Umsatzsteuererklärung (annual VAT declaration)
- [ ] Einkommensteuererklärung (income tax return)

## Document Management with Paperless

Keep tax documents organized using the [paperless-cli](../../paperless-cli/):

```console
# Search for all 2024 invoices
paperless-cli documents search "invoice 2024"

# Download specific documents
paperless-cli documents download 123 --output invoice.pdf

# Tag documents for tax year
paperless-cli documents update 123 --tags "tax-2024,expense"
```

---

[Back to Documentation](../) | [Monthly Invoicing Workflow](./monthly-invoicing.md)
