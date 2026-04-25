"""
Airbnb – stahuje měsíční přehled výdělků v PDF, posílá emailem.
Před prvním spuštěním: spusť AIRBNB_EXPORT_COOKIES.bat
"""

import asyncio
import json
import smtplib
from datetime import datetime
from dateutil.relativedelta import relativedelta
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from playwright.async_api import async_playwright

# ── Konfigurace ───────────────────────────────────────────────────────────────

SCRIPT_DIR      = Path(__file__).parent
SESSION_FILE    = SCRIPT_DIR / "airbnb_session.json"
AIRBNB_PROFILE  = Path(r"C:\Users\jakes\airbnb_chrome_profile")
OUTPUT_DIR      = SCRIPT_DIR / "airbnb_reports"

SMTP_FROM     = "jakes.patrik@gmail.com"
SMTP_PASSWORD = "ruag budq ovfl fsot"
SMTP_TO       = ["jakes.patrik@gmail.com"]

last_month   = datetime.now() - relativedelta(months=1)
PERIOD       = last_month.strftime("%Y-%m")
PERIOD_LABEL = last_month.strftime("%B %Y")


# ── Helpers ───────────────────────────────────────────────────────────────────

def send_email(pdf_path: Path | None):
    msg = MIMEMultipart()
    msg["From"]    = SMTP_FROM
    msg["To"]      = ", ".join(SMTP_TO)

    if pdf_path:
        msg["Subject"] = f"Airbnb – přehled výdělků – {PERIOD_LABEL}"
        body = (
            f"Dobrý den,\n\n"
            f"v příloze zasílám měsíční přehled výdělků z Airbnb za {PERIOD_LABEL}.\n\n"
            f"-- Automatická zpráva"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_path.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=pdf_path.name)
        msg.attach(part)
    else:
        msg["Subject"] = f"Airbnb – přehled za {PERIOD_LABEL} nenalezen"
        body = (
            f"Dobrý den,\n\n"
            f"Nepodařilo se stáhnout přehled výdělků z Airbnb za {PERIOD_LABEL}.\n"
            f"Zkontrolujte prosím ručně.\n\n"
            f"-- Automatická zpráva"
        )
        msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(SMTP_FROM, SMTP_PASSWORD)
        s.sendmail(SMTP_FROM, SMTP_TO, msg.as_string())
    print(f"  Email odeslan -> {', '.join(SMTP_TO)}")


def send_session_expired_email():
    msg = MIMEMultipart()
    msg["From"]    = SMTP_FROM
    msg["To"]      = SMTP_FROM
    msg["Subject"] = "Airbnb – nutná obnova přihlášení"
    msg.attach(MIMEText(
        "Dobrý den,\n\n"
        "Automatický skript pro stahování přehledu z Airbnb nemohl pokračovat,\n"
        "protože přihlašovací session vypršela.\n\n"
        "Spusťte AIRBNB_EXPORT_COOKIES.bat a přihlaste se znovu.\n\n"
        "-- Automatická zpráva",
        "plain", "utf-8"
    ))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(SMTP_FROM, SMTP_PASSWORD)
        s.send_message(msg)
    print("  Session expired email odeslan.")


# ── Hlavní logika ─────────────────────────────────────────────────────────────

async def download_report(page) -> Path | None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    sc_dir = SCRIPT_DIR / "airbnb_screenshots"
    sc_dir.mkdir(exist_ok=True)

    print("  Naviguju na výdělky...")
    await page.goto("https://www.airbnb.cz/hosting/earnings", wait_until="load", timeout=30000)
    await page.wait_for_timeout(3000)
    await page.screenshot(path=str(sc_dir / "earnings.png"), full_page=True)

    # Kliknout na Přehledy
    try:
        btn = page.get_by_role("button", name="Přehledy")
        if await btn.count() == 0:
            btn = page.get_by_text("Přehledy").first
        await btn.click(timeout=8000)
        await page.wait_for_timeout(2000)
        print("  Kliknuto na Přehledy")
    except Exception as e:
        print(f"  Tlačítko Přehledy nenalezeno: {e}")
        await page.screenshot(path=str(sc_dir / "prehledy_error.png"), full_page=True)
        return None

    # Zavřít onboarding popup
    try:
        await page.get_by_role("button", name="Rozumím").click(timeout=3000)
    except Exception:
        pass

    # Kliknout na Zobrazit hlášení (první výskyt = minulý měsíc)
    try:
        btn = page.get_by_role("button", name="Zobrazit hlášení").first
        await btn.click(timeout=8000)
        await page.wait_for_timeout(2000)
        print("  Otevřen přehled")
    except Exception as e:
        print(f"  Tlačítko Zobrazit hlášení nenalezeno: {e}")
        await page.screenshot(path=str(sc_dir / "report_error.png"), full_page=True)
        return None

    # Kliknout na Získat přehled v PDF
    try:
        await page.get_by_role("button", name="Získat přehled v PDF").click(timeout=8000)
        await page.wait_for_timeout(1500)
        print("  Kliknuto na PDF")
    except Exception as e:
        print(f"  Tlačítko PDF nenalezeno: {e}")
        await page.screenshot(path=str(sc_dir / "pdf_error.png"), full_page=True)
        return None

    # Stáhnout PDF
    dest = OUTPUT_DIR / f"airbnb_prehled_{PERIOD}.pdf"
    try:
        async with page.expect_download(timeout=20000) as dl:
            await page.get_by_role("button", name="Stáhnout").click()
        d = await dl.value
        await d.save_as(str(dest))
        print(f"  PDF ulozeno: {dest.name}")
        return dest
    except Exception as e:
        # Zkus page.pdf() jako zálohu
        print(f"  Download selhal ({e}), zkousim page.pdf()...")
        try:
            pdf_bytes = await page.pdf(format="A4", print_background=True)
            dest.write_bytes(pdf_bytes)
            print(f"  PDF ulozeno: {dest.name}")
            return dest
        except Exception as e2:
            print(f"  page.pdf() taky selhalo: {e2}")
            await page.screenshot(path=str(sc_dir / "download_error.png"), full_page=True)
            return None


async def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Airbnb – období: {PERIOD_LABEL}\n")

    if not AIRBNB_PROFILE.exists():
        print("CHYBA: Airbnb Chrome profil nenalezen!")
        print("Spust AIRBNB_EXPORT_COOKIES.bat")
        return

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(AIRBNB_PROFILE),
            headless=False,
            channel="chrome",
            args=["--profile-directory=Default"],
            ignore_default_args=["--enable-automation"],
            accept_downloads=True,
        )
        page = await context.new_page()

        # Ověř přihlášení
        print("Overuji prihlaseni na Airbnb...")
        await page.goto("https://www.airbnb.cz/hosting/earnings", wait_until="load", timeout=30000)
        await page.wait_for_timeout(3000)

        print(f"  URL: {page.url[:80]}")
        if "login" in page.url or "signin" in page.url or "sign_in" in page.url:
            print("Session expirovala!")
            send_session_expired_email()
            await context.close()
            return

        print("  Prihlaseni OK\n")
        pdf = await download_report(page)

        await context.close()

    try:
        send_email(pdf)
    except Exception as e:
        print(f"  Chyba emailu: {e}")

    print("Hotovo!")


if __name__ == "__main__":
    asyncio.run(main())
