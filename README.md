<img alt="freelancer-toolbox" src="https://banner.numtide.com/banner/numtide/freelancer-toolbox.svg">

A collection of CLI tools for freelancers: time tracking exports, invoice generation, bank statement imports, tax estimation, and document management.

## Available Tools

### Time Tracking

<details>
<summary><strong>harvest-exporter</strong> - Export timesheets from Harvest with currency conversion via Wise exchange rates</summary>

- **Homepage**: https://getharvest.com
- **Usage**: `nix run github:numtide/freelancer-toolbox#harvest-exporter -- --help`
- **Nix**: [nix/packages/harvest-exporter.nix](nix/packages/harvest-exporter.nix)
- **Documentation**: [packages/harvest/src/harvest_exporter/README.md](packages/harvest/src/harvest_exporter/README.md)

</details>
<details>
<summary><strong>kimai-exporter</strong> - Export time entries from Kimai with currency conversion</summary>

- **Homepage**: https://www.kimai.org
- **Usage**: `nix run github:numtide/freelancer-toolbox#kimai-exporter -- --help`
- **Nix**: [nix/packages/kimai-exporter.nix](nix/packages/kimai-exporter.nix)
- **Documentation**: [packages/kimai/src/kimai_exporter/README.md](packages/kimai/src/kimai_exporter/README.md)

</details>
<details>
<summary><strong>harvest-rounder</strong> - Round Harvest time entries up to the nearest billing increment</summary>

- **Homepage**: https://getharvest.com
- **Usage**: `nix run github:numtide/freelancer-toolbox#harvest-rounder -- --help`
- **Nix**: [nix/packages/harvest-rounder.nix](nix/packages/harvest-rounder.nix)
- **Documentation**: [packages/harvest/src/harvest_rounder/README.md](packages/harvest/src/harvest_rounder/README.md)

</details>
<details>
<summary><strong>working-days-calculator</strong> - Calculate working days from a Harvest annual CSV export</summary>

