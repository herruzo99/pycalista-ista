#!/usr/bin/env python3
"""End-to-end smoke test / usage example for pycalista-ista.

Connects to the real Ista Calista portal, fetches device history for a date
range, and prints a summary of each device.

Usage:
    export ISTA_EMAIL="your@email.com"
    export ISTA_PASSWORD="your_password"
    python example.py

Optional environment variables:
    ISTA_START_DATE   ISO date string (e.g. 2025-01-01).  Defaults to 30 days ago.
    ISTA_END_DATE     ISO date string (e.g. 2025-01-31).  Defaults to today.
    ISTA_LOG_LEVEL    DEBUG | INFO | WARNING | ERROR.     Defaults to INFO.
"""

import asyncio
import logging
import os
import sys
from datetime import date, timedelta

import aiohttp

from pycalista_ista import IstaConnectionError, IstaLoginError, PyCalistaIsta
from pycalista_ista.const import INCIDENCE_NAMES
from pycalista_ista.models import ColdWaterDevice, HeatingDevice, HotWaterDevice

_DEVICE_ICONS = {
    HeatingDevice: "🔥",
    HotWaterDevice: "🚿",
    ColdWaterDevice: "💧",
}


def _parse_date(env_var: str, fallback: date) -> date:
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return fallback
    try:
        return date.fromisoformat(raw)
    except ValueError:
        print(f"WARNING: Invalid date in {env_var}={raw!r}, using {fallback}")
        return fallback


