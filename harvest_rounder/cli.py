"""CLI for rounding Harvest time entries."""

import argparse
import os
import sys
import urllib.error
from datetime import datetime, timedelta
from fractions import Fraction

from harvest import get_current_user

from . import TimeEntry, get_time_entries, update_time_entry


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Round Harvest time entries to the nearest increment",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    account = os.environ.get("HARVEST_ACCOUNT_ID")
    parser.add_argument(
        "--harvest-account-id",
        default=account,
        required=account is None,
        help="Get one from https://id.getharvest.com/developers (env: HARVEST_ACCOUNT_ID)",
    )

    token = os.environ.get("HARVEST_BEARER_TOKEN")
    parser.add_argument(
        "--harvest-bearer-token",
        default=token,
        required=token is None,
        help="Get one from https://id.getharvest.com/developers (env: HARVEST_BEARER_TOKEN)",
    )

    parser.add_argument(
        "--user",
        type=str,
        default=os.environ.get("HARVEST_USER"),
        help="Filter by user name (env: HARVEST_USER). Defaults to the authenticated user.",
    )

    parser.add_argument(
        "--all-users",
        action="store_true",
        help="Process entries for all users instead of just the authenticated user",
    )

    parser.add_argument(
        "--start",
        type=int,
        help="Start date i.e. 20220101",
    )

    parser.add_argument(
        "--end",
        type=int,
        help="End date i.e. 20220101",
    )

    parser.add_argument(
        "--increment",
        type=int,
        default=15,
        choices=[5, 6, 10, 12, 15, 20, 30, 60],
        help="Rounding increment in minutes",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be rounded without making changes",
    )

    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt and apply changes immediately",
    )

    args = parser.parse_args()
    today = datetime.today()

    # Default to the past 4 weeks (28 days) starting from today
    if not args.start and not args.end:
        four_weeks_ago = today - timedelta(days=28)
        args.start = int(four_weeks_ago.strftime("%Y%m%d"))
        args.end = int(today.strftime("%Y%m%d"))
    elif (args.start and not args.end) or (args.end and not args.start):
        print("Both --start and --end must be provided together", file=sys.stderr)
        sys.exit(1)

    return args


def format_hours(hours: Fraction) -> str:
    """Format hours as HH:MM."""
    total_minutes = int(hours * 60)
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}:{m:02d}"


def format_date(date_str: str) -> str:
    """Format date for display."""
    return date_str


def print_entry(entry: TimeEntry, show_diff: bool = True) -> None:
    """Print a time entry."""
    diff_str = ""
    if show_diff and entry.needs_rounding:
        diff_minutes = int(entry.difference * 60)
        diff_str = f" (+{diff_minutes}min)"

    print(
        f"  {entry.date} | {format_hours(entry.hours)} -> {format_hours(entry.rounded_hours)}{diff_str}"
    )
    print(f"           | {entry.client} / {entry.project} / {entry.task}")
    if entry.notes:
        notes = entry.notes[:60] + "..." if len(entry.notes) > 60 else entry.notes
        print(f"           | {notes}")


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Determine which user to filter by:
    # 1. --all-users: no filtering
    # 2. --user: use the specified user
    # 3. default: auto-discover the authenticated user
    filter_user = None
    if not args.all_users:
        if args.user:
            filter_user = args.user
        else:
            filter_user = get_current_user(
                args.harvest_account_id, args.harvest_bearer_token
            )
        print(f"Fetching time entries for {filter_user}...")

    print(f"Date range: {args.start} to {args.end}")
    entries = get_time_entries(
        args.harvest_account_id,
        args.harvest_bearer_token,
        args.start,
        args.end,
        args.increment,
    )

    # Filter by user unless --all-users is specified
    if filter_user:
        entries = [e for e in entries if e.user == filter_user]
        if not entries:
            print(f"No entries found for user: {filter_user}", file=sys.stderr)
            sys.exit(1)

    # Filter to only entries that need rounding
    to_round = [e for e in entries if e.needs_rounding]

    if not to_round:
        print("All entries are already rounded. Nothing to do.")
        return

    # Calculate totals
    total_original = sum((e.hours for e in to_round), Fraction(0))
    total_rounded = sum((e.rounded_hours for e in to_round), Fraction(0))
    total_added = total_rounded - total_original

    print(f"\nFound {len(to_round)} entries that need rounding:\n")

    # Group by user for display
    by_user: dict[str, list[TimeEntry]] = {}
    for entry in to_round:
        if entry.user not in by_user:
            by_user[entry.user] = []
        by_user[entry.user].append(entry)

    for user, user_entries in sorted(by_user.items()):
        print(f"User: {user}")
        user_entries.sort(key=lambda e: e.date)
        for entry in user_entries:
            print_entry(entry)
        print()

    print("Summary:")
    print(f"  Entries to round: {len(to_round)}")
    print(
        f"  Original total:   {format_hours(total_original)} ({float(total_original):.2f}h)"
    )
    print(
        f"  Rounded total:    {format_hours(total_rounded)} ({float(total_rounded):.2f}h)"
    )
    print(
        f"  Time added:       {format_hours(total_added)} ({float(total_added):.2f}h)"
    )
    print()

    if args.dry_run:
        print("Dry run mode - no changes made.")
        return

    # Confirm before applying
    if not args.yes:
        response = input("Apply these changes? [y/N] ")
        if response.lower() not in ("y", "yes"):
            print("Aborted.")
            return

    # Apply changes
    print("\nApplying changes...")
    success_count = 0
    error_count = 0

    for entry in to_round:
        try:
            update_time_entry(
                args.harvest_account_id,
                args.harvest_bearer_token,
                entry.id,
                entry.rounded_hours,
            )
            success_count += 1
            print(
                f"  Updated entry {entry.id}: {format_hours(entry.hours)} -> {format_hours(entry.rounded_hours)}"
            )
        except urllib.error.URLError as e:
            error_count += 1
            print(f"  Error updating entry {entry.id}: {e}", file=sys.stderr)

    print(f"\nDone. Updated {success_count} entries, {error_count} errors.")


if __name__ == "__main__":
    main()