Export the annual CSV from [numtide.harvestapp.com/reports?kind=year](https://numtide.harvestapp.com/reports?kind=year), then:

```console
working-days-calculator annual-report.csv
```

- **Usage**: `nix run github:numtide/freelancer-toolbox#working-days-calculator -- <csv_file>`
- **Nix**: [nix/packages/working-days-calculator.nix](nix/packages/working-days-calculator.nix)

</details>

### Invoicing & Accounting

<details>
<summary><strong>sevdesk-invoicer</strong> - SevDesk integration: invoice generation, Wise bank imports, and German tax estimation</summary>

This package exposes three commands:

- `sevdesk-invoicer` — generate SevDesk invoices from harvest-exporter or kimai-exporter JSON output
- `sevdesk-wise-importer` — import Wise bank transactions into SevDesk check accounts
- `sevdesk-tax-estimator` — calculate remaining German tax payments

- **Homepage**: https://sevdesk.com
- **Usage**: `nix run github:numtide/freelancer-toolbox#sevdesk-invoicer -- --help`
- **Nix**: [nix/packages/sevdesk-invoicer.nix](nix/packages/sevdesk-invoicer.nix)
- **Documentation**: [packages/sevdesk-invoicer/README.md](packages/sevdesk-invoicer/README.md)

</details>
<details>
<summary><strong>sevdesk-cli</strong> - Command-line interface for the SevDesk API (vouchers, transactions, accounts)</summary>

The console script is named `sevdesk`.

- **Homepage**: https://sevdesk.com
- **Usage**: `nix run github:numtide/freelancer-toolbox#sevdesk-cli -- --help`
- **Nix**: [nix/packages/sevdesk-cli.nix](nix/packages/sevdesk-cli.nix)
- **Documentation**: [packages/sevdesk-cli/README.md](packages/sevdesk-cli/README.md)

</details>
<details>
<summary><strong>quipu-invoicer</strong> - Generate invoices in Quipu from time tracking exports</summary>

This package exposes two commands:

- `quipu-invoicer` — generate Quipu invoices from harvest-exporter or kimai-exporter JSON output
- `quipu-cli` — Python CLI for the Quipu API

- **Homepage**: https://getquipu.com
- **Usage**: `nix run github:numtide/freelancer-toolbox#quipu-invoicer -- --help`
- **Nix**: [nix/packages/quipu-invoicer.nix](nix/packages/quipu-invoicer.nix)
- **Documentation**: [packages/quipu-invoicer/README.md](packages/quipu-invoicer/README.md)

</details>

### Currency & Rates

| Tool | Description |
|------|-------------|
| **[ecbx](packages/ecbx/README.md)** | Fetch and query exchange rates from the [European Central Bank](https://www.ecb.europa.eu) |

### Banking

<details>
<summary><strong>wise-exporter</strong> - Download bank statements from Wise with 2FA support</summary>

- **Homepage**: https://wise.com
- **Usage**: `nix run github:numtide/freelancer-toolbox#wise-exporter -- --help`
- **Nix**: [nix/packages/wise-exporter.nix](nix/packages/wise-exporter.nix)
- **Documentation**: [packages/wise-exporter/README.md](packages/wise-exporter/README.md)

</details>

### Documents

<details>
<summary><strong>paperless-cli</strong> - CLI for Paperless-ngx: manage documents, tags, mail accounts, and rules</summary>

- **Homepage**: https://docs.paperless-ngx.com
- **Usage**: `nix run github:numtide/freelancer-toolbox#paperless-cli -- --help`
- **Nix**: [nix/packages/paperless-cli.nix](nix/packages/paperless-cli.nix)
- **Documentation**: [packages/paperless-cli/README.md](packages/paperless-cli/README.md)

</details>

## Installation

### Using Nix Flakes (Recommended)

Add to your system configuration:

```nix
{
  inputs = {
    freelancer-toolbox.url = "github:numtide/freelancer-toolbox";
  };

  # In your system packages:
  environment.systemPackages = with inputs.freelancer-toolbox.packages.${pkgs.stdenv.hostPlatform.system}; [
    harvest-exporter
    sevdesk-invoicer
    wise-exporter
    # ... other tools
  ];
}
```

> [!NOTE]
> This flake is built and tested against its pinned `nixpkgs-unstable` input.
> If you set `freelancer-toolbox.inputs.nixpkgs.follows = "nixpkgs"`, your
> `nixpkgs` must also track `nixpkgs-unstable` and be reasonably current.

### Try Without Installing

Run a specific tool directly without installing:

```bash
nix run github:numtide/freelancer-toolbox#harvest-exporter -- --help
nix run github:numtide/freelancer-toolbox#sevdesk-invoicer -- --help
nix run github:numtide/freelancer-toolbox#wise-exporter -- --help
# etc.
```

## Development

### Setup

Copy the environment template and fill in your API tokens:

```console
cp .envrc.local-template .envrc.local
# Edit .envrc.local with your API tokens
```

| Variable | Description |
|----------|-------------|
| `HARVEST_ACCOUNT_ID` | Harvest account ID |
| `HARVEST_BEARER_TOKEN` | API token from [Harvest Developers](https://id.getharvest.com/developers) |
| `SEVDESK_API_TOKEN` | SevDesk API token |
| `WISE_API_TOKEN` | Wise API token |
| `WISE_PRIVATE_KEY` | RSA private key for Wise 2FA (see [wise-exporter docs](packages/wise-exporter/README.md)) |
| `WISE_PROFILE` | Wise business profile ID |
| `PAPERLESS_URL` | Paperless-ngx instance URL |
| `PAPERLESS_TOKEN` | Paperless API token |
| `QUIPU_APP_ID` | Quipu OAuth application ID |
| `QUIPU_APP_SECRET` | Quipu OAuth application secret |
| `KIMAI_API_URL` | Kimai instance API URL |
| `KIMAI_API_KEY` | Kimai API key |

### Running the Tools

Run any workspace tool directly from source:

```console
uv sync                          # materialise .venv (one-time)
uv run harvest-exporter --help   # or any other console script
```

`nix develop` drops you into a shell with uv and the project formatters available. For a hermetic build of a specific tool:

```console
nix run .#harvest-exporter
```

The workspace also contains [`sevdesk-api`](packages/sevdesk-api/README.md),
a library member (no CLI) used by the sevdesk tools.

### Code Quality

```console
# Format all code
nix fmt

# Run checks
nix flake check
```

## Usage Examples

The commands below assume the tools are on your PATH — prefix with `uv run`
(see [Development](#development)) or use `nix run .#<package>` if they are not.

### Monthly Invoicing Workflow

Export your time tracking data and generate an invoice:

```console
# From Harvest
harvest-exporter --format json > harvest.json
sevdesk-invoicer --customer "CUSTOMER_ID" harvest.json

# From Kimai
kimai-exporter --client "Acme Corp" > kimai.json
sevdesk-invoicer --customer "CUSTOMER_ID" kimai.json
```

See [docs/workflows/monthly-invoicing.md](docs/workflows/monthly-invoicing.md) for the complete guide including currency conversion and multi-user scenarios.

### Working Days Report

Export the annual CSV from [numtide.harvestapp.com/reports?kind=year](https://numtide.harvestapp.com/reports?kind=year), then:

```console
working-days-calculator annual-report.csv
# Working days: 220 from 2024-01-02 00:00:00 to 2024-12-31 00:00:00
```

## Guides

- [Getting Started](docs/getting-started.md) — set yourself up as a contractor (tax registration, insurance, banking)
- [Monthly Invoicing](docs/workflows/monthly-invoicing.md) — export time tracking data and generate invoices
- [Country Guides](docs/countries/README.md) — country-specific guidance for Germany, UK, Switzerland, and more

## API References

- [Harvest API v2](https://help.getharvest.com/api-v2)
- [Wise API](https://api-docs.transferwise.com/)
- [SevDesk API](https://my.sevdesk.de/api/InvoiceAPI/doc.html)

## License

MIT
