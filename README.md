# Harvest invoice calculator

Create your invoice based on [Harvest](https://numtide.harvestapp.com) timesheets
and calculate the exchange rate to your currency using [Transferwise](https://transferwise.com).

Optional: generate invoice using Sevdesk

## Requirements

Generate your personal access token in Harvest using [this page](https://id.getharvest.com/oauth2/access_tokens/new).

```console
cp .envrc.local-template .envrc.local
```

Save your Account ID and your token in `.envrc.local`

## Usage / Examples

* Generate for the current month

```console
harvest-exporter
```

* Generate for march:

```console
harvest-exporter --month 3
```

* Filter by user

```console
harvest-exporter --user "Hans Maier"
```

* Generate using json output

```console
harvest-exporter --format json
```

* Generate using other currency

```console
harvest-exporter --currency CHF
```

* Override hourly rate:

```
harvest-exporter  --hourly-rate 100
```

This will override the hourly rate reported by harvest prior to applying the nutmide rate.

* Filter by client:

```
harvest-exporter --client "Some client"
```

This can be also used to export hours for clients that are external to numtide (client name starting with "External -")

* Generate an invoice with [sevdesk](https://sevdesk.de)

Generate a bill from the harvest exprt for the customer with the ID 1000

```
$ sevdesk-invoicer --customer "1000" harvest.json
```

## Calculate working days from harvest time report.

For income tax in Germany one can claim money back for each day. The time report can be obtained from [here](https://numtide.harvestapp.com/reports) for each user.
Than run this script:

``` console
$ working-days-calculator report.csv
Working days: 171 from 2022-01-12 00:00:00 to 2022-12-29 00:00:00
```

## Kimai Usage/Examples

Exports the last month timesheets of user Jon for client Bob  
```
./bin/kimai-exporter --client Bob --user Jon
```

## German income tax estimator

Calculates how much money still needs to be paid for the current year, given the current revenu, expenses and already payed pre-tax.

```
$ nix shell $HOME/git/freelancer-toolbox#sevdesk-invoicer -c sevdesk-tax-estimator --tax-office-name 'Finanzamt Berlin Finanzkasse' --harvest-folder 2024 --wise-folder statements/2024
...
Taxes left to pay: XXXXX.XX
```

## Import wise bank statements into sevdesk

1. Get for each currency the account number / IBAN.
2. Download the bank transactions as CSV from the Transactions tab in Wise
3. Run the importer command:

```
nix shell $HOME/git/freelancer-toolbox#sevdesk-invoicer -c sevdesk-wise-importer -add-account "BE00 0000 0000 0000" "EUR" --add-account 8000000000 USD --import-state wise-import-state.json transaction-history.csv
```

## Paperless-ngx CLI

A command-line interface for managing [Paperless-ngx](https://docs.paperless-ngx.com/) documents, mail accounts, mail rules, and tags. This tool allows you to interact with your Paperless-ngx instance from the command line.

### Key features:
- Search, upload, download, and delete documents
- Manage tags and organize documents
- Configure mail accounts and mail rules for automatic document import
- Secure API token management through password managers

### Usage example:

```console
# Search for invoices
paperless-cli documents search "invoice"

# Upload a document with tags
paperless-cli documents upload /path/to/document.pdf --title "Invoice 2024" --tags "1,2,3"

# Create mail rules for automatic processing
paperless-cli mail-rules create "Invoice Rule" \
  --filter-from "invoices@company.com" \
  --assign-tags "1,2,3"
```

See the [paperless-cli README](./paperless-cli/README.md) for detailed configuration and usage instructions.

## API References

* [Harvest](https://help.getharvest.com/api-v2)
* [Transferwise](https://api-docs.transferwise.com/#quotes-get-temporary-quote)
* [Sevdesk](https://my.sevdesk.de/api/InvoiceAPI/doc.html#tag/Invoice)
