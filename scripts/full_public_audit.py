"""Read-only evidence collection from the publicly deployed NordBridge site.

Captures a desktop and mobile viewport of EVERY sitemap URL plus four
full-page mobile screenshots. Tests DOM layout, metadata, internal links,
language controls, form wiring, and console errors without submitting forms,
visiting payment checkout URLs or interacting with private services.

This is automated QA, not a human linguistic or aesthetic certification.
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin

from playwright.async_api import async_playwright
try:
    from scripts.audit_network import read_bytes, goto_with_retry
except ModuleNotFoundError:
    # Direct invocation with `python scripts/full_public_audit.py`.
    from audit_network import read_bytes, goto_with_retry

BASE = "https://www.nordbridge-global.com"
CANONICAL = "https://www.nordbridge-global.com"
LANGUAGES = ("en", "uk", "da", "ar")
EXTRA = ("/index.html",)
PRIORITY = ("/", "/business-financing.html", "/free-tender-fit-check.html",
            "/contact.html", "/tender-subscription.html")
MAX_MESSAGE = 180


def plain(value):
    return re.sub(r"[\r\n|]", " ", str(value or ""))[:MAX_MESSAGE]


def issue(code, severity, path, detail):
    return {"code": code, "severity": severity, "path": path, "detail": plain(detail)}


def sitemap_urls(xml):
    root = ET.fromstring(xml)
    values = [x.text.strip() for x in root.findall(".//{*}loc") if x.text]
    pages = []
    seen = set()
    for value in values:
        u = urlparse(value)
        if u.hostname not in ("nordbridge-global.com", "www.nordbridge-global.com"):
            raise ValueError("External sitemap URL " + value[:120])
        path = u.path or "/"
        if path not in seen:
            pages.append(path)
            seen.add(path)
    return pages


def audit_metadata(path, data, canonical_host=CANONICAL):
    findings = []
    def add(code, level, explanation):
        findings.append(issue(code, level, path, explanation))
    if not data.get("title"):
        add("SEO_TITLE", "error", "Missing page title")
    if not data.get("description"):
        add("SEO_DESCRIPTION", "error", "Missing description")
    if data.get("h1_count") != 1:
        add("HEADING", "warning", "Expected one h1; found " + str(data.get("h1_count")))
    if not data.get("lang"):
        add("HTML_LANG", "error", "Missing html language attribute")
    if not data.get("viewport"):
        add("MOBILE_VIEWPORT", "error", "Missing viewport metadata")
    expected = canonical_host + ("/" if path in ("/", "/index.html") else path)
    current = data.get("canonical", "")
    if not current:
        add("SEO_CANONICAL", "error", "Missing canonical URL")
    elif current != expected:
        add("SEO_CANONICAL_HOST", "warning",
            "Canonical differs from production www URL (expected " + expected + ")")
    if data.get("overflow_px", 0) > 12:
        add("MOBILE_OVERFLOW", "warning",
            str(data["overflow_px"]) + "px horizontal document overflow")
    for anchor in data.get("missing_anchors", []):
        add("BROKEN_ANCHOR", "warning", anchor)
    for input_label in data.get("unlabelled_controls", [])[:8]:
        add("ACCESSIBLE_NAME", "warning", input_label)
    return findings


def untranslated_text_finding(path, language, before, after):
    """Warn when substantial visible English copy remains unchanged after a switch."""
    if language == "en":
        return None
    unchanged = []
    for original, localized in zip(before, after):
        text = " ".join(str(original or "").split())
        if text != " ".join(str(localized or "").split()):
            continue
        if len(text) < 42 or len(re.findall(r"[A-Za-z]{3,}", text)) < 4:
            continue
        if "@" in text or "http" in text.lower() or "www." in text.lower():
            continue
        unchanged.append(text)
    if not unchanged:
        return None
    examples = "; ".join(plain(x) for x in unchanged[:3])
    return issue("TRANSLATION_COPY_UNCHANGED", "warning", path,
                 language + ": " + str(len(unchanged)) + " substantial visible text node(s) stayed unchanged; " + examples)


def meta_js():
    return r"""() => {
      const get = sel => document.querySelector(sel)?.content || '';
      const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      const accessible = el => {
        const label = el.labels?.length
          ? [...el.labels].map(x=>x.innerText.trim()).join(' ')
          : '';
        const closest = el.closest('label')?.innerText?.trim() || '';
        return (el.getAttribute('aria-label') || label || closest
                || el.getAttribute('title') || el.getAttribute('alt')
                || el.innerText || el.value || '').trim();
      };
      return {
        title: document.title.trim(),
        description: get('meta[name="description"]'),
        canonical: document.querySelector('link[rel="canonical"]')?.href || '',
        viewport: !!document.querySelector('meta[name="viewport"]'),
        lang: document.documentElement.lang,
        h1_count: document.querySelectorAll('h1').length,
        overflow_px: Math.max(0, Math.ceil(
          Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0)
          - window.innerWidth)),
        missing_anchors: [...document.querySelectorAll('a[href^="#"]')]
          .map(a=>a.getAttribute('href'))
          .filter(id=>id.length>1 && !document.getElementById(id.slice(1))
            && !document.getElementsByName(id.slice(1)).length).slice(0,12),
        unlabelled_controls: [...document.querySelectorAll('button, input:not([type=hidden]), select, textarea, [role=button]')]
          .filter(el=>el.getAttribute('aria-hidden')!=='true' && el.tabIndex!==-1)
          .filter(visible).filter(el=>!accessible(el))
          .map(el=>el.tagName.toLowerCase()+(el.name?' name='+el.name:'')).slice(0,12),
        internal: [...document.querySelectorAll('a[href]')]
          .map(a=>a.href).filter(x=>x.startsWith(location.origin+'/'))
          .map(x=>{try {return new URL(x).pathname} catch(e) {return ''}})
          .filter(Boolean),
        language: [...document.querySelectorAll('.language-switcher [data-lang]')]
          .map(x=>x.getAttribute('data-lang')),
        forms: [...document.querySelectorAll('form')].map(f=>({
          lead: f.classList.contains('lead-form'),
          action: f.action,
          consent: !!f.querySelector('input[name=privacy_consent]'),
          submit: !!f.querySelector('button[type=submit], input[type=submit]'),
          csrf: !!f.querySelector('[name="cf-turnstile-response"]')
        }))
      };
    }"""


async def inspect(args):
    out = Path(args.output)
    shots = out / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    sitemap_xml = await asyncio.to_thread(read_bytes, BASE + "/sitemap.xml")
    paths = sitemap_urls(sitemap_xml)
    for extra in EXTRA:
        if extra not in paths:
            paths.append(extra)
    findings, records, visited = [], [], set()
    console_errors = []
    page_titles = []
    urls_to_check = set()
    viewports = (("desktop", 1365, 900), ("mobile", 390, 844))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for profile, width, height in viewports:
                context = await browser.new_context(
                    viewport={"width": width, "height": height},
                    device_scale_factor=1, is_mobile=(profile == "mobile"),
                    has_touch=(profile == "mobile"), ignore_https_errors=False)
                try:
                    page = await context.new_page()
                    for idx, path in enumerate(paths):
                        url = BASE + path
                        errors = []
                        def on_error(exc):
                            errors.append(plain(str(exc)))
                        page.on("pageerror", on_error)
                        record = {"path": path, "viewport": profile, "http": None, "image": "",
                                  "console_errors": [], "data": {}}
                        try:
                            response = await goto_with_retry(page, url, timeout=30000)
                            record["http"] = response.status if response else 0
                            if not response or response.status >= 400:
                                findings.append(issue("HTTP", "error", path,
                                                      profile + ": HTTP " + str(record["http"])))
                                continue
                            await page.wait_for_timeout(180)
                            # Turnstile is loaded asynchronously. Inspect the final
                            # form route rather than falsely reporting a slow CDN
                            # as an unprotected permanent fallback.
                            if await page.locator("form.lead-form").count():
                                try:
                                    await page.wait_for_function(
                                        """() => [...document.querySelectorAll('form.lead-form')]
                                          .every(form => form.dataset.intakeEnabled === 'true')""",
                                        timeout=4500)
                                except Exception:
                                    pass  # The audited form will retain a warning.
                            data = await page.evaluate(meta_js())
                            record["data"] = {key: data.get(key) for key in (
                                "title", "description", "canonical", "viewport", "lang",
                                "h1_count", "overflow_px", "language", "forms")}
                            if profile == "desktop":
                                page_titles.append((path, data.get("title", "")))
                                urls_to_check.update(data.get("internal", []))
                            findings.extend(audit_metadata(path, data))
                            if data.get("forms"):
                                for f in data["forms"]:
                                    if f["lead"] and (not f["consent"] or not f["submit"]):
                                        findings.append(issue("LEAD_FORM", "error", path,
                                                              "Missing consent or submit button"))
                                    if f["lead"] and not f["action"].endswith("/api/lead"):
                                        findings.append(issue("FORM_ROUTE", "warning", path,
                                                              "Form not routed through private CRM API"))
                            if profile == "desktop":
                                found_lang = set(data.get("language", []))
                                if found_lang and found_lang != set(LANGUAGES):
                                    findings.append(issue("LANGUAGE_CONTROLS", "error", path,
                                                          "Incomplete language switcher"))
                                if not found_lang:
                                    findings.append(issue("NO_LANGUAGE_SWITCH", "warning", path,
                                                          "Page lacks four-language switcher"))
                                else:
                                    # Test every public page: language/head state plus a heuristic
                                    # warning for substantial visible source copy left unchanged.
                                    base_title = (await page.title()).strip()
                                    base_heading = (await page.locator("h1").first.inner_text()).strip() if data.get("h1_count") else ""
                                    base_copy = await page.evaluate(r"""() => {
                                      const out=[];
                                      const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
                                      for(let n; (n=walker.nextNode());) {
                                        const value=(n.nodeValue||'').trim();
                                        if(value.length>=42 && n.parentElement?.getClientRects().length) out.push(value);
                                      }
                                      return out;
                                    }""")
                                    translated = []
                                    for language in LANGUAGES:
                                        try:
                                            button = page.locator(".language-switcher [data-lang='"+language+"']").first
                                            await button.click(force=True, timeout=4000)
                                            await page.wait_for_timeout(75)
                                            state = await page.evaluate("""() => ({
                                              lang:document.documentElement.lang,
                                              dir:document.documentElement.dir,
                                              title:document.title.trim(),
                                              h1:(document.querySelector('h1')?.innerText||'').trim(),
                                              copy:(() => {
                                                const out=[];
                                                const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
                                                for(let n; (n=walker.nextNode());) {
                                                  const value=(n.nodeValue||'').trim();
                                                  if(value.length>=42 && n.parentElement?.getClientRects().length) out.push(value);
                                                }
                                                return out;
                                              })()
                                            })""")
                                            translated.append(state)
                                            if state["lang"] != language or state["dir"] != ("rtl" if language=="ar" else "ltr"):
                                                findings.append(issue("LANGUAGE_SWITCH_FAIL", "error", path,
                                                                      "Incorrect lang/dir after "+language+" selection"))
                                            if not state["title"] or (data.get("h1_count") and not state["h1"]):
                                                findings.append(issue("TRANSLATION_EMPTY", "error", path,
                                                                      "Missing visible heading or title in "+language))
                                            copy_issue = untranslated_text_finding(path, language, base_copy, state["copy"])
                                            if copy_issue:
                                                findings.append(copy_issue)
                                        except Exception as translation_error:
                                            findings.append(issue("LANGUAGE_CLICK_FAIL", "error", path,
                                                                  language+": "+type(translation_error).__name__))
                                    # A preserved English title or heading is possible partial
                                    # translation, not proof of a bad translation.
                                    for state in translated:
                                        if state["lang"]=="en":
                                            continue
                                        if len(base_heading)>18 and state["h1"]==base_heading and state["title"]==base_title:
                                            findings.append(issue("TRANSLATION_COVERAGE", "warning", path,
                                                                  state["lang"]+": headline and title unchanged"))
                                    await page.locator(".language-switcher [data-lang='en']").first.click(force=True)
                                    record["languages_tested"] = [v["lang"] for v in translated]
                            filename = "page_%02d_%s_%s.jpg" % (
                                idx + 1, profile, "home" if path == "/" else
                                re.sub(r"[^A-Za-z0-9-]", "_", path.strip("/")))
                            screenshot_path = shots / filename
                            await page.screenshot(path=str(screenshot_path), type="jpeg",
                                                  quality=68, full_page=(profile == "mobile" and path in PRIORITY),
                                                  animations="disabled", timeout=30000)
                            record["image"] = str(screenshot_path.relative_to(out))
                            if errors:
                                # Public page exceptions may originate from third-party tags.
                                for message in sorted(set(errors))[:4]:
                                    findings.append(issue("JS_EXCEPTION", "warning", path, profile+": "+message))
                                record["console_errors"] = sorted(set(errors))[:4]
                        except Exception as exc:
                            findings.append(issue("BROWSER_EXCEPTION", "error", path,
                                                  profile+": "+type(exc).__name__+": "+plain(exc)))
                        finally:
                            records.append(record)
                            page.remove_listener("pageerror", on_error)
                finally:
                    await context.close()

            # Check internal targets without clicking checkout, sending forms or
            # invoking any POST endpoints. Do it once per distinct path.
            context = await browser.new_context(ignore_https_errors=False)
            try:
                request = context.request
                listed = set(paths)
                for path in sorted(urls_to_check):
                    if path in listed or path.startswith(("/api/", "/cdn-cgi/")):
                        continue
                    try:
                        response = await request.get(BASE + path, timeout=18000,
                                                     max_redirects=3)
                        if response.status >= 400:
                            findings.append(issue("BROKEN_INTERNAL_LINK", "error", path,
                                                  "GET HTTP " + str(response.status)))
                    except Exception as exc:
                        findings.append(issue("INTERNAL_LINK_REQUEST", "warning", path,
                                              type(exc).__name__))
            finally:
                await context.close()
        finally:
            await browser.close()

    duplicates = {}
    for path, name in page_titles:
        if name: duplicates.setdefault(name, []).append(path)
    for name, pages in duplicates.items():
        if len(pages)>1 and set(pages)!={"/", "/index.html"}:
            findings.append(issue("DUPLICATE_TITLE", "warning", ", ".join(pages),
                                  "Repeated SEO title: "+name))
    findings = list({(f["code"], f["severity"], f["path"], f["detail"]):f
                     for f in findings}.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base": BASE, "sitemap_count": len(paths)-len([p for p in EXTRA if p not in sitemap_urls(sitemap_xml)]),
        "pages_checked": len(paths), "viewport_checks": len(records),
        "screenshots": sum(bool(x["image"]) for x in records),
        "severity_counts": dict(Counter(x["severity"] for x in findings)),
        "issues": findings, "pages": records,
        "limitations": [
            "Automated heuristics and screenshots are not human proofreading of all translations.",
            "Browser check deliberately does not submit forms, follow Stripe checkout or create payments.",
            "External third-party network and UX quality require separate verification."
        ]
    }
    (out/"report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    lines = ["# NordBridge — Full public browser, SEO and mobile audit",
             "", "Generated (UTC): "+report["generated_at"],
             "", f"Sitemap: {len(paths)} routes (including /index.html), "
             f"{len(records)} desktop/mobile inspections, {report['screenshots']} screenshots.",
             "", "## Findings", "", "| Severity | Code | Page | Detail |",
             "|---|---|---|---|"]
    for item in findings[:160]:
        lines.append("| "+item["severity"]+" | "+item["code"]+" | "+
                     item["path"]+" | "+item["detail"]+" |")
    lines += ["", "## Screenshots", ""]
    for item in records:
        if item["image"]:
            lines.append("- "+item["viewport"]+" "+item["path"]+": "+item["image"])
    lines += ["", "## Boundaries", ""]
    lines += ["- "+x for x in report["limitations"]]
    (out/"report.md").write_text("\n".join(lines)+"\n", encoding="utf8")
    summary = (f"NordBridge external QA: {len(paths)} routes, {len(records)} viewport checks, "
               f"{report['screenshots']} screenshots; "
               f"{report['severity_counts'].get('error',0)} errors and "
               f"{report['severity_counts'].get('warning',0)} warnings")
    print(summary)
    for finding in findings[:100]:
        print("FINDING:", finding["severity"], finding["code"], finding["path"], finding["detail"])
    if len(findings) > 100:
        print("FINDING: remaining", len(findings)-100, "see report.json artifact")
    print("Evidence directory:", out)
    if args.strict and report["severity_counts"].get("error", 0):
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/nordbridge-full-audit")
    parser.add_argument("--strict", action="store_true",
                        help="Fail CI on confirmed error-level findings")
    args = parser.parse_args()
    return asyncio.run(inspect(args))


if __name__ == "__main__":
    sys.exit(main())
