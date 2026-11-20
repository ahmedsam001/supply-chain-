# Compliance Review Queue & Authorization Audit (2026-09-28)

> **Critical Rule**: `robots.txt` is a technical crawl-control directive and **does NOT override website Terms of Service (ToS)**. Even when `robots.txt` permits a path, automated scraping or commercial use remains subject to the site's legal Terms of Use and requires human legal sign-off.

---

## 1. Separated Compliance Evidence States

Every source in `config/sources.yaml` is audited across five distinct compliance dimensions:

1. **`ROBOTS VERIFIED`**: Live `robots.txt` retrieved via read-only HTTP GET, status code and SHA-256 recorded, `Allow`/`Disallow` and `Crawl-delay` directives parsed.
2. **`TOS RETRIEVED AND READ`**: Public Terms of Use / Terms & Conditions HTML retrieved, stored in `data/raw/<source>/`, and inspected for automated collection / scraping / commercial-use clauses.
3. **`TOS NOT RETRIEVED`**: Public Terms of Use have not yet been downloaded or legally reviewed; source remains disabled (`enabled: false`).
4. **`ASSUMED / UNVERIFIED`**: Neither `robots.txt` nor ToS could be conclusively verified (e.g., edge challenge, timeout, or unresearched surface); source remains disabled (`enabled: false`).
5. **`HUMAN SIGN-OFF REQUIRED`**: Human legal/compliance officer must review the retrieved ToS or obtain written partner authorization before production or commercial collection.

---

## 2. Live Prototype Sources — `LIVE PENDING HUMAN TOS CONFIRMATION`

### 2.1 Jumia Egypt (`jumia`)
- **Authorization Status**: `LIVE PENDING HUMAN TOS CONFIRMATION` (`LIVE_PENDING_HUMAN_AUTHORIZATION`)
- **Robots State**: `ROBOTS VERIFIED` (`https://www.jumia.com.eg/robots.txt`, captured `2026-09-28`, HTTP 200, SHA-256 `c79601426009...`). Allows public category/PDP HTML under 200 RPM; explicitly disallows `/mobapi/`.
- **ToS State**: `TOS RETRIEVED AND READ`
  - **Wrapper URL**: `https://www.jumia.com.eg/terms-of-use/?internal=footer` (`data/raw/jumia/terms_2026-09-28.html`)
  - **Embedded Terms Content URL**: `https://www.jumia.com.eg/fragment/contents/sp-terms-of-use/?lang=en` (`data/raw/jumia/terms_fragment_2026-09-28.html`, captured `2026-09-28`)
  - **Exact Findings**:
    - **Section 10.9.9**: *"You must not: conduct any systematic or automated data collection activities (including without limitation scraping, data mining, data extraction and data harvesting) on or in relation to our website without our express written consent"*
    - **Section 10.9.10**: *"access or otherwise interact with our website using any robot, spider or other automated means, except for the purpose of search engine indexing"*
    - **Section 10.9.12**: *"violate the directives set out in the robots.txt file for our website"*
- **Compliance Conclusion**: Although `robots.txt` permits public catalog/PDP requests under 200 RPM, Jumia's Terms of Use prohibit systematic or automated data collection without express written consent. `robots.txt` does **not** override the Terms of Use. Live smoke runs (`limit=6`, `<=30 RPM`, strictly excluding `/mobapi/`) are executed solely for technical validation; ongoing or commercial collection requires written consent from Jumia.
- [ ] **Human Legal Sign-Off Required (`jumia`)**: Obtain express written consent from Jumia Egypt or restrict `jumia` to partner feed / offline fixtures.

### 2.2 2B Egypt (`two_b`)
- **Authorization Status**: `LIVE PENDING HUMAN TOS CONFIRMATION`
- **Robots State**: `ROBOTS VERIFIED` (`https://2b.com.eg/robots.txt`, captured `2026-09-28`, HTTP 200, SHA-256 `66a3a3196e46...`). Sets `Crawl-delay: 10` (6 RPM) for `User-agent: *`, allows public category/PDP HTML and `/en/stores`, disallows `/*?*` and `/*/catalogsearch/`.
- **ToS State**: `TOS RETRIEVED AND READ`
  - **Terms URL**: `https://2b.com.eg/en/terms-and-conditions` (`data/raw/two_b/terms_2026-09-28.html`, captured `2026-09-28`)
  - **Exact Findings**:
    - Under **"Use of the Site"**: *"We grant you a non-transferable and revocable license to use the website under the specified terms and conditions. The purpose of this license is to shop for personal items sold on the site. Use for commercial purposes or on behalf of any third party, except as explicitly permitted by us in advance, is prohibited."*
    - The page contains no explicit anti-bot/anti-scraping clause beyond the commercial-use restriction and `robots.txt` (`Crawl-delay: 10`).
