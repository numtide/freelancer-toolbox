#!/usr/bin/env python3

import argparse
import calendar
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction

import kimai
import kimai.api
from harvest_exporter.transferwise import exchange_rate as get_exchange_rate
from kimai.data import JsonSerializable, ProjectInfo, TimeEntry, UserInfo
from kimai.jsonserializer import JsonEncoder

from . import ProjectReport


class Error(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    token = os.environ.get("KIMAI_API_KEY")
    parser.add_argument(
        "--kimai-api-key",
        default=token,
        required=token is None,
        help="Get one from your kimai account (env: KIMAI_API_KEY)",
    )
    api_url = os.environ.get("KIMAI_API_URL")
    parser.add_argument(
        "--api-url",
        default=api_url,
        required=api_url is None,
        help="Kimai API URL (env: KIMAI_API_URL)",
    )
    user = os.environ.get("KIMAI_USER")
    parser.add_argument(
        "--user",
        type=str,
        default=user,
        required=user is None,
        help="user to filter for (env: KIMAI_USER)",
    )
    parser.add_argument(
        "--start",
        type=lambda s: datetime.strptime(s + "T00:00:00", "%Y-%m-%dT%H:%M:%S"),
        help="Start date i.e. YYYY-MM-DD",
    )
    parser.add_argument(
        "--end",
        type=lambda s: datetime.strptime(s + "T00:00:00", "%Y-%m-%dT%H:%M:%S"),
        help="End date i.e. YYYY-MM-DD",
    )
    parser.add_argument(
        "--month",
        type=int,
        choices=range(1, 13),
        help="Month to generate report for (conflicts with `--start` and `--end`)",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Year to generate report for (conflicts with `--start` and `--end`)",
    )
    parser.add_argument(
        "--client",
        type=str,
        required=True,
        help="Export report for this client only",
    )
    parser.add_argument(
        "--agency",
        type=str,
        help="Agency name",
    )
    parser.add_argument(
        "--currency",
        default="EUR",
        type=str,
        help="Target currency to convert to, i.e EUR",
    )
    args = parser.parse_args()
    today = datetime.today()
    if args.month and (args.start or args.end):
        print("--month flag conflicts with --start and --end", file=sys.stderr)
        sys.exit(1)
    if args.month:
        year = today.year
        if args.year:
            year = args.year
        _, last_day = calendar.monthrange(year, args.month)
        args.start = datetime(year, args.month, 1, 0, 0, 0)
        args.end = datetime(year, args.month, last_day, 23, 59, 59)
    elif (args.start and not args.end) or (args.end and not args.start):
        print("both --start and --end flag must be passed", file=sys.stderr)
        sys.exit(1)
    elif not args.start and not args.end:
        # Show the previous month by default
        start_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_of_previous_month = start_of_month - timedelta(days=1)
        start_of_previous_month = end_of_previous_month.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        args.start = start_of_previous_month
        args.end = end_of_previous_month.replace(
            hour=23, minute=59, second=59, microsecond=999999
        )

    return args


@dataclass
class ReportOptions(JsonSerializable):
    kimai_api_key: str
    api_url: str
    user: str
    start: datetime
    end: datetime
    client: str
    agency: str
    currency: str


def generate_report(options: ReportOptions) -> None:
    api = kimai.api.KimaiAPI(options.kimai_api_key, options.api_url)
    projects = api.get_visible_projects()

    # Get user info
    users_data = api.get_visible_users()
    users_data = list(
        filter(
            lambda user: user["username"] == options.user
            or user["alias"] == options.user,
            users_data,
        )
    )
    if len(users_data) < 1:
        msg = f"User {options.user} not found"
        raise Error(msg)
    if len(users_data) > 1:
        msg = f"Multiple users found for {options.user}"
        raise Error(msg)
    user = UserInfo.from_json(users_data[0])

    all_reports: list[ProjectReport] = []
    for project_data in projects:
        project = ProjectInfo.from_json(project_data)
        customer = api.get_customer(project.customer)
        print(
            f"Project name: {project.name}. Customer name: {customer.name}",
            file=sys.stderr,
        )
        if customer.name != options.client:
            continue

        # Group entries by activity so each activity becomes its own
        # invoice line (different hourly rates and tasks shouldn't be
        # collapsed into a single line). Within an activity we still sum
        # across all matching timesheets in the period.
        per_activity: dict[int, dict[str, Fraction]] = {}
        for entry_data in api.get_time_entries(
            options.start, options.end, user.id, customer.id, project_id=project.id
        ):
            entry = TimeEntry.from_json(entry_data)
            bucket = per_activity.setdefault(
                entry.activity,
                {"seconds": Fraction(0), "rate": Fraction(0)},
            )
            bucket["seconds"] += entry.duration
            bucket["rate"] += entry.rate

        if not per_activity:
            continue

        exchange_rate = get_exchange_rate(customer.currency, options.currency)

        for activity_id, bucket in per_activity.items():
            total_seconds = bucket["seconds"]
            total_rate = bucket["rate"]
            if total_seconds == 0:
                continue
            activity = api.get_activity(activity_id)

            # Derive the effective hourly rate from the entries we just
            # summed. Kimai's per-timesheet `rate` already reflects the
            # user/activity/project-specific rate; the user endpoint does
            # not expose a single hourly rate.
            hourly_rate = total_rate / (Fraction(total_seconds) / 3600)

            # Round hours to 2 decimals (matches Kimai's UI granularity)
            # and report cost as hours * rate so the downstream invoice
            # line (`hours @ rate`) reproduces the same total. Log any
            # drift between the rounded value and the actual sum so it
            # doesn't go unnoticed.
            orig_hours = Fraction(total_seconds) / 3600
            rounded_hours = round(orig_hours, 2)
            time_err = round(orig_hours - rounded_hours, 4)
            if time_err < 0:
                print(
                    f"{project.name}/{activity.name}: Time lost: {float(time_err)} hours",
                    file=sys.stderr,
                )
            elif time_err > 0:
                print(
                    f"{project.name}/{activity.name}: Time gained: {float(time_err)} hours",
                    file=sys.stderr,
                )

            target_hourly_rate = hourly_rate * exchange_rate
            if project.name in customer.name or customer.name in project.name:
                task = activity.name
            else:
                task = f"{project.name}: {activity.name}"

            all_reports.append(
                ProjectReport(
                    agency=options.agency,
                    client=customer.name,
                    end_date=options.end.strftime("%Y%m%d"),
                    exchange_rate=float(exchange_rate),
                    rounded_hours=rounded_hours,
                    source_cost=rounded_hours * hourly_rate,
                    source_currency=customer.currency,
                    source_hourly_rate=hourly_rate,
                    start_date=options.start.strftime("%Y%m%d"),
                    target_cost=rounded_hours * target_hourly_rate,
                    target_currency=options.currency,
                    target_hourly_rate=target_hourly_rate,
                    task=task,
                    user=user.alias,
                )
            )

    print(json.dumps(all_reports, indent=2, cls=JsonEncoder))


def main() -> None:
    args = parse_args()
    options = ReportOptions(
        kimai_api_key=args.kimai_api_key,
        api_url=args.api_url,
        user=args.user,
        start=args.start,
        end=args.end,
        client=args.client,
        agency=args.agency,
        currency=args.currency,
    )
    try:
        generate_report(options)
    except Exception:
        print(f"Failed to generate report for {options.client}", file=sys.stderr)
        print(json.dumps(options, indent=2, cls=JsonEncoder), file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
