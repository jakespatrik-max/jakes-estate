"""
Booking.com invoice & statement downloader
Downloads PDF invoice and reservations statement for the previous month.
Sends results via Gmail SMTP. Credentials from environment variables.
"""

import asyncio
import os
import smtplib
import calendar
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext

# ── Configuration ─────────────────────────────────────────────────────────────

PROPERTIES = [
    {
        "hotel_id": "14881473",
        "name": "New Modern Art Loft Apartment",
        "to": "jakes.estate@moneyq.cz",
        "cc": "jakes.patrik@gmail.com",
    },
    {
        "hotel_id": "14234560",
        "name": "Baroque Grand Apartment XXL",
        "to": "jakes.residential@moneyq.cz",
        "cc": "jakes.patrik@gmail.com",
    },
]

BOOKING_USERNAME  = os.environ["BOOKING_USERNAME"]
BOOKING_PASSWORD  = os.environ["BOOKING_PASSWORD"]
GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

SCREENSHOTS_DIR = Path("screenshots")
DOWNLOADS_DIR   = Path("downloads")

# Previous month
_today      = date.today()
_first_this = _today.replace(day=1)
_last_prev  = _first_this - timedelta(days=1)
PREV_MONTH  = _last_prev.month
PREV_YEAR   = _last_prev.year
# Period label as shown on Booking.com, e.g. "Mar 1 - Mar 31"
_month_abbr  = _last_prev.strftime("%b")   # "Mar"
_last_day    = calendar.monthrange(PREV_YEAR, PREV_MONTH)[1]
PERIOD_LABEL = f"{_month_abbr} 1 - {_month_abbr} {_last_day}"  # "Mar 1 - Mar 31"
PREV_MONTH_LABEL = _last_prev.strftime("%B %Y")                  # "March 2026"

BASE = "https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_dirs():
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    DOWNLOADS_DIR.mkdir(exist_ok=True)


async def _screenshot(page: Page, name: str):
    path = SCREENSHOTS_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"  [screenshot] {path}")


# ── Login ──────────────────────────────────────────────────────────────────────

