# kimai-exporter

Export time entries from [Kimai](https://www.kimai.org) with currency conversion.

## Installation

```console
nix shell github:numtide/freelancer-toolbox#kimai-exporter
```

## Configuration

Set the following environment variables (or use CLI flags):

| Variable | Description |
|----------|-------------|
| `KIMAI_API_URL` | Your Kimai instance API URL |
| `KIMAI_API_KEY` | API key from your Kimai account |
| `KIMAI_USER` | Username or alias to filter by |

## Usage

### Basic Export

Export the previous month for a specific client:

```console
kimai-exporter --client "Acme Corp" --user "jane.doe"
```

### Date Filtering

Export a specific month:

```console
kimai-exporter --client "Acme Corp" --month 3
kimai-exporter --client "Acme Corp" --month 6 --year 2024
```

Export date range:

```console
kimai-exporter --client "Acme Corp" --start 2024-01-01 --end 2024-01-31
```

### Currency Conversion

Convert to a different currency:

```console
kimai-exporter --client "Acme Corp" --currency CHF
```

### Agency Mode

Specify an agency name for the export:

```console
kimai-exporter --client "Acme Corp" --agency "My Agency"
```

## Output

JSON output with entries containing:

```json
{
  "user": "jane.doe",
  "client": "Acme Corp",
  "task": "Development, Code Review",
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
  "agency": null
}
```

## Integration

Pipe JSON output to invoice generators:

```console
kimai-exporter --client "Acme Corp" > kimai.json
sevdesk-invoicer --customer "1234" kimai.json
```

See also:
- [sevdesk-invoicer](../sevdesk-invoicer/) - Generate SevDesk invoices
- [quipu](../quipu/) - Generate Quipu invoices
- [Monthly Invoicing Workflow](../docs/workflows/monthly-invoicing.md)
