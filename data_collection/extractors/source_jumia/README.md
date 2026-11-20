# Jumia Egypt Connector (`jumia`)

- **Implementation Status:** `LIVE VALIDATED` (`LIVE PENDING HUMAN TOS CONFIRMATION` / `LIVE_PENDING_HUMAN_AUTHORIZATION`)
- **Compliance Class:** B (`enabled: true` for controlled research smoke validation at `<=30 RPM`; `/mobapi/` strictly disallowed)
- **Robots Status:** `ROBOTS VERIFIED` (`https://www.jumia.com.eg/robots.txt`, captured `2026-09-28`)
- **ToS Status:** `TOS RETRIEVED AND READ` (`https://www.jumia.com.eg/fragment/contents/sp-terms-of-use/?lang=en`, Section 10.9.9 & 10.9.10 require express written consent for automated scraping; `robots.txt` does NOT override ToS)
- **Surface:** Public category HTML (`article.prd`), PDP JSON-LD (`@graph` `Product`) + delivery promise blocks, and 27 governorate delivery zones (`LocationType.DELIVERY_AREA`).
- **Not Exposed / Blocked:** `stock_quantity` is `NOT_EXPOSED` (`null`); multi-city dynamic shipping table via `/mobapi/` is `BLOCKED` by `robots.txt`.
