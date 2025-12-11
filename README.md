# Freelancer Toolbox

A collection of tools and documentation for freelancers to manage invoicing, time tracking, accounting, and tax preparation.

## Getting Started

New to freelancing? Start here:

- **[Getting Started Guide](docs/getting-started.md)** - Set yourself up as a contractor (tax registration, insurance, banking)
- **[Country Guides](docs/countries/)** - Country-specific guidance for Germany, UK, Switzerland, and more

## Workflows

Step-by-step guides for common tasks:

- **[Monthly Invoicing](docs/workflows/monthly-invoicing.md)** - Export time tracking data and generate invoices
- **[Tax Preparation](docs/workflows/tax-preparation.md)** - Year-end tax calculation and document gathering

## Tools

### Time Tracking

| Tool | Description |
|------|-------------|
| **[harvest-exporter](harvest_exporter/README.md)** | Export timesheets from [Harvest](https://getharvest.com) with currency conversion |
| **[kimai-exporter](kimai_exporter/README.md)** | Export time entries from [Kimai](https://www.kimai.org) |

### Invoicing & Accounting

| Tool | Description |
|------|-------------|
| **[sevdesk-cli](sevdesk-cli/README.md)** | CLI for [SevDesk](https://sevdesk.com) - manage vouchers, tax rules, transactions |
| **[sevdesk-api](sevdesk-api/README.md)** | Python client library for SevDesk API |
| **[sevdesk-invoicer](sevdesk-invoicer/README.md)** | Generate SevDesk invoices, import Wise transactions, estimate taxes |
| **[quipu](quipu/README.md)** | Generate invoices in [Quipu](https://getquipu.com) |

### Banking

| Tool | Description |
|------|-------------|
| **[wise-exporter](wise-exporter/README.md)** | Download bank statements from [Wise](https://wise.com) |

### Document Management

| Tool | Description |
|------|-------------|
| **[paperless-cli](paperless-cli/README.md)** | CLI for [Paperless-ngx](https://docs.paperless-ngx.com) - document management |

## Quick Start

### Setup

```console
cp .envrc.local-template .envrc.local
# Edit .envrc.local with your API tokens
```

### Generate an Invoice

1. Export your time tracking data:

```console
harvest-exporter --format json > harvest.json
```

2. Generate the invoice:

```console
sevdesk-invoicer --customer "CUSTOMER_ID" harvest.json
```

See [Monthly Invoicing Workflow](docs/workflows/monthly-invoicing.md) for the complete guide.

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `HARVEST_ACCOUNT_ID` | Harvest account ID |
| `HARVEST_ACCESS_TOKEN` | Harvest API token ([get one here](https://id.getharvest.com/oauth2/access_tokens/new)) |
| `SEVDESK_API_TOKEN` | SevDesk API token |
| `WISE_API_TOKEN` | Wise API token |
| `WISE_PRIVATE_KEY` | Path to RSA private key for Wise 2FA |
| `WISE_PROFILE` | Wise business profile ID |
| `PAPERLESS_URL` | Paperless-ngx instance URL |
| `PAPERLESS_TOKEN` | Paperless API token |

## API References

- [Harvest API v2](https://help.getharvest.com/api-v2)
- [Wise API](https://api-docs.transferwise.com/)
- [SevDesk API](https://my.sevdesk.de/api/InvoiceAPI/doc.html)

## License

MIT
