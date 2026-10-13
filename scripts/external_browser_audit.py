import asyncio, os, re, xml.etree.ElementTree as ET
from urllib.request import urlopen
from urllib.parse import urlparse
from playwright.async_api import async_playwright

BASE = "https://nordbridge-global.com"
async def main():
    failures, warnings = [], []
    with urlopen(BASE + "/sitemap.xml", timeout=30) as response:
        root = ET.fromstring(response.read())
    urls = [n.text.strip() for n in root.findall(".//{*}loc") if n.text]
    if not urls:
        raise SystemExit("No sitemap URLs found")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for width, height in [(1365, 900), (390, 844)]:
            context = await browser.new_context(viewport={"width": width, "height": height})
            page = await context.new_page()
            for url in urls:
                if urlparse(url).netloc != urlparse(BASE).netloc:
                    failures.append(f"External sitemap URL: {url}")
                    continue
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                    if not response or response.status >= 400:
                        failures.append(f"HTTP {response.status if response else 'none'}: {url}")
                        continue
                    title = (await page.title()).strip()
                    if not title: warnings.append(f"Missing title: {url}")
                    lang = await page.locator("html").get_attribute("lang")
                    if not lang: warnings.append(f"Missing html lang: {url}")
                    links = await page.locator("a[href]").evaluate_all("""els => els.map(e => ({href:e.href,text:(e.innerText||e.getAttribute('aria-label')||'').trim()}))""")
                    for link in links:
                        href = link["href"]
                        if href.startswith(("javascript:", "mailto:", "tel:")): continue
                        if not link["text"] and not href.endswith("#"): warnings.append(f"Unlabelled link: {url} -> {href}")
                        if urlparse(href).netloc == urlparse(BASE).netloc:
                            path = urlparse(href).path
                            if path.endswith(".html") and path not in {urlparse(u).path for u in urls}:
                                warnings.append(f"Internal HTML link not in sitemap: {url} -> {href}")
                    forms = await page.locator("form").count()
                    for i in range(forms):
                        form = page.locator("form").nth(i)
                        if await form.locator("button[type=submit], input[type=submit]").count() == 0:
                            warnings.append(f"Form without submit control: {url}")
                    # Do not submit forms or click checkout/payment buttons in production.
                except Exception as exc:
                    failures.append(f"Browser error {url}: {type(exc).__name__}: {str(exc)[:180]}")
            await context.close()
        await browser.close()
    print(f"Audited {len(urls)} sitemap pages at desktop and mobile sizes")
    for msg in sorted(set(warnings)): print("WARNING:", msg)
    for msg in sorted(set(failures)): print("ERROR:", msg)
    if failures: raise SystemExit(1)

asyncio.run(main())
