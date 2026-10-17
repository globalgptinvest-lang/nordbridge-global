"""Smoke-test public language switcher and key financing translations.

Does not claim human linguistic QA; only verifies functionality and nonempty localized content.
"""
import asyncio
from playwright.async_api import async_playwright
from audit_network import goto_with_retry

URL = "https://www.nordbridge-global.com/business-financing.html"
LANGS = {"en": "Funding", "uk": "фінанс", "da": "finans", "ar": "تمويل"}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for viewport in [{"width": 1365, "height": 900}, {"width": 390, "height": 844}]:
            page = await browser.new_page(viewport=viewport)
            response = await goto_with_retry(page, URL)
            assert response and response.ok, "Funding page unavailable"
            for lang, keyword in LANGS.items():
                switch = page.locator(f".language-switcher [data-lang='{lang}']")
                assert await switch.count() == 1, f"Missing {lang} switch"
                await switch.click(force=True)
                await page.wait_for_timeout(150)
                title = (await page.locator("[data-bf-key='heroTitle']").inner_text()).strip()
                assert title and keyword.casefold() in title.casefold(), f"{lang} title not localized: {title}"
                assert await page.locator("[data-bf-key='submit']").count() > 0, f"{lang} submit text missing"
                assert (await page.locator("[data-bf-key='submit']").inner_text()).strip(), f"{lang} submit text empty"
                assert (await page.locator("html").get_attribute("lang")) == lang, f"HTML lang did not change to {lang}"
            await page.close()
        await browser.close()
    print("Language switcher smoke checks passed (EN/UK/DA/AR, desktop/mobile)")

asyncio.run(main())
