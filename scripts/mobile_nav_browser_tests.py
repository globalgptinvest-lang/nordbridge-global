"""Production Chromium regression for progressive, keyboard-accessible navigation.

Read-only: no form submission, no payment checkout, no CRM writing.
"""
import asyncio
import os
from playwright.async_api import async_playwright
from audit_network import goto_with_retry

BASE = os.getenv("NORDBRIDGE_TEST_BASE", "https://www.nordbridge-global.com").rstrip("/")


async def inspect_mobile(browser, path):
    context = await browser.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True, has_touch=True)
    try:
        page = await context.new_page()
        response = await goto_with_retry(page, BASE + path)
        assert response and response.ok, f"Page unavailable: {path}"
        toggle = page.locator("nav.nav .mobile-nav-toggle")
        await toggle.wait_for(state="visible", timeout=10000)
        inner = page.locator("nav.nav .nav-inner")
        assert await toggle.get_attribute("aria-expanded") == "false"
        assert not await inner.is_visible(), f"Menu should start collapsed: {path}"

        await toggle.click()
        assert await toggle.get_attribute("aria-expanded") == "true"
        assert await inner.is_visible(), f"Menu does not open: {path}"
        assert await inner.locator("a").count() >= 5, f"Missing site links: {path}"

        await page.keyboard.press("Escape")
        assert await toggle.get_attribute("aria-expanded") == "false"
        assert not await inner.is_visible(), f"Menu did not close with Escape: {path}"
        assert await toggle.evaluate("(el) => document.activeElement === el"), "Focus not restored"

        await page.locator(".language-switcher [data-lang='uk']").first.click()
        assert (await toggle.text_content()).strip() == "Меню", "UA menu label missing"
        await page.locator(".language-switcher [data-lang='ar']").first.click()
        assert (await toggle.text_content()).strip() == "القائمة", "Arabic menu label missing"
        assert await page.locator("html").get_attribute("dir") == "rtl", "RTL missing"
        overflow = await page.evaluate("() => document.documentElement.scrollWidth - visualViewport.width")
        assert overflow <= 14, f"RTL viewport expands horizontally: {overflow}px"

        await toggle.click(timeout=8000)
        assert await toggle.get_attribute("aria-expanded") == "true"
        target = inner.locator('a[href$="about.html"]').first
        assert await target.is_visible(), f"Menu about link missing: {path}"
        await target.click()
        await page.wait_for_url("**/about.html")
        await page.locator("nav.nav .mobile-nav-toggle").wait_for(state="visible")
        assert await page.locator("nav.nav .mobile-nav-toggle").get_attribute("aria-expanded") == "false"
    finally:
        await context.close()


async def inspect_desktop(browser):
    page = await browser.new_page(viewport={"width": 1365, "height": 900})
    try:
        r = await goto_with_retry(page, BASE + "/")
        assert r and r.ok, "Desktop home unavailable"
        assert not await page.locator("nav.nav .mobile-nav-toggle").is_visible()
        assert await page.locator('nav.nav .nav-inner a[href$="about.html"]').is_visible()
    finally:
        await page.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for path in ("/", "/about.html", "/contact.html"):
                await inspect_mobile(browser, path)
            await inspect_desktop(browser)
        finally:
            await browser.close()
    print("Mobile navigation passed: collapse, open, Escape, links, Ukrainian/Arabic, desktop fallback")


if __name__ == "__main__":
    asyncio.run(main())
