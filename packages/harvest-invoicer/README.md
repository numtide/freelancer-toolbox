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
                       [--db PATH] [--invoices-dir DIR]
                       [--templates-dir DIR] [--output PATH.pdf]
                       [--host ADDR] [--allowed-host HOST]... [--port N] [--no-browser]
                       [--currency CODE] [--no-agency] [--demo]
                       [--oidc-issuer URL ...]  # see "Server deployment (OIDC)"
```

Starts a local Flask server on `127.0.0.1` (not reachable from the network
unless `--host` says otherwise) and opens the editor in your default browser.  The editor starts **without
fetching**, seeded with the previous month's number, billing period, and
import range — all editable on the page.  Import the hours with **Fetch
from Harvest** (credentials are only needed at that point).  Use `--demo` to try
the editor with synthetic data pre-loaded.

The live preview has two modes: **PDF** (the default — the exact WeasyPrint
render, byte-identical to the generated file, with real pagination and page
footers; refreshes are debounced since each render takes about a second) and
**HTML** (instant, same template and stylesheet the PDF uses).  The preview
pane can be hidden, and opened in a separate window.

Until the issuer has a name and a bill-to client with a name is selected,
the preview (and Generate / Send) shows a short explanation with a link to
Settings instead of the invoice.

**Generate PDF** archives the invoice (see "Invoice archive" below) and
opens a panel with the file name and **Open**, **Download** and **Send by
email** buttons.  `--output PATH.pdf` additionally writes each generated
PDF to that path.  In `--demo` mode there is no database to archive into,
so Generate only writes `--output` (default `invoice-<number>.pdf` in the
current directory), as before the archive existed.

### Invoice archive

> **Upgrading:** `serve` no longer writes `invoice-<number>.pdf` to the
> current directory unless `--output` is given — generated PDFs go to the
> archive.  Scripts that picked up that file should pass
> `--output invoice.pdf` (or read the archive directory) instead.

Every PDF that `serve` generates is kept, with its metadata, so earlier
invoices can be reopened, downloaded, sent or deleted later.

- **Where:** `--invoices-dir DIR` or `HARVEST_INVOICER_INVOICES_DIR`;
  default `invoices/` next to the state database (e.g.
  `~/.local/share/harvest-invoicer/invoices/`).  The metadata (number,
  bill-to client, period, total, content hash, creation date, and every
  send with its recipients) lives in the database (`invoices` and
  `invoice_sends` tables); existing databases gain them automatically.
- **Permissions:** the directory should belong to the user the service
  runs as (that uid writes, reads and deletes the PDFs).  When the tool
  creates it, it is `0700`; an existing directory is never changed — if
  other users can access it, a warning is logged and tightening it is up
  to you.  PDFs are written `0600` and flushed to disk before they are
  listed.  A PDF that no longer matches its recorded SHA-256 is treated
  as missing (not served, sent or reused).
- **File names** are readable and unique:
  `<number>_<client>_<random>.pdf`, e.g. `2026-06_Numtide-Sarl_3f9a1c2e.pdf`
  (accents folded, anything but letters, digits and dashes replaced).
- **Duplicates:** generating again without changes reuses the newest
  archived PDF for that invoice number when its content is identical,
  instead of adding a copy.  Any edit gives a new entry.
- **Links:** each entry has its own unguessable link,
  `/invoices/<id>.pdf` (`?download=1` downloads it under its file name).
  With OIDC the links, like every page, require a signed-in, allow-listed
  user.  `/pdf` is a legacy link, kept for old bookmarks: it serves the
  PDF this editor session generated last (404 until you Generate).

The **Invoices** page (the archive-box icon in the editor's top bar)
lists every archived invoice — creation date, number, client, total and
whether it was sent (the last send, and how many) — with **Open**, **Download**, **Send**
and **Delete** actions.  Deleting asks for confirmation (with an extra
warning if the invoice was already emailed) and removes both the entry
and its PDF.

Headless `generate` does not use the archive.

### Sending by email

With SMTP configured, the generated-PDF panel, the Invoices page and the
editor's **Send invoice** action open a send dialog:

- **To** is prefilled with the bill-to client's `email`; several
  addresses can be given, separated by commas.
- **Subject** and **message** are prefilled in the invoice's language
  (English or Spanish, like the PDF) and mention the invoice number and,
  when set, the service period.  Custom templates saved in Settings >
  Email (with `{number}`, `{period}`, `{total}`, `{due}`, `{company}`, …)
  take precedence.
- The archived PDF is attached under its file name, and the send is
  recorded on the archive entry (date and the recipients the mail server
  accepted).  If the server refuses some recipients, a warning names
  them; if it refuses all of them, the send fails (even when your own
  copy went through).  Sending again — from the Invoices page, or from
  the editor when the PDF to send is identical to one already emailed —
  shows the previous send and asks for confirmation; every send is kept.

Without an SMTP host the Send buttons are disabled with a pointer to
Settings > Email.  The SMTP settings are edited there; each non-secret
field can be fixed by an environment variable instead, and the password
is read **only** from the environment:

| Environment variable | Setting |
|----------------------|---------|
| `HARVEST_INVOICER_SMTP_HOST` | SMTP server |
| `HARVEST_INVOICER_SMTP_PORT` | Port (default per encryption: 587 / 465 / 25) |
| `HARVEST_INVOICER_SMTP_ENCRYPTION` | `starttls` (default), `ssl` or `none` |
| `HARVEST_INVOICER_SMTP_USERNAME` | Login user |
| `HARVEST_INVOICER_SMTP_PASSWORD` | Login password (environment only, never stored) |
| `HARVEST_INVOICER_SMTP_FROM_ADDRESS` | Sender address (default: the issuer's email) |
| `HARVEST_INVOICER_SMTP_REPLY_TO` | Reply-To address |

TLS certificates are always verified.  For example, with Proton Mail
(SMTP submission uses an SMTP token generated in Proton Mail's settings,
not your account password; see Proton's documentation for which plans
and addresses support it):

```console
export HARVEST_INVOICER_SMTP_HOST=smtp.protonmail.ch
export HARVEST_INVOICER_SMTP_PORT=587
export HARVEST_INVOICER_SMTP_ENCRYPTION=starttls
export HARVEST_INVOICER_SMTP_USERNAME=billing@your-domain.example
export HARVEST_INVOICER_SMTP_FROM_ADDRESS=billing@your-domain.example
export HARVEST_INVOICER_SMTP_PASSWORD="$(cat /run/secrets/proton-smtp-token)"
harvest-invoicer serve
```

**Settings > Email > Send test email** checks the connection and login
without sending anything.  Message bodies, recipients and credentials are
never logged.

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
| `HARVEST_INVOICER_INVOICES_DIR` | Invoice archive directory (same as `--invoices-dir`; default: `invoices/` next to the database) |
| `HARVEST_INVOICER_SMTP_*` | Email sending — see "Sending by email" |
| `INVOICE_TEMPLATES_DIR` | Directory for custom templates (same as `--templates-dir`) |
| `HARVEST_INVOICER_HOST` | Bind address for `serve` (same as `--host`) |
| `HARVEST_INVOICER_OIDC_*`, … | OIDC login for a server deployment — see below |

## Configuration

All configuration lives in a single SQLite state database, managed entirely
through the editor's **Settings** page — issuer identity, banking, invoice
defaults, and per-client billing details.  Saves apply to the running
session immediately (the live preview updates) and persist transactionally.
In `--demo` mode changes apply to the session only.

### Where state lives

1. `--db PATH` or `HARVEST_INVOICER_DB` — explicit location (use this for
   a server deployment, e.g. `/var/lib/harvest-invoicer/state.db`; the
   invoice archive then defaults to `/var/lib/harvest-invoicer/invoices/`).
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
| `tax_id_label` | `"Tax ID"` | Label shown next to your tax ID. A plain string is used verbatim; a per-language map (e.g. `{"en": "Tax ID", "es": "Identificador fiscal"}`) is localized to the invoice language |
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
invoice; prefilled as the recipient when sending the invoice by email.

**Optional `language`** (`en` or `es`): the language of invoices rendered
for this client — headings, column labels, payment block, and the PDF page
footer.  Defaults to the issuer-level `language`, then English.  Dates keep
following `date_format` and amounts keep one consistent notation regardless
of language.  A plain-string `tax_id_label` still overrides the translated
default in every language; use the per-language map form (see above) to keep
the label localized.  Custom templates receive the same `t(key)` helper and
`lang` variable.

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

## Server deployment (OIDC)

`serve` can run on a server behind a reverse proxy, with every request
requiring an OpenID Connect login.  It is opt-in: setting an issuer turns
it on; without one nothing changes.  Every option also reads the
environment variable shown.  Pass secrets through the environment or the
`*_FILE` variants rather than command-line flags, which show up in the
process list.

| Option | Environment variable | Default / notes |
|--------|----------------------|-----------------|
| `--oidc-issuer URL` | `HARVEST_INVOICER_OIDC_ISSUER` | Enables OIDC. Must be `https://` (plain http only on loopback) |
| `--oidc-client-id` | `HARVEST_INVOICER_OIDC_CLIENT_ID` | Required |
| `--oidc-client-secret` | `HARVEST_INVOICER_OIDC_CLIENT_SECRET` | Omit for a PKCE-only public client |
| `--oidc-client-secret-file` | `HARVEST_INVOICER_OIDC_CLIENT_SECRET_FILE` | Read the secret from a file (e.g. a mounted Kubernetes secret) |
| `--oidc-allowed-email` | `HARVEST_INVOICER_OIDC_ALLOWED_EMAILS` | Repeatable / comma-separated. Matched case-insensitively against a *verified* `email` claim |
| `--oidc-allowed-subject` | `HARVEST_INVOICER_OIDC_ALLOWED_SUBJECTS` | Repeatable / comma-separated `sub` claims |
| `--oidc-allow-any-user` | `HARVEST_INVOICER_OIDC_ALLOW_ANY_USER` | Admit anyone the provider authenticates. Without it an empty allow-list refuses to start |
| `--oidc-scopes` | `HARVEST_INVOICER_OIDC_SCOPES` | `openid email profile` |
| `--public-url URL` | `HARVEST_INVOICER_PUBLIC_URL` | **Required** with OIDC, e.g. `https://invoicer.example.com`. The redirect and post-logout URIs are built from it alone; the CSRF guard accepts its host |
| `--session-secret` | `HARVEST_INVOICER_SESSION_SECRET` | **Required** with OIDC, ≥ 32 characters (`openssl rand -hex 32`). Signs the session cookie, so logins survive restarts; rotating it signs everyone out |
| `--session-secret-file` | `HARVEST_INVOICER_SESSION_SECRET_FILE` | Read it from a file |
| `--session-lifetime HOURS` | `HARVEST_INVOICER_SESSION_LIFETIME` | `12`. Counted from the login, however active the session |
| `--trusted-proxies N` | `HARVEST_INVOICER_TRUSTED_PROXIES` | Proxies whose `X-Forwarded-*` headers are honored: 1 with OIDC, else 0. They only affect the CSRF host check and the cookie's `Secure` flag |
| `--secure-cookies` | `HARVEST_INVOICER_SECURE_COOKIES` | Always mark the cookie `Secure` (default: when the request is https) |
| `--server` | `HARVEST_INVOICER_SERVER` | `auto`: waitress with OIDC, the Werkzeug development server otherwise. `waitress` / `werkzeug` force one |
| `--threads N` | `HARVEST_INVOICER_THREADS` | `8` waitress worker threads |

