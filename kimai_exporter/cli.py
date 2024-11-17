#!/usr/bin/env python3

import argparse
import calendar
import json
import os
import sys
from datetime import datetime, timedelta
from fractions import Fraction

import kimai
import kimai.api
from harvest_exporter.transferwise import exchange_rate as get_exchange_rate
from kimai.data import ProjectInfo, TimeEntry, UserInfo
from kimai.jsonserializer import JsonEncoder

from . import ProjectReport


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


def main() -> None:
    args = parse_args()
    api = kimai.api.KimaiAPI(args.kimai_api_key, args.api_url)
    projects = api.get_visible_projects()

    # Get user info
    users_data = api.get_visible_users()
    users_data = list(
        filter(
            lambda user: user["username"] == args.user or user["alias"] == args.user,
            users_data,
        )
    )
    if len(users_data) < 1:
        raise Exception(f"User {args.user} not found")
    if len(users_data) > 1:
        raise Exception(f"Multiple users found for {args.user}")
    user = UserInfo.from_json(users_data[0])

    all_reports: list[ProjectReport] = []
    for project_data in projects:
        project = ProjectInfo.from_json(project_data)
        customer = api.get_customer(project.customer)
        if customer.name != args.client:
            continue
        total_seconds = Fraction(0)
        total_rate = Fraction(0)
        total_internal_rate = Fraction(0)
        tasks = set()

        for entry_data in api.get_time_entries(
            args.start, args.end, user.id, project.id
        ):
            entry = TimeEntry.from_json(entry_data)
            activity = api.get_activity(entry.activity)
            tasks.add(activity.name)
            total_seconds += entry.duration
            total_rate += entry.rate
            total_internal_rate += entry.internalRate

        hourly_rate = api.get_time_entry(user.id).hourlyRate

        rounded_hours = round(total_seconds / 60 / 60, 2)
        exchange_rate = get_exchange_rate(customer.currency, args.currency)
        report = ProjectReport(
            agency=args.agency,
            client=customer.name,
            end_date=args.end.strftime("%Y%m%d"),
            exchange_rate=float(exchange_rate),
            rounded_hours=rounded_hours,
            source_cost=total_rate,
            source_currency=customer.currency,
            source_hourly_rate=hourly_rate,
            start_date=args.start.strftime("%Y%m%d"),
            target_cost=total_rate * exchange_rate,
            target_currency=args.currency,
            target_hourly_rate=hourly_rate * exchange_rate,
            task=",".join(tasks),
            user=user.alias,
        )
        all_reports.append(report)

    print(json.dumps(all_reports, indent=2, cls=JsonEncoder))


if __name__ == "__main__":
    main()
