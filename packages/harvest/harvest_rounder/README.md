# harvest-rounder

Round [Harvest](https://getharvest.com) time entries up to the nearest increment (default: 15 minutes). This ensures time entries are rounded consistently for billing purposes.

## Installation

```console
nix shell github:numtide/freelancer-toolbox#harvest-rounder
```

## Configuration

Set the following environment variables (or use CLI flags):

| Variable | Description |
|----------|-------------|
| `HARVEST_ACCOUNT_ID` | Your Harvest account ID |
| `HARVEST_BEARER_TOKEN` | API token from [Harvest Developers](https://id.getharvest.com/developers) |

## Usage

By default, rounds entries for the authenticated user from the past 4 weeks.

Preview changes without applying them:

```console
harvest-rounder --dry-run
```

Apply rounding (will prompt for confirmation):

```console
harvest-rounder
```
