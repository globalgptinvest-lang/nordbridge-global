"""Non-destructive production browser checks for NordBridge calculators."""
import asyncio
from playwright.async_api import async_playwright

BASE = "https://nordbridge-global.com"

async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        for width, height in [(1365, 900), (390, 844)]:
            page = await browser.new_page(viewport={"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            response = await page.goto(BASE + "/business-financing.html", wait_until="domcontentloaded")
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
            await page.goto(BASE + "/", wait_until="domcontentloaded")
            calculator = page.locator("#service-calculator")
            assert await calculator.count() == 1, "Service calculator missing from homepage"
            if await calculator.count():
                total = page.locator("#calc-total")
                checks = calculator.locator(".calc-item input")
                assert await checks.count() > 0, "Service calculator missing choices"
                await checks.first.check(force=True)
                await page.wait_for_timeout(100)
                assert (await total.inner_text()).strip() not in ("", "€0"), "Service total not updated"
                href = await page.locator("#calc-request").get_attribute("href")
                assert "package=custom" in (href or ""), "Service request link not updated"
                assert "services=" in (href or ""), "Selected services missing from request"
                assert "estimate=" in (href or ""), "Estimated price missing from request"
                await page.locator("#calc-reset").click()
                assert (await total.inner_text()).strip() in ("€0", "€0.00"), "Reset did not clear total"
            assert not errors, f"JavaScript exceptions: {errors[:3]}"
            await page.close()
        await browser.close()
    print("Financing and service calculator checks passed at desktop/mobile widths")

asyncio.run(main())
