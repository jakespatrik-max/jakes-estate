"""
Otevře samostatný Chrome profil (nezasahuje do tvého hlavního Chrome).
Přihlas se ručně na Booking.com admin, pak stiskni Enter v terminálu.
Cookies se uloží a příště není potřeba login.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

BOOKING_PROFILE = Path(r"C:\Users\jakes\booking_chrome_profile")
SESSION_FILE    = Path(__file__).parent / "booking_session.json"

async def main():
    BOOKING_PROFILE.mkdir(parents=True, exist_ok=True)
    print("Spoustim samostatny Chrome pro Booking.com...")
    print("(Tvuj hlavni Chrome zustava otevreny)\n")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(BOOKING_PROFILE),
            headless=False,
            channel="chrome",
            args=["--profile-directory=Default"],
            ignore_default_args=["--enable-automation"],
        )
        page = await context.new_page()

        print("Naviguju na Booking.com admin...")
        await page.goto("https://admin.booking.com", wait_until="load", timeout=30000)
        await page.wait_for_timeout(3000)

        if "sign-in" in page.url or "login" in page.url:
            print("")
            print("==============================================")
            print("  PRIHLASTE SE v Chrome okne!")
            print("  Pouzijte svuj Booking.com Partner ucet.")
            print("  Po UPLNEM prihlaseni (az uvidite admin panel)")
            print("  se vradte SEM a stisknete Enter.")
            print("==============================================")
            input("\nStiskni Enter az vidis admin panel na obrazovce...")
            await page.wait_for_timeout(3000)

        # Naviguj znovu na admin aby se uložily admin cookies
        await page.goto(
            "https://admin.booking.com/hotel/hoteladmin/groups/home/index.html",
            wait_until="load", timeout=30000
        )
        await page.wait_for_timeout(3000)

        if "sign-in" in page.url or "login" in page.url:
            print("CHYBA: Admin panel neni dostupny. Zkus znovu.")
            await context.close()
            return

        print(f"Admin panel OK! URL: {page.url[:80]}")
        cookies = await context.cookies()
        SESSION_FILE.write_text(json.dumps({"cookies": cookies}, indent=2))
        print(f"\nOK! Ulozeno {len(cookies)} cookies do {SESSION_FILE.name}")
        print("Hotovo! Muzete zavrit Chrome okno.")
        await context.close()

asyncio.run(main())
