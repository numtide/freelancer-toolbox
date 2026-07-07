# ecbx

Fetch and query exchange rate data published by the [European Central Bank](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/).

Rates are stored locally in a SQLite database and can be queried offline. Cross-rates between non-EUR currencies are calculated from their respective EUR reference rates.

## Usage

### Initialize the local database

Downloads the full historical dataset (~27 years of daily rates):

```console
ecbx initialize
```

### Update to the latest rates

```console
ecbx update
```

### Show database status

```console
ecbx status
ecbx --verbose status   # also lists all available currencies
```

### Convert between currencies

The date argument is currently required in practice — defaulting to the latest available rate when no date is given is a known limitation.

```console
# Specific date
ecbx convert 2024-01-05 EUR USD 100

# Compact date format also works
ecbx convert 20240105 EUR USD 100
```

### List all rates for a date

```console
# Latest available date
ecbx rates

# Specific date
ecbx rates 2024-01-05
```

### Show a full rate matrix for a base currency

```console
ecbx matrix 2024-01-05 USD
ecbx matrix --format json 2024-01-05 USD
```

### List available currencies

```console
ecbx currencies
```

## Options

| Option | Description |
|--------|-------------|
| `--db PATH` | Use a custom database file instead of the default XDG path |
| `--verbose` | Show additional information |

The default database is stored at `$XDG_CONFIG_HOME/ecbx/rates.db` (usually `~/.config/ecbx/rates.db`).
