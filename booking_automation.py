"""
Booking.com invoice & statement downloader
Runs headless, downloads PDFs for the previous month, sends via Gmail SMTP.
Credentials come from environment variables — never hardcode them.
"""

import asyncio
import os
import smtplib
import calendar
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext

# ── Configuration ────────────────────────────────────────────────────────────

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

BOOKING_USERNAME = os.environ["BOOKING_USERNAME"]
BOOKING_PASSWORD = os.environ["BOOKING_PASSWORD"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

SCREENSHOTS_DIR = Path("screenshots")
DOWNLOADS_DIR = Path("downloads")

# Previous month helpers
_today = date.today()
_first_this = _today.replace(day=1)
_last_prev = _first_this - timedelta(days=1)
PREV_MONTH = _last_prev.month
PREV_YEAR = _last_prev.year
PREV_MONTH_LABEL = _last_prev.strftime("%B %Y")          # e.g. "March 2026"
PREV_MONTH_SHORT = _last_prev.strftime("%m/%Y")          # e.g. "03/2026"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_dirs():
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    DOWNLOADS_DIR.mkdir(exist_ok=True)


async def _screenshot(page: Page, name: str):
    path = SCREENSHOTS_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"  [screenshot] {path}")


async def _login(page: Page):
    print("Logging in to Booking.com …")
    await page.goto("https://account.booking.com/sign-in", wait_until="networkidle")
    await page.fill('input[name="username"]', BOOKING_USERNAME)
    await page.click('button[type="submit"]')          # "Next"
    await page.wait_for_load_state("networkidle")
    await page.fill('input[name="password"]', BOOKING_PASSWORD)
    await page.click('button[type="submit"]')          # "Sign in"
    await page.wait_for_load_state("networkidle")
    print("  Logged in.")


async def _open_property(context: BrowserContext, hotel_id: str) -> Page:
    """Navigate to the admin panel for a specific hotel and return the page."""
    url = (
        f"https://admin.booking.com/hotel/hoteladmin/groups/home"
        f"?ses=&hotel_id={hotel_id}"
    )
    page = await context.new_page()
    await page.goto(url, wait_until="networkidle")
    # Confirm we landed on the right property
    await page.wait_for_selector(f'[data-hotel-id="{hotel_id}"], [data-id="{hotel_id}"]',
                                  timeout=10_000, state="attached")
    return page


# ── Invoice download ──────────────────────────────────────────────────────────

async def _download_invoice(page: Page, hotel_id: str) -> Path | None:
    """
    Finance → Invoices and documents → Payments to Booking.com → PDF for prev month.
    Returns local path or None when not found.
    """
    print(f"  Navigating to Invoices …")
    await page.goto(
        f"https://admin.booking.com/hotel/hoteladmin/finance/invoices/"
        f"?hotel_id={hotel_id}",
        wait_until="networkidle",
    )

    # Find the row for previous month
    # Booking renders invoice rows with month labels like "March 2026"
    row_locator = page.locator(f'text="{PREV_MONTH_LABEL}"').first
    try:
        await row_locator.wait_for(timeout=8_000)
    except Exception:
        await _screenshot(page, f"invoice_not_found_{hotel_id}")
        print(f"  No invoice found for {PREV_MONTH_LABEL}.")
        return None

    # Click PDF link in that row
    row = row_locator.locator("..").locator("..")   # go up to the table row
    pdf_link = row.locator('a[href*=".pdf"], a:has-text("PDF"), a:has-text("Download")')
    href = await pdf_link.get_attribute("href")

    if not href:
        await _screenshot(page, f"invoice_no_href_{hotel_id}")
        print("  PDF link found but no href.")
        return None

    # Download the PDF
    dest = DOWNLOADS_DIR / f"invoice_{hotel_id}_{PREV_YEAR}_{PREV_MONTH:02d}.pdf"
    async with page.expect_download() as dl_info:
        await pdf_link.click()
    download = await dl_info.value
    await download.save_as(str(dest))
    print(f"  Invoice saved: {dest}")
    return dest


# ── Statement download ────────────────────────────────────────────────────────