async def main() -> int:
    log_level = os.environ.get("ISTA_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    email = os.environ.get("ISTA_EMAIL", "").strip()
    password = os.environ.get("ISTA_PASSWORD", "").strip()

    if not email or not password:
        print(
            "ERROR: Set the ISTA_EMAIL and ISTA_PASSWORD environment variables.\n"
            "  export ISTA_EMAIL='your@email.com'\n"
            "  export ISTA_PASSWORD='yourpassword'",
            file=sys.stderr,
        )
        return 1

    today = date.today()
    start = _parse_date("ISTA_START_DATE", today - timedelta(days=30))
    end = _parse_date("ISTA_END_DATE", today)

    from pycalista_ista import VERSION

    print(f"Account  : {email}")
    print(f"Period   : {start} → {end}  ({(end - start).days + 1} days)")
    print(f"Version  : pycalista-ista {VERSION}")
    print()

    async with aiohttp.ClientSession() as session:
        async with PyCalistaIsta(email, password, session=session) as client:
            print("Logging in…", end=" ", flush=True)
            try:
                await client.login()
            except IstaLoginError as exc:
                print(f"FAILED\nLogin error: {exc}", file=sys.stderr)
                return 1
            except IstaConnectionError as exc:
                print(f"FAILED\nConnection error: {exc}", file=sys.stderr)
                return 1
            print("OK")

            print("Fetching device history…", end=" ", flush=True)
            try:
                devices = await client.get_devices_history(start, end)
            except (IstaConnectionError, IstaLoginError) as exc:
                print(f"FAILED\n{exc}", file=sys.stderr)
                return 1
            print(f"OK  ({len(devices)} devices)\n")

            print("Fetching invoices…", end=" ", flush=True)
            try:
                invoices = await client.get_invoices()
            except (IstaConnectionError, IstaLoginError) as exc:
                print(f"FAILED\n{exc}", file=sys.stderr)
                return 1
            print(f"OK  ({len(invoices)} invoices)\n")

            print("Fetching invoice XLS…", end=" ", flush=True)
            try:
                invoice_xls = await client.get_invoice_xls()
            except (IstaConnectionError, IstaLoginError) as exc:
                print(f"FAILED\n{exc}", file=sys.stderr)
                return 1
            print(f"OK  ({len(invoice_xls)} rows)\n")

            print("Fetching billed consumption…", end=" ", flush=True)
            try:
                billed = await client.get_billed_consumption()
            except (IstaConnectionError, IstaLoginError) as exc:
                print(f"FAILED\n{exc}", file=sys.stderr)
                return 1
            print(f"OK  ({len(billed)} readings)\n")

    # ── Summary table ────────────────────────────────────────────────────────
    col = "{:<3} {:<10} {:<20} {:<28} {:>8}  {}"
    print(col.format("", "Serial", "Type", "Location", "Readings", "Last reading"))
    print("-" * 80)

    for serial, device in sorted(devices.items()):
        icon = _DEVICE_ICONS.get(type(device), "?")
        type_name = type(device).__name__.replace("Device", "")
        location = (device.location or "(no location)")[:27]
        n_readings = len(device.history)

        last = device.last_reading
        if last and last.reading is not None:
            last_str = f"{last.reading:.3f}  ({last.date.date()})"
        else:
            last_str = "N/A"

        print(col.format(icon, serial, type_name, location, n_readings, last_str))

    print()

    # ── Consumption summary ──────────────────────────────────────────────────
    print("Consumption (last two readings):")
    for serial, device in sorted(devices.items()):
        consumption = device.last_consumption
        if consumption is not None and consumption.reading is not None:
            print(f"  {serial:12s}  {consumption.reading:+.3f}")

    print()

    # ── Invoices (HTML listing) ───────────────────────────────────────────────
    inv_col = "{:<12}  {:<38}  {:>10}  {}"
    print(inv_col.format("Date", "Type", "Amount", "ID"))
    print("-" * 80)
    for inv in invoices:
        inv_date = inv.invoice_date.isoformat() if inv.invoice_date else "N/A"
        device_type = (inv.device_type or "N/A")[:37]
        amount = f"{inv.amount:.2f} €" if inv.amount is not None else "N/A"
        print(inv_col.format(inv_date, device_type, amount, inv.invoice_id))

    # ── Invoice XLS export ────────────────────────────────────────────────────
    print()
    xls_col = "{:<12}  {:<38}  {:>10}"
    print(xls_col.format("Date", "Type", "Amount"))
    print("-" * 65)
    for inv in invoice_xls:
        inv_date = inv.invoice_date.isoformat() if inv.invoice_date else "N/A"
        device_type = (inv.device_type or "N/A")[:37]
        amount = f"{inv.amount:.2f} €" if inv.amount is not None else "N/A"
        print(xls_col.format(inv_date, device_type, amount))

    # ── Billed consumption ───────────────────────────────────────────────────
    print()
    bc_col = "{:<12}  {:<12}  {:>12}  {:>12}  {:>12}  {:<6}  {}"
    print(
        bc_col.format(
            "Serial", "Date", "Previous", "Current", "Consumption", "Unit", "Incidence"
        )
    )
    print("-" * 80)
    # Show last reading per device
    seen: set[str] = set()
    for r in billed:
        if r.serial_number not in seen:
            seen.add(r.serial_number)
            est = " (est.)" if r.is_estimated else ""
            print(
                bc_col.format(
                    r.serial_number,
                    r.date.isoformat(),
                    f"{r.previous_reading:.3f}",
                    f"{r.current_reading:.3f}",
                    f"{r.consumption:.3f}",
                    r.unit,
                    r.incidence + est,
                )
            )

    # ── Incidence code inventory (for mapping unknown codes) ─────────────────
    print()
    print("Incidence codes seen across all billed readings:")
    inc_col = "{:<10}  {:<6}  {:<28}  {}"
    print(inc_col.format("Code", "Count", "Name", "Example serial  (date)"))
    print("-" * 72)
    from collections import Counter

    inc_counter: Counter[str] = Counter()
    inc_example: dict[str, tuple[str, str]] = {}
    for r in billed:
        inc_counter[r.incidence] += 1
        if r.incidence not in inc_example:
            inc_example[r.incidence] = (r.serial_number, r.date.isoformat())
    for code, count in sorted(inc_counter.items()):
        serial, dt = inc_example[code]
        name = INCIDENCE_NAMES.get(code, "*** UNKNOWN ***")
        print(inc_col.format(code, count, name, f"{serial}  ({dt})"))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
