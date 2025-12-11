# wise-exporter

Download bank statements from [Wise](https://wise.com) (formerly TransferWise) with 2FA support.

## Installation

```console
nix shell github:numtide/freelancer-toolbox#wise-exporter
```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `WISE_API_TOKEN` | API token from [Wise Settings](https://wise.com/settings/) |
| `WISE_PRIVATE_KEY` | Path to RSA private key for 2FA signing |
| `WISE_PROFILE` | (Optional) Business profile ID |

### Setting Up 2FA Key

Wise requires 2FA for API access. Generate a key pair:

```console
openssl genrsa -out private.pem 2048
ssh-keygen -p -m PEM -f private.pem -N ""
openssl rsa -pubout -in private.pem -out public.pem
```

Upload `public.pem` to Wise:
1. Go to [Wise Settings](https://wise.com/settings/)
2. Find "API tokens" section
3. Click "Manage public keys"
4. Upload your public key

Set the private key path:

```console
export WISE_PRIVATE_KEY="$(cat private.pem)"
```

## Usage

### Basic Export

Export the previous month (default):

```console
wise-exporter
```

### Date Filtering

Export a specific month:

```console
wise-exporter --month 3
wise-exporter --month 6 --year 2024
```

Export date range:

```console
wise-exporter --start 20240101 --end 20240131
```

### Profile Selection

If you have multiple business profiles:

```console
wise-exporter --wise-profile 12345678
```

## Output

JSON output with statements for each currency balance:

```json
[
  {
    "accountHolder": {
      "type": "BUSINESS",
      "businessName": "My Company"
    },
    "issuer": {
      "name": "Wise",
      "firstLine": "56 Shoreditch High Street",
      "city": "London"
    },
    "transactions": [
      {
        "type": "CREDIT",
        "date": "2024-01-15T10:30:00.000Z",
        "amount": {"value": 1000.00, "currency": "EUR"},
        "details": {
          "type": "MONEY_ADDED",
          "description": "Invoice payment from Acme Corp"
        },
        "runningBalance": {"value": 5000.00, "currency": "EUR"}
      }
    ],
    "startOfStatementBalance": {"value": 4000.00, "currency": "EUR"},
    "endOfStatementBalance": {"value": 5000.00, "currency": "EUR"}
  }
]
```

## Integration

### Import to SevDesk

Use with [sevdesk-wise-importer](../sevdesk-invoicer/):

```console
# Download CSV from Wise Transactions tab, then:
sevdesk-wise-importer \
  --add-account "BE00 0000 0000 0000" EUR \
  --import-state wise-import-state.json \
  transaction-history.csv
```

### Tax Estimation

Use with [sevdesk-tax-estimator](../sevdesk-invoicer/):

```console
mkdir -p statements/2024
wise-exporter --year 2024 > statements/2024/wise.json

sevdesk-tax-estimator \
  --harvest-folder harvest/2024 \
  --wise-folder statements/2024 \
  --tax-office-name "Finanzamt Berlin"
```

See also:
- [sevdesk-invoicer](../sevdesk-invoicer/) - SevDesk integration tools
- [Tax Preparation Workflow](../docs/workflows/tax-preparation.md)
