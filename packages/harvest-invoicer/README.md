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
harvest-invoicer serve

# Headless PDF generation
harvest-invoicer generate --month 2026-06 --output-dir ./invoices/
```

## CLI reference

### `serve` — interactive editor

```
harvest-invoicer serve [--harvest-client NAME]
                       [--db PATH]
                       [--templates-dir DIR] [--output PATH.pdf]
                       [--port N] [--no-browser]
                       [--currency CODE] [--no-agency] [--demo]
```

Starts a local Flask server on `127.0.0.1` (never exposed to the network)
and opens the editor in your default browser.  The editor starts **without
fetching**, seeded with the previous month's number, billing period, and
import range — all editable on the page.  Import the hours with **Fetch
from Harvest** (credentials are only needed at that point).  Use `--demo` to try
the editor with synthetic data pre-loaded.

The live preview has two modes: **PDF** (the default — the exact WeasyPrint
render, byte-identical to the generated file, with real pagination and page
footers; refreshes are debounced since each render takes about a second) and
**HTML** (instant, same template and stylesheet the PDF uses).  The preview
pane can be hidden, and opened in a separate window.

### `generate` — headless batch mode

```
harvest-invoicer generate [--month YYYY-MM]... [--harvest-client NAME] [--user NAME]
                          [--db PATH] [--bill-to KEY]
                          [--templates-dir DIR]
                          [--number STR] [--output-dir DIR]
                          [--period-start YYYY-MM-DD] [--period-end YYYY-MM-DD]
                          [--currency CODE] [--no-agency] [--demo]