- **Compliance Conclusion**: Non-commercial academic/prototype testing at `<=6 RPM` (`10s` delay) complies with `robots.txt`, but any commercial supply-chain intelligence use requires advance permission from 2B Egypt.
- [ ] **Human Legal Sign-Off Required (`two_b`)**: Confirm non-commercial academic scope or obtain commercial data permission from 2B Egypt.

---

## 3. Complete 21-Source Compliance Matrix

| Source ID | Name | Class | `enabled` | Robots State | ToS State | Authorization Status | Human Sign-Off |
|-----------|------|-------|-----------|--------------|-----------|----------------------|----------------|
| `jumia` | Jumia Egypt | `B` | `true` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `LIVE PENDING HUMAN TOS CONFIRMATION` | `[ ]` Required |
| `carrefour` | Carrefour Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `btech` | B.TECH | `C` | `false` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `BLOCKED (PROHIBITED BY TOS)` | `[ ]` Required |
| `two_b` | 2B Egypt | `B` | `true` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `LIVE PENDING HUMAN TOS CONFIRMATION` | `[ ]` Required |
| `tradeline` | Tradeline Stores | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `dream2000` | Dream 2000 | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `raya` | Raya Shop | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `noon` | Noon Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `spinneys` | Spinneys Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `samsung_eg` | Samsung Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `orange_eg` | Orange Egypt | `D` | `false` | `ASSUMED / UNVERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `vodafone_eg` | Vodafone Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `we_eg` | WE / Telecom Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `eand_eg` | e& Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `metro` | Metro Markets | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `hyperone` | Hyper One | `D` | `false` | `ASSUMED / UNVERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `elaraby` | Elaraby Group | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `amazon_eg` | Amazon Egypt | `C` | `false` | `ROBOTS VERIFIED` | `TOS RETRIEVED AND READ` | `BLOCKED (PROHIBITED BY TOS)` | `[ ]` Required |
| `talabat` | Talabat Mart / Talabat Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `instashop` | InstaShop Egypt | `D` | `false` | `ROBOTS VERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |
| `lulu` | Lulu Hypermarket Egypt | `D` | `false` | `ASSUMED / UNVERIFIED` | `TOS NOT RETRIEVED` | `HUMAN SIGN-OFF REQUIRED` | `[ ]` Required |

---

## 4. Source-by-Source Evidence Details & Sign-Off Checklists

### `jumia` — Jumia Egypt (`jumia.com.eg`)
- **Compliance Class**: `B` (`enabled: true`)
- **Implementation Status**: `PROTOTYPE`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.jumia.com.eg/robots.txt`)
- **ToS Status**: `TOS RETRIEVED AND READ` (`https://www.jumia.com.eg/terms-of-use/?internal=footer`)
- **Authorization Status**: `LIVE PENDING HUMAN TOS CONFIRMATION`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: ROBOTS VERIFIED (2026-09-28, HTTP 200, 9825 bytes, allows catalog/PDP under 200 RPM, disallows /mobapi/). TOS RETRIEVED AND READ (2026-09-28, /fragment/contents/sp-terms-of-use/?lang=en): Section 10.9.9 prohibits systematic or automated data collection (scraping, data mining, data extraction, data harvesting) without express written consent; Section 10.9.10 prohibits robots/spiders except search engine indexing. robots.txt does NOT override ToS. Status: LIVE PENDING HUMAN TOS CONFIRMATION.
- [ ] **Human Sign-Off (`jumia`)**: `pending_human_tos_confirmation` — LIVE PENDING HUMAN TOS CONFIRMATION (Class B prototype; requires written consent for production)

### `carrefour` — Carrefour Egypt (`carrefouregypt.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `PROTOTYPE`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.carrefouregypt.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 1521 bytes): Disallow /cart, /*checkout. Public store pages exist, but MAF ToS requires human legal sign-off before live automation.
- [ ] **Human Sign-Off (`carrefour`)**: `pending_human_review` — Candidate for Class B (pending ToS review; enabled remains false)

