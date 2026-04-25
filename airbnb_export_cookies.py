"""
Exportuje session z Airbnb Chrome profilu.
Chrome nemusí být zavřený – používá separátní profil.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

AIRBNB_PROFILE = Path(r"C:\Users\jakes\airbnb_chrome_profile")

async def main():
    AIRBNB_PROFILE.mkdir(parents=True, exist_ok=True)
    print("Spoustim samostatny Chrome pro Airbnb...")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(AIRBNB_PROFILE),
            headless=False,
            channel="chrome",
            args=["--profile-directory=Default"],
            ignore_default_args=["--enable-automation"],
        )
        page = await context.new_page()
        await page.goto("https://www.airbnb.cz/hosting/earnings", wait_until="load", timeout=30000)
        await page.wait_for_timeout(3000)

        if "login" in page.url or "signin" in page.url or "sign_in" in page.url:
            print("")
            print("==============================================")
            print("  PRIHLASTE SE na Airbnb v Chrome okne!")
            print("  Po uplnem prihlaseni (az uvidite prehledy)")
            print("  se vradte SEM a stisknete Enter.")
            print("==============================================")
            input("\nStiskni Enter az vidis Airbnb hosting stranku...")
            await page.wait_for_timeout(2000)

        print(f"Prihlasen! URL: {page.url[:80]}")
        print(f"Hotovo! Muzete zavrit Chrome okno.")
        await context.close()

asyncio.run(main())
