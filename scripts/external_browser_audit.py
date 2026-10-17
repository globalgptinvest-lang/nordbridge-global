import asyncio, xml.etree.ElementTree as ET
from audit_network import read_bytes, goto_with_retry
from urllib.parse import urlparse
from playwright.async_api import async_playwright

BASE = "https://www.nordbridge-global.com"
async def main():
    failures, warnings = [], []
    root = ET.fromstring(await asyncio.to_thread(read_bytes, BASE + "/sitemap.xml"))
    urls = [n.text.strip() for n in root.findall(".//{*}loc") if n.text]
    if not urls:
        raise SystemExit("No sitemap URLs found")
    sitemap_paths = {urlparse(u).path for u in urls}
    # /index.html is an alternative path to the canonical homepage /.
    sitemap_paths.add("/index.html")
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
                    response = await goto_with_retry(page, url, timeout=25000)
                    if not response or response.status >= 400:
                        failures.append(f"HTTP {response.status if response else 'none'}: {url}")
                        continue
                    title = (await page.title()).strip()
                    if not title: warnings.append(f"Missing title: {url}")
                    lang = await page.locator("html").get_attribute("lang")
                    if not lang: warnings.append(f"Missing html lang: {url}")
                    # Check visible interactive controls without activating external services.
                    controls = await page.locator("button, input[type=button], input[type=submit], [role=button]").evaluate_all("""els => els.filter(e => e.getClientRects().length > 0).map(e => ({name:(e.innerText||e.value||e.getAttribute("aria-label")||e.getAttribute("title")||"").trim(), disabled:e.disabled===true}))""")
                    for control in controls:
                        if not control["name"]:
                            warnings.append(f"Unlabelled visible button: {url}")
                    broken_anchors = await page.locator("a[href^='#']").evaluate_all("""els => els.filter(e => {const id=e.getAttribute("href").slice(1);return id && !document.getElementById(id) && !document.getElementsByName(id).length}).map(e => e.getAttribute("href"))""")
                    for anchor in broken_anchors:
                        warnings.append(f"Broken in-page anchor: {url} -> {anchor}")
                    images = await page.locator("img:not([alt])").count()
                    if images:
                        warnings.append(f"Images missing alt attribute ({images}): {url}")
                    links = await page.locator("a[href]").evaluate_all("""els => els.map(e => ({href:e.href,text:(e.innerText||e.getAttribute('aria-label')||'').trim()}))""")
                    for link in links:
                        href = link["href"]
                        if href.startswith(("javascript:", "mailto:", "tel:")): continue
                        if not link["text"] and not href.endswith("#"): warnings.append(f"Unlabelled link: {url} -> {href}")
                        if urlparse(href).netloc == urlparse(BASE).netloc:
                            path = urlparse(href).path
                            if path.endswith(".html") and path not in sitemap_paths:
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

if __name__ == "__main__":
    asyncio.run(main())
