"""Jinja2 rendering and WeasyPrint PDF generation."""

from __future__ import annotations

from pathlib import Path

from jinja2 import (
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

from harvest_invoicer.i18n import resolve_language, translator
from harvest_invoicer.model import (
    Invoice,
    fmt_date,
    fmt_money,
    fmt_qty,
    fmt_vat_cell,
)

_PACKAGED_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _build_jinja_env(
    date_format: str,
    user_templates_dir: Path | None = None,
) -> Environment:
    """Build the Jinja2 environment with a ChoiceLoader.

    When *user_templates_dir* is supplied the user's directory is searched
    first; the packaged ``templates/`` directory acts as the fallback.  This
    lets users override individual template files (e.g. ``invoice.html``)
    without replacing the entire set.

    The ``date_format`` comes from issuer.json ``date_format`` field (or the
    ISO-8601 default).  All template filters are registered here so the
    template files themselves stay free of logic.
    """
    loaders: list[FileSystemLoader] = []
    if user_templates_dir is not None:
        loaders.append(FileSystemLoader(str(user_templates_dir)))
    loaders.append(FileSystemLoader(str(_PACKAGED_TEMPLATES_DIR)))

    env = Environment(
        loader=ChoiceLoader(loaders),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    env.filters["money"] = fmt_money
    env.filters["qty"] = fmt_qty
    env.filters["fmtdate"] = lambda d: fmt_date(d, date_format)
    env.filters["vat_cell"] = fmt_vat_cell
    return env


def _effective_base_url(user_templates_dir: Path | None) -> str:
    """Return the directory WeasyPrint uses to resolve relative URLs (style.css).

    If the user supplies a custom templates directory and it contains
    ``style.css``, that file takes precedence.  Otherwise the packaged
    directory is used.
    """
    if user_templates_dir is not None and (user_templates_dir / "style.css").exists():
        return str(user_templates_dir)
    return str(_PACKAGED_TEMPLATES_DIR)


def render_html(
    invoice: Invoice,
    issuer: dict[str, object],
    client: dict[str, str],
    user_templates_dir: Path | None = None,
) -> str:
    """Render invoice.html to an HTML string.

    ``issuer`` is the parsed issuer.json dict; ``client`` is the per-client
    client record (already resolved by the CLI).

    When *user_templates_dir* is set the ChoiceLoader checks that directory
    first, falling back to the packaged templates.
    """
    date_format = str(issuer.get("date_format") or "%Y-%m-%d")
    env = _build_jinja_env(date_format, user_templates_dir)
    template = env.get_template("invoice.html")
    lang = resolve_language(client, issuer)
    return template.render(
        invoice=invoice,
        issuer=issuer,
        client=client,
        lang=lang,
        t=translator(lang),
    )


def render_pdf_bytes(
    invoice: Invoice,
    issuer: dict[str, object],
    client: dict[str, str],
    user_templates_dir: Path | None = None,
) -> bytes:
    """Render invoice to PDF via WeasyPrint and return the bytes.

    The HTML is rendered first via :func:`render_html`; WeasyPrint then
    converts it using ``base_url`` so that relative ``style.css`` links
    resolve correctly.  The user templates directory (if present) takes
    precedence over the packaged fallback for both HTML and CSS.
    """
    from weasyprint import HTML  # noqa: PLC0415
    from weasyprint.text.fonts import FontConfiguration  # noqa: PLC0415

    html_str = render_html(invoice, issuer, client, user_templates_dir)
    base_url = _effective_base_url(user_templates_dir)
    font_config = FontConfiguration()
    pdf = HTML(string=html_str, base_url=base_url).write_pdf(
        font_config=font_config,
    )
    # write_pdf returns bytes when no target is given; guard narrows the
    # untyped return for mypy and catches API changes.
    if not isinstance(pdf, bytes):  # pragma: no cover
        msg = "WeasyPrint returned no PDF data"
        raise TypeError(msg)
    return pdf


def render_pdf(
    invoice: Invoice,
    issuer: dict[str, object],
    client: dict[str, str],
    output_path: Path,
    user_templates_dir: Path | None = None,
) -> None:
    """Render invoice to PDF via WeasyPrint, writing to ``output_path``."""
    output_path.write_bytes(
        render_pdf_bytes(invoice, issuer, client, user_templates_dir)
    )
