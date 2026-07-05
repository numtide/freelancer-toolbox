"""End-to-end demo script: starts the Flask editor in demo mode and probes
key endpoints, then generates a PDF headlessly via the generate command.

Run with:
    python tests/e2e_demo.py
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

_PACKAGE_DIR = Path(__file__).parent.parent
_FLAKE_DIR = _PACKAGE_DIR.parent.parent  # repo root (has flake.nix)
_STATIC_DIR = _PACKAGE_DIR / "src" / "harvest_invoicer" / "static"
_EXAMPLES_DIR = _PACKAGE_DIR / "src" / "harvest_invoicer" / "examples"
_PORT = 18321


def _wait_for_server(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
        else:
            return
    msg = f"Server did not start within {timeout}s"
    raise RuntimeError(msg)


def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def run() -> None:
    ok = True

    # ------------------------------------------------------------------
    # 1. Start the editor in demo mode (background thread via Flask test
    #    client to avoid needing a real TCP port on CI, but here we use
    #    the real server on localhost so the URL fetch is realistic).
    # ------------------------------------------------------------------
    print("Starting demo editor server…")
    sys.path.insert(0, str(_PACKAGE_DIR / "src"))

    from harvest_invoicer.app import create_app  # noqa: PLC0415
    from harvest_invoicer.fetch import (  # noqa: PLC0415
        load_clients,
        load_issuer,
        make_demo_lines,
        resolve_client,
        resolve_invoice_number,
    )

    issuer = load_issuer(str(_EXAMPLES_DIR / "issuer.example.json"))
    clients = load_clients(str(_EXAMPLES_DIR / "clients.example.json"))
    lines = make_demo_lines()
    client_entry = resolve_client(None, clients, lines)
    number = resolve_invoice_number("2026-06")

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(
            lines,
            issuer,
            client_entry,
            number,
            Path(tmp) / "invoice-demo.pdf",
        )

        server_thread = threading.Thread(
            target=lambda: app.run(
                host="127.0.0.1", port=_PORT, debug=False, use_reloader=False
            ),
            daemon=True,
        )
        server_thread.start()
        base = f"http://127.0.0.1:{_PORT}"
        _wait_for_server(f"{base}/")

        # ------------------------------------------------------------------
        # 2. Check editor root
        # ------------------------------------------------------------------
        status, _body = _get(f"{base}/")
        if status == 200:
            print(f"  [PASS] GET /           -> {status}")
        else:
            print(f"  [FAIL] GET /           -> {status}")
            ok = False

        # ------------------------------------------------------------------
        # 3. /static/htmx.min.js — bytes must equal the packaged file
        # ------------------------------------------------------------------
        packaged = (_STATIC_DIR / "htmx.min.js").read_bytes()
        status, data = _get(f"{base}/static/htmx.min.js")
        if status == 200 and data == packaged:
            print(
                f"  [PASS] GET /static/htmx.min.js -> {status}, bytes match packaged file"
            )
        else:
            print(
                f"  [FAIL] GET /static/htmx.min.js -> status={status}, "
                f"bytes_match={data == packaged}"
            )
            ok = False

        # ------------------------------------------------------------------
        # 4. /style.css — 200, non-empty CSS
        # ------------------------------------------------------------------
        status, data = _get(f"{base}/style.css")
        if status == 200 and b"table.items" in data:
            print(f"  [PASS] GET /style.css  -> {status}, contains 'table.items'")
        else:
            print(
                f"  [FAIL] GET /style.css  -> status={status}, body[:80]={data[:80]!r}"
            )
            ok = False

        # ------------------------------------------------------------------
        # 5. /favicon.ico — 204
        # ------------------------------------------------------------------
        try:
            with urllib.request.urlopen(f"{base}/favicon.ico") as resp:
                fav_status = resp.status
        except urllib.error.HTTPError as exc:
            fav_status = exc.code
        if fav_status == 204:
            print(f"  [PASS] GET /favicon.ico -> {fav_status}")
        else:
            print(f"  [FAIL] GET /favicon.ico -> {fav_status}")
            ok = False

        # ------------------------------------------------------------------
        # 6. /preview — 200
        # ------------------------------------------------------------------
        status, data = _get(f"{base}/preview")
        if status == 200:
            print(f"  [PASS] GET /preview    -> {status}")
        else:
            print(f"  [FAIL] GET /preview    -> {status}")
            ok = False

    # ------------------------------------------------------------------
    # 7. PDF generation via nix run (demo mode, no Harvest credentials)
    # ------------------------------------------------------------------
    print("Running headless PDF generation in demo mode via nix run…")
    with tempfile.TemporaryDirectory() as out_dir:
        result = subprocess.run(
            [
                "nix",
                "run",
                f"{_FLAKE_DIR}#harvest-invoicer",
                "--",
                "generate",
                "--demo",
                "--month",
                "2026-06",
                "--output-dir",
                out_dir,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        pdf = Path(out_dir) / "invoice-2026-06.pdf"
        if result.returncode == 0 and pdf.exists() and pdf.stat().st_size > 1000:
            print(
                f"  [PASS] generate --demo produced {pdf.name} ({pdf.stat().st_size} bytes)"
            )
        else:
            print(
                f"  [FAIL] generate --demo rc={result.returncode} "
                f"pdf_exists={pdf.exists()}\n"
                f"  stdout: {result.stdout.strip()}\n"
                f"  stderr: {result.stderr.strip()[:500]}"
            )
            ok = False

    # ------------------------------------------------------------------
    # 8. Wheel content: NOTICE + js present
    # ------------------------------------------------------------------
    notice = _STATIC_DIR / "htmx.min.js.NOTICE"
    js = _STATIC_DIR / "htmx.min.js"
    if notice.exists() and js.exists():
        sha = hashlib.sha256(js.read_bytes()).hexdigest()
        notice_text = notice.read_text(encoding="utf-8")
        expected_sha = next(
            (
                line.split(":", 1)[1].strip()
                for line in notice_text.splitlines()
                if line.startswith("SHA-256:")
            ),
            None,
        )
        if sha == expected_sha:
            print(f"  [PASS] NOTICE sha256 matches htmx.min.js ({sha[:16]}…)")
        else:
            print(f"  [FAIL] NOTICE sha256 mismatch: {sha} vs {expected_sha}")
            ok = False
    else:
        print("  [FAIL] NOTICE or htmx.min.js missing from static dir")
        ok = False

    print()
    if ok:
        print("All e2e checks passed.")
    else:
        print("Some e2e checks FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    run()
