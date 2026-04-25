"""
Booking.com – GitHub Actions verze.
Cookies se načítají z env proměnné BOOKING_COOKIES (GitHub Secret).
"""

import asyncio
import json
import os
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path
from playwright.async_api import async_playwright

# ── Konfigurace ───────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("faktury")

HOTELS = [
    {
        "id": 14881473,
        "name": "New Modern Art Loft Apartment",
        "to": ["jakes.patrik@gmail.com", "jakes.estate@moneyq.cz"],
    },
    {
        "id": 14234560,
        "name": "Baroque Grand Apartment XXL",
        "to": ["jakes.patrik@gmail.com", "jakes.residential@moneyq.cz"],
    },
]

SMTP_FROM     = os.environ["GMAIL_USER"]
SMTP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]

last_month   = datetime.now() - relativedelta(months=1)
PERIOD       = last_month.strftime("%Y-%m")
PERIOD_LABEL = last_month.strftime("%B %Y")

BASE = "https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_cookies() -> list:
    raw = os.environ.get("BOOKING_COOKIES", "")
    if not raw:
        raise RuntimeError("BOOKING_COOKIES secret neni nastaven!")
    data = json.loads(raw)
    return data if isinstance(data, list) else data["cookies"]


def send_session_expired_email():
    msg = MIMEMultipart()
    msg["From"]    = SMTP_FROM
    msg["To"]      = "jakes.patrik@gmail.com"
    msg["Subject"] = "Booking.com – nutná obnova přihlášení"
    msg.attach(MIMEText(
        "Dobrý den,\n\n"
        "Automatický skript pro stahování faktur z Booking.com nemohl pokračovat,\n"
        "protože přihlašovací session vypršela.\n\n"
        "Postup obnovy:\n"
        "1. Spusťte EXPORT_COOKIES.bat na svém počítači\n"
        "2. Přihlaste se na Booking.com v okně které se otevře\n"
        "3. Obsah souboru booking_session.json zkopírujte do GitHub Secret BOOKING_COOKIES\n\n"
        "-- Automatická zpráva",
        "plain", "utf-8"
    ))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(SMTP_FROM, SMTP_PASSWORD)
        s.sendmail(SMTP_FROM, ["jakes.patrik@gmail.com"], msg.as_string())


def send_email(hotel: dict, invoice: Path | None, statement: Path | None):
    to_list = hotel["to"]
    msg = MIMEMultipart()
    msg["From"] = SMTP_FROM
    msg["To"]   = ", ".join(to_list)

    has_docs = invoice or statement

    if has_docs:
        msg["Subject"] = f"Booking.com – {hotel['name']} – {PERIOD_LABEL}"
        lines = [
            f"Dobrý den,\n",
            f"v příloze zasílám dokumenty z Booking.com za {PERIOD_LABEL}",
            f"pro ubytování: {hotel['name']} (ID {hotel['id']})\n",
        ]
        if invoice:
            lines.append(f"  • {invoice.name} – Commission invoice")
        if statement:
            lines.append(f"  • {statement.name} – Reservations statement")
        lines.append("\n-- Automatická zpráva")
    else:
        msg["Subject"] = f"Booking.com – {hotel['name']} – {PERIOD_LABEL} – žádné rezervace"
        lines = [
            f"Dobrý den,\n",
            f"za {PERIOD_LABEL} nebyly nalezeny žádné rezervace ani dokumenty",
            f"pro ubytování: {hotel['name']} (ID {hotel['id']}).",
            "\n-- Automatická zpráva",
        ]

    msg.attach(MIMEText("\n".join(lines), "plain", "utf-8"))

    for f in [invoice, statement]:
        if f:
            part = MIMEBase("application", "pdf")
            part.set_payload(f.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=f.name)
            msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(SMTP_FROM, SMTP_PASSWORD)
        s.sendmail(SMTP_FROM, to_list, msg.as_string())
    print(f"  Email odeslan -> {', '.join(to_list)}")


# ── Stahování ─────────────────────────────────────────────────────────────────

async def get_invoice(page, context, hotel_id: int, ses: str) -> Path | None:
    print(f"  Faktury...")
    await page.goto(
        f"{BASE}/finance_invoices.html?hotel_id={hotel_id}&lang=xu&ses={ses}",
        wait_until="load", timeout=30000
    )
    await page.wait_for_timeout(2000)

    invoice_el = await page.query_selector("table tbody tr:first-child td:nth-child(2)")
    if not invoice_el:
        print(f"  Faktura nenalezena")
        return None

    invoice_number = (await invoice_el.inner_text()).strip()
    invoice_name   = f"1000-{invoice_number}"
    print(f"  Faktura: {invoice_name}")

    cookies     = await context.cookies()
    cookie_dict = {c["name"]: c["value"] for c in cookies}
    pdf_url = (
        f"https://admin.booking.com/fresa/extranet/finance/invoices/get_document"
        f"?ses={ses}&hotel_id={hotel_id}&lang=xu&invoice_name={invoice_name}"
    )
    response = requests.get(pdf_url, cookies=cookie_dict, timeout=30)

    dest = OUTPUT_DIR / f"faktura_{hotel_id}_{PERIOD}.pdf"
    if response.status_code == 200 and len(response.content) > 1000:
        dest.write_bytes(response.content)
        print(f"  Faktura ulozena: {dest.name}")
        return dest
    else:
        print(f"  Chyba stazeni faktury: HTTP {response.status_code}")
        return None


async def get_statement(page, hotel_id: int, ses: str) -> Path | None:
    print(f"  Reservations statement...")
    await page.goto(
        f"{BASE}/finance_reservations.html?hotel_id={hotel_id}&lang=xu&ses={ses}&period={PERIOD}",
        wait_until="load", timeout=30000
    )
    await page.wait_for_timeout(2000)

    dest = OUTPUT_DIR / f"statement_{hotel_id}_{PERIOD}.pdf"
    try:
        pdf_bytes = await page.pdf(
            format="A4", print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"}
        )
        dest.write_bytes(pdf_bytes)
        print(f"  Statement ulozen: {dest.name}")
        return dest
    except Exception as e:
        print(f"  Chyba statement: {e}")
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Obdobi: {PERIOD_LABEL}\n")

    cookies = load_cookies()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        await context.add_cookies(cookies)
        page = await context.new_page()

        print("Overuji prihlaseni...")
        await page.goto(
            "https://admin.booking.com/hotel/hoteladmin/groups/home/index.html",
            wait_until="load", timeout=30000
        )
        await page.wait_for_timeout(2000)

        if "sign-in" in page.url or "login" in page.url:
            print("Session expirovala!")
            send_session_expired_email()
            await browser.close()
            return

        ses = ""
        if "ses=" in page.url:
            ses = page.url.split("ses=")[1].split("&")[0]
        print(f"Prihlaseni OK\n")

        for hotel in HOTELS:
            hid = hotel["id"]
            print(f"{'='*50}")
            print(f"{hotel['name']} ({hid})")

            invoice = await get_invoice(page, context, hid, ses)

            if invoice is None:
                statement = None
            else:
                statement = await get_statement(page, hid, ses)

            try:
                send_email(hotel, invoice, statement)
            except Exception as e:
                print(f"  Chyba emailu: {e}")
            print()

        await browser.close()

    print("Hotovo!")


if __name__ == "__main__":
    asyncio.run(main())
