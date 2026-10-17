"""Non-destructive production browser checks for NordBridge calculators."""
import asyncio
from playwright.async_api import async_playwright
from audit_network import goto_with_retry

BASE = "https://www.nordbridge-global.com"

async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for width, height in [(1365, 900), (390, 844)]:
            page = await browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            response = await goto_with_retry(page, BASE + "/business-financing.html")
            assert response and response.ok, "Financing page unavailable"
            amount = page.locator("#finance-amount")
            upfront = page.locator("#finance-upfront")
            assert await amount.count() == 1 and await upfront.count() == 1, "Financing calculator controls missing"
            for value, expected in [(100000, "€500"), (500000, "€500"), (1000000, "€1,000"), (5000000, "€5,000")]:
                await amount.fill(str(value))
                await amount.dispatch_event("input")
                await page.wait_for_timeout(120)
                actual = (await upfront.inner_text()).strip()
                assert expected in actual, f"Financing {value}: expected {expected}, got {actual}"
            await amount.fill("50000")
            await amount.dispatch_event("input")
            await page.wait_for_timeout(120)
            warning = page.locator("#finance-warning")
            assert await warning.is_visible(), "Financing minimum threshold warning not shown"
            # Service calculator JavaScript exists in the repository, but the
            # homepage does not currently include its widget or load calculator.js.
            # Do not fail the production audit for an undeployed feature.
            # Add a separate interaction test if/when the widget is published.
            assert not errors, f"JavaScript exceptions: {errors[:3]}"
            await page.close()
        await browser.close()
    print("Financing calculator checks passed at desktop/mobile widths")

asyncio.run(main())