With OIDC the app is served by [waitress](https://docs.pylonsproject.org/projects/waitress/):
one process (the editor's state lives in memory, so never run several),
several threads, request bodies capped at 1 MiB, and a graceful stop on
`SIGTERM`.  Forwarded headers are handled by the app (`--trusted-proxies`),
not by waitress, whose `trusted_proxy` setting stays off.

Point liveness/readiness probes (e.g. Kubernetes `httpGet`) at
**`/healthz`**: it answers `200 ok` with no login and for any `Host`
(kubelet probes use the pod IP), reveals nothing about the deployment, and
does no work.  Every other path refuses a `Host` that is not served (`403`),
so it is the only one usable as a probe.

Register the client with your provider as a web application using the
authorization-code flow with PKCE:

- **Redirect URI:** `https://<public host>/oidc/callback`
- **Post-logout redirect URI:** `https://<public host>/` (sign-out also ends
  the provider session when it advertises an `end_session_endpoint`)
- **ID token signing:** RS256, PS256, ES256 or EdDSA

With Zitadel (any OIDC provider works the same way):

```console
export HARVEST_INVOICER_OIDC_ISSUER=https://auth.example.com
export HARVEST_INVOICER_OIDC_CLIENT_ID=123456789@invoicer
export HARVEST_INVOICER_OIDC_CLIENT_SECRET_FILE=/run/secrets/oidc-client-secret
export HARVEST_INVOICER_OIDC_ALLOWED_EMAILS=you@example.com
export HARVEST_INVOICER_SESSION_SECRET_FILE=/run/secrets/session-secret
export HARVEST_INVOICER_PUBLIC_URL=https://invoicer.example.com

harvest-invoicer serve --host 0.0.0.0 --no-browser \
  --db /var/lib/harvest-invoicer/state.db
```

Zitadel puts the email in the userinfo response rather than the ID token
by default; the editor fetches it from there when the ID token lacks
`email` or `email_verified` (the subject must match).

Unauthenticated page loads redirect to the provider and come back to the
requested page; other requests get `401`.  A signed-in account that is not
on the allow-list gets a `403` page.  Each request checks the session's
age and the allow-list in effect: an account removed from the allow-list
(which takes a restart) loses access on its next request.  The signed-in
email and a sign-out button appear in the top bar.

All allowed users share one editor: the same invoice session, Harvest
fetches, invoice archive and SMTP sending.  It is meant for one person (or a few trusted
ones), not as a multi-tenant service.

## Security

Without OIDC the editor has no authentication: it binds to `127.0.0.1`
by default, and must not be exposed to a network you don't trust.  A Host
guard answers only the served host(s) — loopback, `--host`,
`--allowed-host` and, with OIDC, the `--public-url` host (compared without
case, port or trailing dot) — for every request, and state-changing
requests must also come from the same origin.  Binding to `0.0.0.0`
without `--allowed-host` (and without OIDC) accepts any host, still
requiring a same-origin `Origin`/`Referer` for changes; naming hosts with
`--allowed-host` restricts it to those.

With OIDC (see above) every request needs an allow-listed login.  The
login flow uses PKCE, state and nonce; the ID token's signature (asymmetric
algorithms only), issuer, audience and expiry are verified.  The session
cookie is `HttpOnly` and `SameSite=Lax`, and **signed, not encrypted**: during
a login it holds the PKCE verifier and nonce, readable by (only) the user's
own browser.  Signing out is a `POST` covered by the CSRF guard.  Behind a
TLS-terminating proxy the guard accepts the `--public-url` host; with OIDC
a wildcard bind never accepts other hosts.

Every request — reads included — must name a host the server serves (the
same allow-list), so a DNS-rebinding page can't read the editor or the
invoices through its own domain.

Archived invoices: links carry a random 128-bit id, but are not a
capability — they need the same login as everything else.  Archive files
are created owner-only (`0600`, in a `0700` directory), their names are
reduced to `[A-Za-z0-9_-]` and re-checked to stay inside the invoices
directory, and they are opened without following symlinks.  Deleting and
sending are `POST`s
covered by the CSRF guard.  Recipients and the subject are validated and
may not contain line breaks or control characters (no header injection).

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
