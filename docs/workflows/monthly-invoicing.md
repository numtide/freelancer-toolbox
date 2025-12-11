# Monthly Invoicing Workflow

This guide walks through generating monthly invoices from time tracking data.

## Overview

```
Time Tracking (Harvest/Kimai)
         |
         v
    harvest-exporter / kimai-exporter
         |
         v
    JSON export file
         |
         v
    sevdesk-invoicer / quipu-invoicer
         |
         v
    Invoice in accounting system
```

## Prerequisites

### Environment Variables

Set up your credentials in `.envrc.local` (or export them directly):

```bash
# Harvest (time tracking)
export HARVEST_ACCOUNT_ID="your-account-id"
export HARVEST_ACCESS_TOKEN="your-access-token"

# SevDesk (invoicing/accounting)
export SEVDESK_API_TOKEN="your-api-token"

# Optional: Wise (for exchange rates)
export WISE_API_TOKEN="your-api-token"
```

### Get Your Harvest Token

Generate a personal access token at: <https://id.getharvest.com/oauth2/access_tokens/new>

## Step 1: Export Time Entries

### From Harvest

Export current month for all tracked time:

```console
harvest-exporter --format json > harvest-$(date +%Y-%m).json
```

Export a specific month (e.g., March):

```console
harvest-exporter --month 3 --format json > harvest-2024-03.json
```

Filter by user:

```console
harvest-exporter --user "Your Name" --format json > harvest.json
```

Filter by client:

```console
harvest-exporter --client "Client Name" --format json > harvest.json
```

Export in a different currency (applies exchange rate):

```console
harvest-exporter --currency CHF --format json > harvest.json
```

Override hourly rate:

```console
harvest-exporter --hourly-rate 100 --format json > harvest.json
```

### From Kimai

Export last month for a specific user and client:

```console
kimai-exporter --client "Client Name" --user "Your Name" > kimai.json
```

## Step 2: Review the Export

Before generating an invoice, review the JSON output:

```console
harvest-exporter  # Human-readable output
```

Check for:
- Correct hours per project
- Correct hourly rates
- Expected total amounts

## Step 3: Generate Invoice

### With SevDesk

Find your customer ID in SevDesk, then generate the invoice:

```console
sevdesk-invoicer --customer "1000" harvest.json
```

The invoice will be created as a draft in SevDesk. Review and finalize it in the SevDesk web interface.

### With Quipu

```console
quipu-invoicer harvest.json
```

## Step 4: Import Bank Statements (Optional)

If using Wise, import transactions into SevDesk for matching:

1. Download CSV from Wise Transactions tab
2. Get account IBANs for each currency
3. Run the importer:

```console
sevdesk-wise-importer \
  --add-account "BE00 0000 0000 0000" "EUR" \
  --add-account 8000000000 USD \
  --import-state wise-import-state.json \
  transaction-history.csv
```

The `--import-state` flag tracks which transactions have been imported to avoid duplicates.

## Automation Tips

### Monthly Cron Job

Create a script for your monthly workflow:

```bash
#!/usr/bin/env bash
set -euo pipefail

month=$(date -d "last month" +%m)
year=$(date -d "last month" +%Y)

harvest-exporter --month "$month" --format json > "harvest-${year}-${month}.json"
echo "Exported harvest data to harvest-${year}-${month}.json"
echo "Review and run: sevdesk-invoicer --customer YOUR_ID harvest-${year}-${month}.json"
```

---

[Back to Documentation](../) | [Tax Preparation Workflow](./tax-preparation.md)