```

`--month` is repeatable; one PDF is produced per month.  Exits non-zero if any
month has no entries.

### Service period and import range

The service period drives **both** the Harvest import range and the
**Period** row shown on the invoice.  It defaults to the first and last day
of the invoiced month; for headless `generate`, customize it with
`--period-start` / `--period-end` (single-month only) to import and bill a
partial month.

In the interactive editor the two concepts are separate rows: the invoice's
**Period start/end** fields only relabel the document (clearing both removes
the Period row), while the **Import from Harvest — start/end** fields plus
the **Fetch from Harvest** button re-import the line items for that range on
the spot (a confirmation guards against overwriting manual edits).  Fetching
never modifies the invoice's period fields.

### Bill-to selection

The client whose hours you *fetch* (`--client`, a Harvest client name) and
the client you *bill* are independent — in agency mode you typically fetch
hours logged under end-customer Harvest clients but invoice the agency.

The bill-to entry is chosen in this order:

1. `--bill-to KEY` — an explicit client key (`generate`).
2. `default_bill_to` in the issuer settings — pin your standard recipient (e.g. the
   consultancy you invoice every month).
3. Auto-detect: the first fetched line's Harvest client name, if it matches
   a configured client key.
4. The single configured client, when there is exactly one.

In the editor, the **Bill to** dropdown (Invoice details) switches the
invoiced client mid-session: the current line items and manual edits are
kept, the previous client's recurring extra lines are swapped for the new
client's, and its `vat_rate` is applied.  Switching never re-fetches;
subsequent fetches follow the selected client.  Clients added in Settings
appear in the dropdown.

### Whose hours are imported

Without a user filter the fetch imports **everyone's** hours in the
consultancy's Harvest account.  If you invoice only your own time:

1. Set `"harvest_user": "Your Harvest Name"` in the issuer settings (in
   Settings) — plain `serve`/`generate` then imports only your hours.
2. Or pass `--user "Your Harvest Name"` to `generate` (wins over the config).

The name must match your Harvest user name exactly.  On a mismatch the
error lists the user names that do have hours in the period.  When an
import without any user filter mixes several people's hours, the editor
shows a prominent warning (and `generate` prints one to stderr) so a
whole-team total can't masquerade as a personal invoice.  The warning
lists every name as a **click-to-pick button**: clicking your name sets
`harvest_user`, saves it, and re-imports only your hours
on the spot.

`--harvest-client NAME` (formerly `--client`, still accepted) restricts the
import to hours logged under one Harvest client; it is unrelated to the
invoiced (bill-to) client.

### Agency mode and `--no-agency`

By default both commands operate in **agency mode**: time entries are grouped
by real Harvest client name and the agency multiplier (inherited from
`harvest-exporter`'s `NUMTIDE_RATE`) is applied to each developer's hourly
rate.  "External - " prefixed clients are treated as direct-billed and are
excluded from the output unless `--client` explicitly targets one.  The keys in
the client settings must be the exact Harvest client names.

Pass `--no-agency` to switch to **direct-billing mode**: entries are grouped by
project name (the same grouping the Harvest exporter uses when agency is
disabled), the agency multiplier is not applied, and `--client` must be the
Harvest project name.  A `--client` filter is effectively required in this mode
because all entries are treated as external when there is no agency rate.

## Environment variables

| Variable | Description |
|----------|-------------|
| `HARVEST_ACCOUNT_ID` | Harvest account ID (needed when fetching; `generate` requires it) |
| `HARVEST_BEARER_TOKEN` | Harvest API bearer token (needed when fetching; `generate` requires it) |
| `HARVEST_INVOICER_DB` | State database path (default: `~/.local/share/harvest-invoicer/state.db`) |
| `INVOICE_TEMPLATES_DIR` | Directory for custom templates (same as `--templates-dir`) |

## Configuration

All configuration lives in a single SQLite state database, managed entirely
through the editor's **Settings** page — issuer identity, banking, invoice
defaults, and per-client billing details.  Saves apply to the running
session immediately (the live preview updates) and persist transactionally.
In `--demo` mode changes apply to the session only.

### Where state lives

1. `--db PATH` or `HARVEST_INVOICER_DB` — explicit location (use this for
   a server deployment, e.g. `/var/lib/harvest-invoicer/state.db`).
2. Default: `~/.local/share/harvest-invoicer/state.db` (respects
   `XDG_DATA_HOME`).

**First run:** with an empty database, `serve` opens straight into the
Settings page — fill in your details and they are saved.  Headless
`generate` errors until configured.

### Issuer fields

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
| `harvest_user` | _(absent)_ | Only import this Harvest user's hours (see "Whose hours are imported") |
| `default_bill_to` | _(absent)_ | Client key billed by default (see "Bill-to selection") |

**Examples of `date_format`:**

| Pattern | Example output |
|---------|---------------|
| `%Y-%m-%d` (default) | 2026-06-01 |
| `%d/%m/%Y` | 01/06/2026 |
| `%d.%m.%Y` | 01.06.2026 |
| `%B %d, %Y` | June 01, 2026 |

### Client fields

Clients are keyed by the exact Harvest client name:

```json
{
  "Harvest Client Name": {
    "name": "Full legal name for invoice",
    "address_line1": "Street and number",
    "address_line2": "Postal code and city",
    "country": "Country",
    "tax_id": "Client tax identifier",
    "tax_id_label": "VAT No.",
    "vat_rate": 0.21
  }
}
```

**Optional `vat_rate`** (number between 0 and 1, e.g. `0.21` for 21%): applied
to every imported line for that client — use it for domestic clients that
must be charged VAT.  Omit it for reverse-charge / VAT-exempt invoicing
(lines default to 0%).  The rate can still be adjusted per line via the
invoice model if needed.

**Optional `email`**: the recipient's billing address — not printed on the
invoice; reserved for sending the invoice by email.

**Optional `language`** (`en` or `es`): the language of invoices rendered
for this client — headings, column labels, payment block, and the PDF page
footer.  Defaults to the issuer-level `language`, then English.  Dates keep
following `date_format` and amounts keep one consistent notation regardless
of language; `tax_id_label` still overrides the translated default.  Custom
templates receive the same `t(key)` helper and `lang` variable.

**Optional `extra_lines`**: recurring non-Harvest items (fixed retainer,
license pass-through, …) automatically appended to every import for that
client:

```json
"extra_lines": [
  { "concept": "Monthly retainer", "unit_price": 500, "quantity": 1 }
]
```

`quantity` defaults to 1.  Extra lines are marked with an "extra" pill in
the editor, are re-added on every fetch, and are never collapsed by
merge-duplicates.  They are editable in Settings (one per line:
`description ; unit price ; quantity`).

See `src/harvest_invoicer/examples/` for full working examples with fake data.

### Invoice numbering

The default invoice number is the invoiced month string `YYYY-MM`
(e.g. `2026-06`).  Override via:

1. `--number` CLI flag (single-month only).
2. `number_template` in the issuer settings using `{year}` and `{month}` placeholders
   (e.g. `"{year}-{month}"` → `"2026-06"`).

## Custom templates

The packaged `invoice.html` and `style.css` are sensible defaults.  To customise
the invoice layout, scaffold a templates folder and point the tool at it:

```console
# Create ./invoice-templates (or pass a directory name) with editable
# copies of the packaged invoice.html and style.css
harvest-invoicer templates init

# Use your custom templates (packaged files act as per-file fallback)
harvest-invoicer serve --templates-dir ./invoice-templates ...
harvest-invoicer generate --templates-dir ./invoice-templates ...
```

`templates init` never overwrites existing files unless you pass `--force`,
so re-running it is safe.  You can override just one file — for example, only
`invoice.html` — and the packaged `style.css` is still used as the fallback;
delete whichever file you don't customise.

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
your issuer and client settings — not in the tool itself.