### `btech` — B.TECH (`btech.com`)
- **Compliance Class**: `C` (`enabled: false`)
- **Implementation Status**: `BLOCKED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://btech.com/en/terms-and-conditions`)
- **ToS Status**: `TOS RETRIEVED AND READ`
- **Authorization Status**: `BLOCKED (PROHIBITED BY TOS)`
- **Captured On**: `2026-09-27`
- **Evidence Summary**: B.TECH Terms & Conditions explicitly prohibit automated scraping, bots, and data extraction. Hard-blocked in config and code.
- [ ] **Human Sign-Off (`btech`)**: `compliance_gate_blocked` — Class C (DO NOT AUTOMATE - Blocked)

### `two_b` — 2B Egypt (`2b.com.eg`)
- **Compliance Class**: `B` (`enabled: true`)
- **Implementation Status**: `PROTOTYPE`
- **Robots Status**: `ROBOTS VERIFIED` (`https://2b.com.eg/robots.txt`)
- **ToS Status**: `TOS RETRIEVED AND READ` (`https://2b.com.eg/en/terms-and-conditions`)
- **Authorization Status**: `LIVE PENDING HUMAN TOS CONFIRMATION`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: ROBOTS VERIFIED (2026-09-28, HTTP 200, 2600 bytes, Crawl-delay: 10s, allows catalog/PDP and /en/stores). TOS RETRIEVED AND READ (2026-09-28, https://2b.com.eg/en/terms-and-conditions): 'Use of the Site' grants a personal shopping license and prohibits commercial use without advance permission; contains no explicit anti-scraping clause for non-commercial research. Status: LIVE PENDING HUMAN TOS CONFIRMATION.
- [ ] **Human Sign-Off (`two_b`)**: `pending_human_tos_confirmation` — LIVE PENDING HUMAN TOS CONFIRMATION (Class B prototype at <=6 RPM; requires human sign-off for commercial use)

### `tradeline` — Tradeline Stores (`tradelinestores.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `PROTOTYPE`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.tradelinestores.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 3644 bytes): standard Shopify robots.txt (Allow: /, Disallow: /admin, /cart, /checkout). Public /products.json and store locator exist; awaiting human sign-off.
- [ ] **Human Sign-Off (`tradeline`)**: `pending_human_review` — Candidate for Class B (proposal only; enabled remains false)

### `dream2000` — Dream 2000 (`dream2000.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `PROTOTYPE`
- **Robots Status**: `ROBOTS VERIFIED` (`https://dream2000.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 3620 bytes): standard Shopify robots.txt (Allow: /). Public /products.json exposes EAN-13 GTINs; awaiting human ToS sign-off.
- [ ] **Human Sign-Off (`dream2000`)**: `pending_human_review` — Candidate for Class B (proposal only; enabled remains false)

### `raya` — Raya Shop (`rayashop.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `PROTOTYPE`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.rayashop.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 1396 bytes): Disallow /ar/checkout/, /en/checkout/, /customer/. Terms of Use not yet cleared by human reviewer; offline synthetic fixture only.
- [ ] **Human Sign-Off (`raya`)**: `pending_human_review` — Candidate for Class B (proposal only; enabled remains false)

### `noon` — Noon Egypt (`noon.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.noon.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 269 bytes): Disallow /_svc/, /_vs/. Protected by anti-bot WAF and restrictive ToS.
- [ ] **Human Sign-Off (`noon`)**: `pending_human_review` — Needs permission / official partner API (enabled remains false)

### `spinneys` — Spinneys Egypt (`spinneys-egypt.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://spinneys-egypt.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 144 bytes): User-agent: * Disallow: (empty). Grocery category candidate, pending human ToS review.
- [ ] **Human Sign-Off (`spinneys`)**: `pending_human_review` — Candidate for Class B (proposal only; enabled remains false)

### `samsung_eg` — Samsung Egypt (`samsung.com/eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.samsung.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 10085 bytes): Disallow search/account/checkout paths. Global Samsung ToS restricts automated scraping without written permission.
- [ ] **Human Sign-Off (`samsung_eg`)**: `pending_human_review` — Needs permission (enabled remains false)

### `orange_eg` — Orange Egypt (`shop.orange.eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ASSUMED / UNVERIFIED` (`https://www.orange.eg/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only check returned HTTP 404 (no robots.txt at root). Telecom device shop requires explicit legal review.
- [ ] **Human Sign-Off (`orange_eg`)**: `pending_human_review` — Still deferred / needs permission (enabled remains false)

### `vodafone_eg` — Vodafone Egypt (`web.vodafone.com.eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://web.vodafone.com.eg/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 452 bytes): User-agent: * Allow: /, blocks AI bots (OAI-SearchBot, GPTBot). Requires telecom legal review.
- [ ] **Human Sign-Off (`vodafone_eg`)**: `pending_human_review` — Needs permission (enabled remains false)

### `we_eg` — WE / Telecom Egypt (`te.eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://te.eg/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 23 bytes): User-Agent: * Disallow:. Limited e-commerce catalog; deferred.
- [ ] **Human Sign-Off (`we_eg`)**: `pending_human_review` — Still deferred (enabled remains false)

### `eand_eg` — e& Egypt (`eand.com.eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.eand.com.eg/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 4122 bytes UTF-16LE): Disallow /StaticFiles/css, portal paths. Telecom portal; deferred.
- [ ] **Human Sign-Off (`eand_eg`)**: `pending_human_review` — Still deferred / needs permission (enabled remains false)

### `metro` — Metro Markets (`metro-markets.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.metro-markets.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 24 bytes): User-agent: * Disallow:. Supermarket catalog structure and ToS require human review.
- [ ] **Human Sign-Off (`metro`)**: `pending_human_review` — Still deferred (enabled remains false)

### `hyperone` — Hyper One (`hyperone.com.eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ASSUMED / UNVERIFIED` (`https://www.hyperone.com.eg/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check returned HTTP 403 Forbidden (WAF blocks automated HTTP clients). Do not evade WAF.
- [ ] **Human Sign-Off (`hyperone`)**: `pending_human_review` — Needs permission / blocked by WAF (enabled remains false)

### `elaraby` — Elaraby Group (`elarabygroup.com`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.elarabygroup.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 1000 bytes): explicitly lists Googlebot/Googlebot-image; general bot policy requires human ToS review.
- [ ] **Human Sign-Off (`elaraby`)**: `pending_human_review` — Candidate for Class B after ToS review (enabled remains false)

### `amazon_eg` — Amazon Egypt (`amazon.eg`)
- **Compliance Class**: `C` (`enabled: false`)
- **Implementation Status**: `BLOCKED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.amazon.eg/gp/help/customer/display.html?nodeId=201909000`)
- **ToS Status**: `TOS RETRIEVED AND READ`
- **Authorization Status**: `BLOCKED (PROHIBITED BY TOS)`
- **Captured On**: `2026-09-27`
- **Evidence Summary**: Amazon Conditions of Use strictly prohibit data mining, robots, or similar data gathering and extraction tools. Only official Amazon PA-API 5.0 with approved credentials is acceptable.
- [ ] **Human Sign-Off (`amazon_eg`)**: `compliance_gate_blocked` — Class C (DO NOT AUTOMATE without official API credentials - Blocked)

