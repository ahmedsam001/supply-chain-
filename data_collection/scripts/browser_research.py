"""
Phase 5 Browser Research Script — Automated Source Exploration with Playwright Chromium.

For each permitted source:
1. Opens Chromium in headless mode
2. Navigates to homepage, sample category, and sample product
3. Captures URLs, titles, and full page HTML snapshots
4. Detects JSON-LD schemas
5. Identifies product cards, pagination, and links
6. Detects branch/store locator markers
7. Intercepts and records API/network requests
8. Saves debug screenshots (homepage.png, sample_category.png, sample_product.png)
9. Generates detected_fields.json and network.json

Outputs to: data/research/<source_id>/
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import structlog
from playwright.async_api import async_playwright

logger = structlog.get_logger()

RESEARCH_TARGETS = {
    "tradeline": {
        "name": "Tradeline Stores",
        "home_url": "https://www.tradelinestores.com",
        "category_url": "https://www.tradelinestores.com/collections/mac",
        "product_url": "https://www.tradelinestores.com/products/macbook-air-13-m3-chip-2024-8c-cpu-8c-gpu-8gb-256gb-ssd-midnight",
        "store_locator_url": "https://www.tradelinestores.com/pages/store-locator",
    },
    "dream2000": {
        "name": "Dream 2000",
        "home_url": "https://dream2000.com",
        "category_url": "https://dream2000.com/collections/smartphones",
        "product_url": "https://dream2000.com/collections/smartphones/products/samsung-galaxy-a55-5g",
        "store_locator_url": "https://dream2000.com/pages/branches",
    },
    "btech": {
        "name": "B.TECH",
        "home_url": "https://btech.com",
        "category_url": "https://btech.com/en/mobiles",
        "product_url": "https://btech.com/en/store-finder",
        "store_locator_url": "https://btech.com/en/store-finder",
    },
    "two_b": {
        "name": "2B Egypt",
        "home_url": "https://2b.com.eg",
        "category_url": "https://2b.com.eg/en/computers/laptops.html",
        "product_url": "https://2b.com.eg/en/stores/",
        "store_locator_url": "https://2b.com.eg/en/stores/",
    },
}


async def conduct_browser_research(
    source_id: str,
    output_base: str = "./data/research",
    timeout_ms: int = 30000,
):
    target = RESEARCH_TARGETS.get(source_id)
    if not target:
        raise ValueError(f"Unknown research target: {source_id}")

    output_dir = Path(output_base) / source_id
    output_dir.mkdir(parents=True, exist_ok=True)

    log = logger.bind(source=target["name"], source_id=source_id)
    log.info("research.start", target_dir=str(output_dir))

    network_requests = []
    detected_fields = {
        "source_id": source_id,
        "source_name": target["name"],
        "homepage": {},
        "category_page": {},
        "product_page": {},
        "store_locator": {},
        "summary": {},
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 "
                "EgyptEcommerceResearchBot/1.0"
            ),
        )
        page = await context.new_page()

        # Listen to relevant network requests (JSON / XHR / Fetch)
        def handle_request(req):
            if req.resource_type in ["xhr", "fetch"]:
                network_requests.append({
                    "url": req.url,
                    "method": req.method,
                    "resource_type": req.resource_type,
                    "headers": dict(req.headers),
                })

        page.on("request", handle_request)

        # 1. Homepage Exploration
        log.info("research.homepage.navigating", url=target["home_url"])
        try:
            resp = await page.goto(target["home_url"], timeout=timeout_ms, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            detected_fields["homepage"] = {
                "final_url": page.url,
                "title": await page.title(),
                "status": resp.status if resp else None,
                "has_search": await page.locator("input[type='search'], input[name*='search'], input[name='q']").count() > 0,
            }
            await page.screenshot(path=str(output_dir / "homepage.png"))
            html = await page.content()
            (output_dir / "page.html").write_text(html, encoding="utf-8")
        except Exception as e:
            log.warning("research.homepage.failed", error=str(e))
            detected_fields["homepage"]["error"] = str(e)

        # 2. Category Page Exploration
        if "category_url" in target:
            log.info("research.category.navigating", url=target["category_url"])
            try:
                resp = await page.goto(target["category_url"], timeout=timeout_ms, wait_until="domcontentloaded")
                await asyncio.sleep(2)

                # Card detection
                card_selectors = [
                    "div.product-item", "div.product-card", "li.grid__item",
                    "article.product", "div[data-product-id]", "div.card"
                ]
                card_count = 0
                matching_selector = None
                for sel in card_selectors:
                    c = await page.locator(sel).count()
                    if c > 0:
                        card_count = c
                        matching_selector = sel
                        break

                # Pagination detection
                has_pagination = await page.locator(
                    "ul.pagination, nav.pagination, a[href*='page='], button:has-text('Next')"
                ).count() > 0

                # Product links
                product_links = await page.locator("a[href*='/products/'], a[href*='/product/']").evaluate_all(
                    "elements => elements.slice(0, 10).map(e => e.href)"
                )

                detected_fields["category_page"] = {
                    "final_url": page.url,
                    "title": await page.title(),
                    "product_cards_detected": card_count,
                    "card_selector": matching_selector,
                    "has_pagination": has_pagination,
                    "sample_product_links": list(set(product_links)),
                }
                await page.screenshot(path=str(output_dir / "sample_category.png"))
            except Exception as e:
                log.warning("research.category.failed", error=str(e))
                detected_fields["category_page"]["error"] = str(e)

        # 3. Product Page & JSON-LD Exploration
        if "product_url" in target:
            log.info("research.product.navigating", url=target["product_url"])
            try:
                resp = await page.goto(target["product_url"], timeout=timeout_ms, wait_until="domcontentloaded")
                await asyncio.sleep(2)

                # Extract JSON-LD scripts
                scripts = await page.locator('script[type="application/ld+json"]').all_inner_texts()
                json_ld_parsed = []
                for s in scripts:
                    try:
                        json_ld_parsed.append(json.loads(s))
                    except Exception:
                        pass

                # Check price & availability elements
                has_price = await page.locator("[class*='price'], span[itemprop='price']").count() > 0
                has_sku = await page.locator("[class*='sku'], [itemprop='sku']").count() > 0

                detected_fields["product_page"] = {
                    "final_url": page.url,
                    "title": await page.title(),
                    "json_ld_blocks_found": len(json_ld_parsed),
                    "json_ld_data": json_ld_parsed,
                    "has_price_element": has_price,
                    "has_sku_element": has_sku,
                }
                await page.screenshot(path=str(output_dir / "sample_product.png"))
            except Exception as e:
                log.warning("research.product.failed", error=str(e))
                detected_fields["product_page"]["error"] = str(e)

        # 4. Store Locator Exploration
        if "store_locator_url" in target:
            log.info("research.store_locator.navigating", url=target["store_locator_url"])
            try:
                await page.goto(target["store_locator_url"], timeout=timeout_ms, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                branch_markers = await page.locator("[class*='branch'], [class*='store'], [class*='location']").count()
                detected_fields["store_locator"] = {
                    "url": page.url,
                    "title": await page.title(),
                    "location_markers_detected": branch_markers,
                }
            except Exception as e:
                log.warning("research.store_locator.failed", error=str(e))
                detected_fields["store_locator"]["error"] = str(e)

        await browser.close()

    # Save artifacts
    (output_dir / "detected_fields.json").write_text(
        json.dumps(detected_fields, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    (output_dir / "network.json").write_text(
        json.dumps(network_requests[:100], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    log.info("research.completed", output_directory=str(output_dir))
    return detected_fields


async def main():
    parser = argparse.ArgumentParser(description="Phase 5 Browser Research Script")
    parser.add_argument("--source", type=str, default="tradeline", choices=list(RESEARCH_TARGETS.keys()))
    parser.add_argument("--all", action="store_true", help="Run research on all targets")
    args = parser.parse_args()

    if args.all:
        for s in RESEARCH_TARGETS:
            try:
                await conduct_browser_research(s)
            except Exception as err:
                logger.error("research.target_failed", source=s, error=str(err))
    else:
        await conduct_browser_research(args.source)


if __name__ == "__main__":
    asyncio.run(main())
