# harvest-exporter

Export timesheets from [Harvest](https://getharvest.com) with currency conversion via Wise exchange rates.

## Installation

```console
nix shell github:numtide/freelancer-toolbox#harvest-exporter
```

## Configuration

Set the following environment variables (or use CLI flags):

| Variable | Description |
|----------|-------------|
| `HARVEST_ACCOUNT_ID` | Your Harvest account ID |
| `HARVEST_BEARER_TOKEN` | API token from [Harvest Developers](https://id.getharvest.com/developers) |
| `HARVEST_USER` | (Optional) Filter by user name |

## Usage

### Basic Export

Export the previous month (default):

```console
harvest-exporter
```

### Date Filtering

Export specific months:

```console
harvest-exporter --months 3           # March of current year
harvest-exporter --months 1 2 3       # Q1
harvest-exporter --months 6 --year 2024
```

Export date range:

```console
harvest-exporter --start 20240101 --end 20240131
```

### User Filtering

```console
harvest-exporter --user "Jane Doe"    # Specific user
harvest-exporter --all-users          # All users (not just authenticated user)
```

### Client Filtering

```console
harvest-exporter --client "Acme Corp"
```

### Currency Conversion

Convert to a different currency (applies Wise exchange rate):

```console
harvest-exporter --currency CHF
harvest-exporter --currency USD
```

### Hourly Rate Override

Override the rate from Harvest:

```console
harvest-exporter --hourly-rate 100
```

### Output Formats

```console
harvest-exporter --format humanreadable  # Default, human-readable text
harvest-exporter --format json           # JSON for piping to other tools
harvest-exporter --format csv            # CSV format
harvest-exporter --format table          # Rich table format
```

### Agency Mode

By default, a numtide agency rate (75%) is applied. To disable:

```console
harvest-exporter --agency none --client "Direct Client"
```

## Output

JSON output contains entries with:

```json
{
  "user": "Jane Doe",
  "client": "Acme Corp",
  "task": "Development",
  "rounded_hours": 40.5,
  "source_currency": "USD",
  "source_hourly_rate": 100,
  "source_cost": 4050,
  "target_currency": "EUR",
  "target_hourly_rate": 92.5,
  "target_cost": 3746.25,
  "exchange_rate": 0.925,
  "start_date": "20240101",
  "end_date": "20240131",
  "agency": "numtide"
}
```

## Integration

Pipe JSON output to invoice generators:

```console
harvest-exporter --format json > harvest.json
sevdesk-invoicer --customer "1234" harvest.json
```

See also:
- [sevdesk-invoicer](../sevdesk-invoicer/) - Generate SevDesk invoices
- [quipu](../quipu/) - Generate Quipu invoices
- [Monthly Invoicing Workflow](../docs/workflows/monthly-invoicing.md)
