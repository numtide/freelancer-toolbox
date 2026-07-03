import csv
import json
import sys
from fractions import Fraction

from rich.console import Console
from rich.table import Table

from . import User


def round_cents(n: Fraction) -> float:
    """
    Use this method only for displaying currencies to avoid rounding errors
    """
    return float(round(n, 2))


def as_humanreadable(
    users: dict[str, User],
    start_date: int,
    end_date: int,
    currency: str,
) -> None:
    print(f"time: {start_date} -> {end_date}")
    for user_name, user in users.items():
        print(f"{user_name}:")
        currencies = {}
        for client_name, client in user.clients.items():
            for task_name, task in client.tasks.items():
                if task.currency != currency:
                    currencies[task.currency] = task.exchange_rate(currency)
                round_cents(task.cost)
                converted_cost = round_cents(task.converted_cost(currency))
                converted_hourly_rate = round_cents(
                    task.converted_hourly_rate(currency)
                )

                print(
                    f"  {client_name} - {task_name} ({float(round(task.hourly_rate, 2))} {task.currency}/h -> {converted_hourly_rate} {currency}/h): {float(task.rounded_hours)}h -> {converted_cost} {currency}"
                )
        print("Exchange rates")
        for source_currency, rate in currencies.items():
            print(f"1 {source_currency} -> {float(rate)} {currency}")


def as_csv(
    users: dict[str, User],
    start_date: int,
    end_date: int,
    currency: str,
) -> None:
    fieldnames = [
        "user",
        "start_date",
        "end_date",
        "agency",
        "client",
        "task",
        "rounded_hours",
        "source_cost",
        "source_currency",
        "source_hourly_rate",
        "target_cost",
        "target_currency",
        "target_hourly_rate",
        "exchange_rate",
    ]

    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    for user_name, user in users.items():
        for client_name, client in user.clients.items():
            for task_name, task in client.tasks.items():
                writer.writerow(
                    dict(
                        user=user_name,
                        start_date=start_date,
                        end_date=end_date,
                        agency=task.agency,
                        client=client_name,
                        task=task_name,
                        rounded_hours=float(task.rounded_hours),
                        source_hourly_rate=round_cents(task.hourly_rate),
                        source_cost=round_cents(task.cost),
                        source_currency=task.currency,
                        target_hourly_rate=round_cents(
                            task.converted_hourly_rate(currency)
                        ),
                        target_cost=round_cents(task.converted_cost(currency)),
                        target_currency=currency,
                        exchange_rate=float(task.exchange_rate(currency)),
                    )
                )


def as_json(
    users: dict[str, User],
    start_date: int,
    end_date: int,
    currency: str,
) -> None:
    data = []
    for user_name, user in users.items():
        for client_name, client in user.clients.items():
            for task_name, task in client.tasks.items():
                data.append(
                    dict(
                        user=user_name,
                        start_date=start_date,
                        end_date=end_date,
                        agency=task.agency,
                        client=client_name,
                        task=task_name,
                        rounded_hours=float(task.rounded_hours),
                        source_hourly_rate=round_cents(task.hourly_rate),
                        source_cost=round_cents(task.cost),
                        source_currency=task.currency,
                        target_hourly_rate=round_cents(
                            task.converted_hourly_rate(currency)
                        ),
                        target_cost=round_cents(task.converted_cost(currency)),
                        target_currency=currency,
                        exchange_rate=float(task.exchange_rate(currency)),
                    )
                )
    json.dump(data, sys.stdout, indent=4, sort_keys=True)


def as_rich_table(
    users: dict[str, User],
    start_date: int,
    end_date: int,
    currency: str,
) -> None:
    console = Console()

    table_title = f"Time Report: {start_date} to {end_date}"
    table = Table(title=table_title, show_header=True, header_style="bold magenta")
    table.add_column("User", style="dim")
    table.add_column("Client")
    table.add_column("Task")
    table.add_column("Hours", justify="right")
    table.add_column("Source Cost", justify="right")
    table.add_column("Source Rate/hr", justify="right")
    table.add_column("Target Cost (" + currency + ")", justify="right")
    table.add_column("Target Rate/hr (" + currency + ")", justify="right")
    table.add_column("Exchange Rate", justify="right")

    total_source_cost = 0.0
    total_target_cost = 0.0
    total_hours = 0.0

    for user_name, user in users.items():
        for client_name, client in user.clients.items():
            for task_name, task in client.tasks.items():
                source_cost = round_cents(task.cost)
                target_cost = round_cents(task.converted_cost(currency))
                task_hours = float(task.rounded_hours)

                total_source_cost += source_cost
                total_target_cost += target_cost
                total_hours += task_hours

                table.add_row(
                    user_name,
                    client_name,
                    task_name,
                    f"{task_hours:.2f}",
                    f"{source_cost:.2f} {task.currency}",
                    f"{round_cents(task.hourly_rate):.2f} {task.currency}/hr",
                    f"{target_cost:.2f} {currency}",
                    f"{round_cents(task.converted_hourly_rate(currency)):.2f} {currency}/hr",
                    f"1 {task.currency} = {round_cents(task.exchange_rate(currency)):.2f} {currency}",
                )

    # Add a separator
    table.add_row("", "", "", "", "", "", "", "", "", end_section=True)

    # Add the total row with bold style
    table.add_row(
        "Total",
        "",
        "",
        f"{total_hours:.2f}",
        f"{total_source_cost:.2f}",
        "",
        f"{total_target_cost:.2f}",
        "",
        "",
        style="bold",
    )

    console.print(table)