### `talabat` — Talabat Mart / Talabat Egypt (`talabat.com/egypt`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://www.talabat.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 126 bytes): Sitemap links only. Quick-commerce inventory requires location session/API; requires partner permission.
- [ ] **Human Sign-Off (`talabat`)**: `pending_human_review` — Needs permission (enabled remains false)

### `instashop` — InstaShop Egypt (`instashop.com/en-eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ROBOTS VERIFIED` (`https://instashop.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check (HTTP 200, 2518 bytes): User-agent: * Allow: /, Disallow: /my-orders/*. Quick-commerce platform requires ToS review.
- [ ] **Human Sign-Off (`instashop`)**: `pending_human_review` — Needs permission (enabled remains false)

### `lulu` — Lulu Hypermarket Egypt (`luluhypermarket.com/en-eg`)
- **Compliance Class**: `D` (`enabled: false`)
- **Implementation Status**: `DEFERRED`
- **Robots Status**: `ASSUMED / UNVERIFIED` (`https://www.luluhypermarket.com/robots.txt`)
- **ToS Status**: `TOS NOT RETRIEVED`
- **Authorization Status**: `HUMAN SIGN-OFF REQUIRED`
- **Captured On**: `2026-09-28`
- **Evidence Summary**: Read-only robots.txt check timed out (ReadTimeout / edge protection). Deferred until human verification.
- [ ] **Human Sign-Off (`lulu`)**: `pending_human_review` — Still deferred (enabled remains false)
