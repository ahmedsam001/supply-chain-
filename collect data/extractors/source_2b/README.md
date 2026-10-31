# 2B Egypt Connector (`two_b`)

- **Implementation Status:** `LIVE VALIDATED` (`LIVE PENDING HUMAN TOS CONFIRMATION`)
- **Compliance Class:** B (`enabled: true` for controlled research smoke validation at `<=6 RPM`, enforcing `10s` `Crawl-delay`)
- **Robots Status:** `ROBOTS VERIFIED` (`https://2b.com.eg/robots.txt`, captured `2026-09-28`, `Crawl-delay: 10`)
- **ToS Status:** `TOS RETRIEVED AND READ` (`https://2b.com.eg/en/terms-and-conditions`, grants personal shopping license and prohibits commercial use without advance permission)
- **Surface:** Public Magento 2 category HTML (`li.product-item`), PDP HTML (`div.product.attribute.sku`, `.breadcrumbs`, delivery ETA text), and public store locator (`https://2b.com.eg/en/stores` -> 59 `LocationType.BRANCH` records with GPS coordinates).
- **Not Exposed:** `sku` and `gtin` are `NOT_EXPOSED` (`null`) on category cards (SKU is `EXTRACTED` on PDPs); `stock_quantity` and `delivery_fee` are `NOT_EXPOSED` (`null`).