async def _login(page: Page):
    print("Logging in...")
    await page.goto("https://account.booking.com/sign-in", wait_until="domcontentloaded")
    await page.fill('input[name="username"]', BOOKING_USERNAME)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")
    await page.fill('input[name="password"]', BOOKING_PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")
    print(f"  Logged in: {page.url}")


# ── Navigate to property ───────────────────────────────────────────────────────

async def _open_property(page: Page, hotel_id: str):
    """Click on the property in the groups home to set the session context."""
    await page.goto(
        "https://admin.booking.com/hotel/hoteladmin/groups/home/index.html",
        wait_until="networkidle"
    )
    # Click on the row with the matching hotel_id
    link = page.locator(f'text="{hotel_id}"').first
    await link.wait_for(timeout=10_000)
    await link.click()
    await page.wait_for_load_state("networkidle")
    print(f"  Opened property {hotel_id}: {page.url}")


# ── Invoice (PDF) ──────────────────────────────────────────────────────────────

async def _download_invoice(page: Page, hotel_id: str) -> Path | None:
    """
    Finance -> Documents and invoices -> find row matching previous month -> download PDF.
    """
    print(f"  Navigating to invoices...")
    await page.goto(f"{BASE}/finance_invoices.html", wait_until="networkidle")
    await _screenshot(page, f"invoices_{hotel_id}")

    # Find table row matching period label, e.g. "Mar 1 - Mar 31"
    row = page.locator("tr").filter(has_text=PERIOD_LABEL).first
    try:
        await row.wait_for(timeout=8_000)
    except Exception:
        await _screenshot(page, f"invoice_not_found_{hotel_id}")
        print(f"  No invoice found for period: {PERIOD_LABEL}")
        return None

    # Click PDF download link in that row
    pdf_link = row.locator('a:has-text("PDF")')
    dest = DOWNLOADS_DIR / f"invoice_{hotel_id}_{PREV_YEAR}_{PREV_MONTH:02d}.pdf"
    try:
        async with page.expect_download(timeout=15_000) as dl_info:
            await pdf_link.click()
        dl = await dl_info.value
        await dl.save_as(str(dest))
        print(f"  Invoice saved: {dest}")
        return dest
    except Exception as exc:
        await _screenshot(page, f"invoice_download_error_{hotel_id}")
        print(f"  Invoice download error: {exc}")
        return None


# ── Reservations statement ─────────────────────────────────────────────────────

async def _download_statement(page: Page, hotel_id: str) -> Path | None:
    """
    Finance -> Reservations statement -> select period -> Generate statement -> download.
    """
    print(f"  Navigating to reservations statement...")
    await page.goto(
        f"{BASE}/finance_reservations.html?hotel_id={hotel_id}",
        wait_until="networkidle"
    )
    await _screenshot(page, f"statement_{hotel_id}")

    # Select the correct period from the dropdown
    period_select = page.locator('select').first
    try:
        # Try selecting by visible text matching period label
        await period_select.select_option(label=PERIOD_LABEL, timeout=5_000)
        await page.wait_for_load_state("networkidle")
    except Exception:
        # Dropdown might already show the right period (latest = previous month)
        current = await period_select.input_value()
        print(f"  Period dropdown current value: {current} (wanted: {PERIOD_LABEL})")

    await _screenshot(page, f"statement_period_selected_{hotel_id}")

    # Save page as PDF (equivalent to "Print this page")
    dest = DOWNLOADS_DIR / f"statement_{hotel_id}_{PREV_YEAR}_{PREV_MONTH:02d}.pdf"
    try:
        pdf_bytes = await page.pdf(format="A4", print_background=True)
        dest.write_bytes(pdf_bytes)
        print(f"  Statement saved: {dest}")
        return dest
    except Exception as exc:
        await _screenshot(page, f"statement_error_{hotel_id}")
        print(f"  Statement error: {exc}")
        return None


# ── Email ──────────────────────────────────────────────────────────────────────

def _send_email(prop: dict, invoice: Path | None, statement: Path | None):
    name = prop["name"]
    hotel_id = prop["hotel_id"]

    if invoice is None and statement is None:
        subject = f"Booking.com - chybejici dokumenty - {name} - {PREV_MONTH_LABEL}"
        body = (
            f"Dobry den,\n\n"
            f"Za obdobi {PREV_MONTH_LABEL} nebyly nalezeny zadne dokumenty\n"
            f"pro ubytovani '{name}' (ID {hotel_id}) na Booking.com.\n\n"
            f"-- Automaticka zprava"
        )
        attachments = []
    else:
        subject = f"Booking.com dokumenty - {name} - {PREV_MONTH_LABEL}"
        lines = [f"Dobry den,\n"]
        lines.append(f"Dokumenty za {PREV_MONTH_LABEL} pro '{name}' (ID {hotel_id}):\n")
        lines.append(f"  - Invoice: {invoice.name if invoice else 'nenalezena'}")
        lines.append(f"  - Reservations statement: {statement.name if statement else 'nenalezen'}")
        lines.append(f"\n-- Automaticka zprava")
        body = "\n".join(lines)
        attachments = [p for p in (invoice, statement) if p]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = prop["to"]
    msg["Cc"]      = prop["cc"]
    msg.set_content(body)

    for path in attachments:
        msg.add_attachment(path.read_bytes(), maintype="application", subtype="pdf",
                           filename=path.name)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)

    print(f"  Email sent to {prop['to']}, cc {prop['cc']}")


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    _ensure_dirs()
    headless = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
    print(f"Starting (headless={headless}, period={PERIOD_LABEL})\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # Login once
        try:
            await _login(page)
        except Exception as exc:
            await _screenshot(page, "login_error")
            raise RuntimeError(f"Login failed: {exc}") from exc

        # Process each property
        for prop in PROPERTIES:
            hotel_id = prop["hotel_id"]
            print(f"\n{'─'*60}")
            print(f"Property: {prop['name']} ({hotel_id})")

            try:
                await _open_property(page, hotel_id)
            except Exception as exc:
                await _screenshot(page, f"open_property_error_{hotel_id}")
                print(f"  Could not open property: {exc}")
                _send_email(prop, None, None)
                continue

            invoice_path = None
            try:
                invoice_path = await _download_invoice(page, hotel_id)
            except Exception as exc:
                await _screenshot(page, f"invoice_error_{hotel_id}")
                print(f"  Invoice error: {exc}")

            statement_path = None
            try:
                statement_path = await _download_statement(page, hotel_id)
            except Exception as exc:
                await _screenshot(page, f"statement_error_{hotel_id}")
                print(f"  Statement error: {exc}")

            try:
                _send_email(prop, invoice_path, statement_path)
            except Exception as exc:
                print(f"  Email error: {exc}")

        await browser.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
