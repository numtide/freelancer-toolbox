import json
from datetime import datetime
from pathlib import Path

import click
from quipu_api import QuipuAPI


@click.command()
@click.option("--quipu-app-id", envvar="QUIPU_APP_ID", required=True)
@click.option(
    "--quipu-app-secret",
    envvar="QUIPU_APP_SECRET",
    required=True,
)
@click.option(
    "--customer", default=5458533, show_default=True, type=int, help="Customer ID"
)
@click.option("--invoice-number", type=str, help="Invoice number")
@click.option(
    "--accounting-category",
    default=133,
    show_default=True,
    type=int,
    help="Accounting category Id",
)
@click.option(
    "--vat-percent", default=0, show_default=True, type=int, help="VAT percentage"
)
@click.option(
    "--issue-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Issue date in YYYY-MM-DD format",
)
@click.option(
    "--due-date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Due date in YYYY-MM-DD format",
)
@click.option(
    "--notes",
    default="Factura exenta de IVA por aplicación artículo 25 Ley IVA de 1992.",
    show_default=True,
)
@click.argument("json_file", type=click.Path(exists=True))
def main(
    quipu_app_id: str,
    quipu_app_secret: str,
    customer: int,
    invoice_number: str,
    accounting_category: int,
    vat_percent: int,
    issue_date: datetime,
    due_date: datetime,
    notes: str,
    json_file: str,
) -> None:
    tasks = json.loads(Path(json_file).read_text())

    create_invoice(
        quipu_app_id,
        quipu_app_secret,
        tasks,
        customer,
        invoice_number,
        accounting_category,
        vat_percent,
        issue_date or datetime.now(),
        due_date or datetime.now(),
        notes,
    )


def create_invoice(
    app_id: str,
    app_secret: str,
    tasks: list[dict],
    customer_id: int,
    invoice_number: str,
    accounting_category_id: int,
    vat_percent: int,
    issue_date: datetime,
    due_date: datetime,
    notes: str,
) -> None:
    quipu_api = QuipuAPI(app_id=app_id, app_secret=app_secret)

    items_data = [
        {
            "type": "book_entry_items",
            "attributes": {
                "concept": f"{task['client']} - {task['task']}",
                "unitary_amount": str(task["target_hourly_rate"]),
                "quantity": task["rounded_hours"],
                "vat_percent": vat_percent,
                "retention_percent": 0,
            },
        }
        for task in tasks
        if validate_task(task)
    ]

    invoice_data = {
        "data": {
            "type": "invoices",
            "attributes": {
                "kind": "income",
                "number": invoice_number,
                "issue_date": issue_date.strftime("%Y-%m-%d"),
                "due_date": due_date.strftime("%Y-%m-%d"),
                "paid_at": None,
                "payment_method": "bank_transfer",
                "notes": notes,
            },
            "relationships": {
                "contact": {"data": {"id": customer_id, "type": "contacts"}},
                "accounting_category": {
                    "data": {
                        "id": accounting_category_id,
                        "type": "accounting_categories",
                    }
                },
                "items": {"data": items_data},
            },
        }
    }

    quipu_api.create_invoice(invoice_data)


def validate_task(task: dict) -> bool:
    required_keys = ["client", "task", "target_hourly_rate", "rounded_hours"]
    return all(key in task for key in required_keys)


if __name__ == "__main__":
    main()