async def _download_statement(page: Page, hotel_id: str) -> Path | None:
    """
    Reservations statement → View statement → Print → save as PDF via CDP.
    Returns local path or None when not found.
    """
    print(f"  Navigating to Reservations statement …")
    await page.goto(
        f"https://admin.booking.com/hotel/hoteladmin/finance/reservations-statement/"
        f"?hotel_id={hotel_id}",
        wait_until="networkidle",
    )

    # Select previous month in the period picker (varies by UI; try common selectors)
    month_selector = page.locator('select[name="month"], [data-testid="month-select"]')
    if await month_selector.count():
        await month_selector.select_option(str(PREV_MONTH))
        year_selector = page.locator('select[name="year"], [data-testid="year-select"]')
        if await year_selector.count():
            await year_selector.select_option(str(PREV_YEAR))
        apply_btn = page.locator('button:has-text("Apply"), button:has-text("Go"), button[type="submit"]').first
        if await apply_btn.count():
            await apply_btn.click()
            await page.wait_for_load_state("networkidle")

    # Click "View statement"
    view_btn = page.locator('a:has-text("View statement"), button:has-text("View statement")').first
    try:
        await view_btn.wait_for(timeout=8_000)
    except Exception:
        await _screenshot(page, f"statement_not_found_{hotel_id}")
        print(f"  No statement found for {PREV_MONTH_LABEL}.")
        return None

    # Open statement in new tab
    async with page.context.expect_page() as new_page_info:
        await view_btn.click()
    stmt_page = await new_page_info.value
    await stmt_page.wait_for_load_state("networkidle")

    # Print to PDF via Chrome DevTools Protocol
    dest = DOWNLOADS_DIR / f"statement_{hotel_id}_{PREV_YEAR}_{PREV_MONTH:02d}.pdf"
    pdf_bytes = await stmt_page.pdf(
        path=str(dest),
        format="A4",
        print_background=True,
    )
    await stmt_page.close()
    print(f"  Statement saved: {dest}")
    return dest


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email(prop: dict, invoice: Path | None, statement: Path | None):
    subject = f"Booking.com dokumenty — {prop['name']} — {PREV_MONTH_LABEL}"

    if invoice is None and statement is None:
        body = (
            f"Dobrý den,\n\n"
            f"Invoice na Booking.com za {PREV_MONTH_LABEL} pro ubytování "
            f"„{prop['name']}" (ID {prop['hotel_id']}) není k dispozici.\n\n"
            f"Rezervační výpis rovněž nebyl nalezen.\n\n"
            f"— Automatická zpráva"
        )
        attachments = []
    else:
        lines = [
            f"Dobrý den,\n",
            f"V příloze naleznete dokumenty za {PREV_MONTH_LABEL} "
            f"pro „{prop['name']}" (ID {prop['hotel_id']}):\n",
        ]
        if invoice:
            lines.append(f"  • Invoice: {invoice.name}")
        else:
            lines.append(f"  • Invoice: nebyl nalezen na Booking.com")
        if statement:
            lines.append(f"  • Reservations statement: {statement.name}")
        else:
            lines.append(f"  • Reservations statement: nebyl nalezen")
        lines.append("\n— Automatická zpráva")
        body = "\n".join(lines)
        attachments = [p for p in (invoice, statement) if p]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = prop["to"]
    msg["Cc"] = prop["cc"]
    msg.set_content(body)

    for path in attachments:
        data = path.read_bytes()
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=path.name)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)

    recipients = f"{prop['to']}, {prop['cc']}"
    print(f"  Email odeslan → {recipients}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    _ensure_dirs()
    headless = os.environ.get("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
    print(f"Starting (headless={headless}, month={PREV_MONTH_LABEL}) …\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)

        # Single login on first page
        login_page = await context.new_page()
        try:
            await _login(login_page)
        except Exception as exc:
            await _screenshot(login_page, "login_error")
            raise RuntimeError(f"Login failed: {exc}") from exc
        await login_page.close()

        for prop in PROPERTIES:
            hotel_id = prop["hotel_id"]
            print(f"\n{'─'*60}")
            print(f"Property: {prop['name']} ({hotel_id})")

            try:
                page = await context.new_page()

                # Invoice
                invoice_path = None
                try:
                    invoice_path = await _download_invoice(page, hotel_id)
                except Exception as exc:
                    await _screenshot(page, f"invoice_error_{hotel_id}")
                    print(f"  ERROR downloading invoice: {exc}")

                # Statement
                statement_path = None
                try:
                    statement_path = await _download_statement(page, hotel_id)
                except Exception as exc:
                    await _screenshot(page, f"statement_error_{hotel_id}")
                    print(f"  ERROR downloading statement: {exc}")

                await page.close()

            except Exception as exc:
                print(f"  FATAL for {hotel_id}: {exc}")
                invoice_path = None
                statement_path = None

            # Always send email (even if both are missing)
            try:
                _send_email(prop, invoice_path, statement_path)
            except Exception as exc:
                print(f"  ERROR sending email: {exc}")

        await browser.close()

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
