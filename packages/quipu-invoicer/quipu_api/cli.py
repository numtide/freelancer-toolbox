from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import click
from click_option_group import optgroup

from quipu_api import QuipuAPI, QuipuResponse


def pprint(data: Any) -> None:
    if isinstance(data, QuipuResponse):
        data = data.to_dict()
    print(json.dumps(data, indent=4))


def load_invoice_data(
    ctx: click.Context, param: click.Parameter, value: str | None
) -> Any:
    if value is not None:
        return json.loads(Path(value).read_text())
    return None


def set_log_level(ctx: click.Context, param: click.Parameter, value: str) -> str:
    if value:
        logging.basicConfig(
            level=getattr(logging, value.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    return value


@click.group()
@optgroup.group("API Credentials", help="Quipu API credentials")
@optgroup.option(
    "--quipu-app-id",
    envvar="QUIPU_APP_ID",
    required=True,
    help="Application ID for Quipu API.",
)
@optgroup.option(
    "--quipu-app-secret",
    envvar="QUIPU_APP_SECRET",
    required=True,
    help="Application Secret for Quipu API.",
)
@click.option(
    "--log-level",
    default="INFO",
    callback=set_log_level,
    expose_value=False,
    is_eager=True,
    help="Set the logging level (e.g., DEBUG, INFO, WARNING, ERROR, CRITICAL)",
)
@click.pass_context
def cli(ctx: click.Context, quipu_app_id: str, quipu_app_secret: str) -> None:
    """Interact with Quipu API."""
    ctx.obj = QuipuAPI(quipu_app_id, quipu_app_secret)


@cli.group()
def invoices() -> None:
    """Commands related to invoices."""


@invoices.command(name="list")
@click.option("--page", default=1, help="Page number.")
@click.pass_obj
def list_invoices(quipu_api: QuipuAPI, page: int) -> None:
    """List all invoices."""
    pprint(quipu_api.list_invoices(page))


@invoices.command(name="get")
@click.argument("invoice_id")
@click.pass_obj
def get_invoice(quipu_api: QuipuAPI, invoice_id: str) -> None:
    """Get a specific invoice."""
    pprint(quipu_api.get_invoice(invoice_id))


@invoices.command(name="create")
@click.argument(
    "invoice_data", type=click.Path(exists=True), callback=load_invoice_data
)
@click.pass_obj
def create_invoice(quipu_api: QuipuAPI, invoice_data: dict) -> None:
    """Create a new invoice."""
    pprint(quipu_api.create_invoice(invoice_data))


@invoices.command(name="edit")
@click.argument("invoice_id")
@click.argument(
    "invoice_data", type=click.Path(exists=True), callback=load_invoice_data
)
@click.pass_obj
def edit_invoice(quipu_api: QuipuAPI, invoice_id: str, invoice_data: dict) -> None:
    """Edit an existing invoice."""
    pprint(quipu_api.update_invoice(invoice_id, invoice_data))


@cli.group()
def contacts() -> None:
    """Commands related to contacts."""


@contacts.command(name="list")
@click.option("--page", default=1, help="Page number.")
@click.pass_obj
def list_contacts(quipu_api: QuipuAPI, page: int) -> None:
    """List all contacts."""
    pprint(quipu_api.list_contacts(page))


@contacts.command(name="get")
@click.argument("contact_id", type=int)
@click.pass_obj
def get_contact(quipu_api: QuipuAPI, contact_id: str) -> None:
    """Get a specific contact by its ID."""
    pprint(quipu_api.get_contact(contact_id))


if __name__ == "__main__":
    cli()
