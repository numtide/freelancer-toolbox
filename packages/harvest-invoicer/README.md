# harvest-invoicer

Fetches a month of [Harvest](https://getharvest.com) time data, opens a
browser-based editor where line items can be renamed, merged, or dropped, and
generates an invoice PDF via WeasyPrint.

## Installation

Via Nix (recommended — all native deps resolved):

```console
nix run .#harvest-invoicer -- --help
```

Via uv (development):

```console
uv sync
uv run harvest-invoicer --help
```

> **NixOS note**: `uv run harvest-invoicer` may fail at runtime if WeasyPrint
> cannot locate system libraries (libgobject, pango, etc.) — the same
> `LD_LIBRARY_PATH` issue that affects other packages with native deps.
> Use `nix run .#harvest-invoicer` for a fully hermetic execution.

## Quick start

```console
export HARVEST_ACCOUNT_ID=...
export HARVEST_BEARER_TOKEN=...

# Interactive editor (previous month, opens browser)
harvest-invoicer edit --issuer issuer.json --clients clients.json

# Headless PDF generation
harvest-invoicer generate --month 2026-06 --output-dir ./invoices/
```

## CLI reference

### `edit` — interactive editor

```
harvest-invoicer edit [--month YYYY-MM] [--client NAME] [--user NAME]
                      [--issuer PATH] [--clients PATH]
                      [--templates-dir DIR]
                      [--number STR] [--output PATH.pdf]
                      [--period-start YYYY-MM-DD] [--period-end YYYY-MM-DD]
                      [--port N] [--no-browser]
                      [--currency CODE] [--no-agency] [--demo]
```

Starts a local Flask server on `127.0.0.1` (never exposed to the network),
opens the editor in your default browser, and waits for you to click
**Generate PDF**.  Use `--demo` to try the editor without Harvest credentials
(loads synthetic line items and example config).

### `generate` — headless batch mode

```
harvest-invoicer generate [--month YYYY-MM]... [--client NAME] [--user NAME]
                          [--issuer PATH] [--clients PATH]
                          [--templates-dir DIR]
                          [--number STR] [--output-dir DIR]
                          [--period-start YYYY-MM-DD] [--period-end YYYY-MM-DD]
                          [--currency CODE] [--no-agency] [--demo]
```

`--month` is repeatable; one PDF is produced per month.  Exits non-zero if any
month has no entries.

### Service period

Each invoice shows a **Period** row (the service period it covers), defaulting
to the first and last day of `--month`.  Customize it with
`--period-start` / `--period-end` (single-month only), or edit the period
directly in the interactive editor — clearing both fields removes the row.

### Agency mode and `--no-agency`

By default both commands operate in **agency mode**: time entries are grouped
by real Harvest client name and the agency multiplier (inherited from
`harvest-exporter`'s `NUMTIDE_RATE`) is applied to each developer's hourly
rate.  "External - " prefixed clients are treated as direct-billed and are
excluded from the output unless `--client` explicitly targets one.  The keys in
`clients.json` must be the exact Harvest client names.

Pass `--no-agency` to switch to **direct-billing mode**: entries are grouped by
project name (the same grouping the Harvest exporter uses when agency is
disabled), the agency multiplier is not applied, and `--client` must be the
Harvest project name.  A `--client` filter is effectively required in this mode
because all entries are treated as external when there is no agency rate.

## Environment variables

| Variable | Description |
|----------|-------------|
| `HARVEST_ACCOUNT_ID` | Harvest account ID (required unless `--demo`) |
| `HARVEST_BEARER_TOKEN` | Harvest API bearer token (required unless `--demo`) |
| `INVOICE_ISSUER_FILE` | Path to issuer.json (default: `./issuer.json`) |
| `INVOICE_CLIENTS_FILE` | Path to clients.json (default: `./clients.json`) |
| `INVOICE_TEMPLATES_DIR` | Directory for custom templates (same as `--templates-dir`) |

## Configuration

### issuer.json

```json
{
  "name": "Your Name / Company",
  "address_line1": "Street and number",
  "address_line2": "Postal code and city",
  "country": "Country",
  "tax_id": "Your tax identifier",
  "tax_id_label": "VAT ID",
  "phone": "+1 555 000 0000",
  "email": "you@example.com",
  "bank": {
    "iban": "XX00 0000 0000 0000 0000 00",
    "bic": "BANKBICXXX"
  },
  "date_format": "%Y-%m-%d",
  "legal_note": "Optional legal note shown at the bottom of the invoice.",
  "number_template": "{year}-{month}"
}
```

**Optional fields:**

| Field | Default | Description |
|-------|---------|-------------|
| `tax_id_label` | `"Tax ID"` | Label shown next to your tax ID on the invoice |
| `date_format` | `"%Y-%m-%d"` | Python strftime pattern for all dates |
| `legal_note` | _(absent)_ | Legal text at the invoice footer; omitted entirely when not set |
| `number_template` | _(absent)_ | Invoice number template with `{year}` and `{month}` placeholders |

**Examples of `date_format`:**

| Pattern | Example output |
|---------|---------------|
| `%Y-%m-%d` (default) | 2026-06-01 |
| `%d/%m/%Y` | 01/06/2026 |
| `%d.%m.%Y` | 01.06.2026 |
| `%B %d, %Y` | June 01, 2026 |

### clients.json

A JSON object keyed by the exact Harvest client name:

```json
{
  "Harvest Client Name": {
    "name": "Full legal name for invoice",
    "address_line1": "Street and number",
    "address_line2": "Postal code and city",
    "country": "Country",
    "tax_id": "Client tax identifier",
    "tax_id_label": "VAT No."
  }
}
```

See `src/harvest_invoicer/examples/` for full working examples with fake data.

### Invoice numbering

The default invoice number is the invoiced month string `YYYY-MM`
(e.g. `2026-06`).  Override via:

1. `--number` CLI flag (single-month only).
2. `number_template` in issuer.json using `{year}` and `{month}` placeholders
   (e.g. `"{year}-{month}"` → `"2026-06"`).

## Custom templates

The packaged `invoice.html` and `style.css` are sensible defaults.  To customise
the invoice layout, copy them as a starting point and point the tool at your
directory:

```console
# Copy packaged templates to a local directory
OUT=$(nix build .#harvest-invoicer --no-link --print-out-paths)
cp -r "$OUT/lib/python3.13/site-packages/harvest_invoicer/templates" ./my-templates

# Use your custom templates (packaged files act as per-file fallback)
harvest-invoicer edit   --templates-dir ./my-templates ...
harvest-invoicer generate --templates-dir ./my-templates ...
```

You can override just one file — for example, only `invoice.html` — and the
packaged `style.css` is still used as the fallback.

## Security

The editor server binds to `127.0.0.1` only and has no authentication.
Do not expose it to a network interface.

## Examples

See `src/harvest_invoicer/examples/issuer.example.json` and
`src/harvest_invoicer/examples/clients.example.json` for fully working
fake-data configs.  A Spanish setup example:

```json
{
  "tax_id_label": "NIF",
  "date_format": "%d/%m/%Y",
  "legal_note": "Factura exenta de IVA por aplicación artículo 25 Ley IVA de 1992."
}
```

Country-specific labels, date formats, and legal notes belong in your
`issuer.json` and `clients.json` — not in the tool itself.
