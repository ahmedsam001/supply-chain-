# Compliance Framework

## Overview

Every data source must be classified before any automated extraction begins.
The platform uses a four-class system:

| Class | Symbol | Description |
|-------|--------|-------------|
| **A** | ✅ | **Clearly Permitted.** robots.txt explicitly allows crawling, and ToS permits automated access. Evidence is documented. |
| **B** | 🟡 | **Conditional.** Automated access is technically feasible, but requires specific conditions: identified user-agent, rate limits, restricted paths, or a data partnership agreement. Class B sources may be enabled for controlled prototypes only. |
| **C** | 🔴 | **Prohibited.** robots.txt explicitly disallows scraping, ToS forbids it, or a cease-and-desist has been received. No live requests may be made. Code may exist for reference only. |
| **D** | ❓ | **Unknown.** Compliance status has not been verified. Source is **disabled by default**. Research must be completed before enabling. |

---

## Prohibited Actions (All Sources)

The following are **never permitted** regardless of compliance class:

- Stealth scraping, proxy rotation, CAPTCHA solving
- Browser fingerprint spoofing or header spoofing
- Headless-browser evasion techniques
- Accessing private or undocumented mobile APIs
- Credential guessing or brute-force authentication
- Violating `Disallow` rules in `robots.txt`
- Exceeding stated crawl-delay or rate limits
- Fabricating data that was not observed from the source

---

## Class B Conditions

A Class B source may be enabled for a **controlled prototype** only when ALL of
the following conditions are met:

1. `robots.txt` has been fetched and reviewed; disallowed paths are documented
2. User-agent clearly identifies the platform (e.g., `EgyptEcommerceDataPlatform`)
3. Rate limit is set conservatively (≤ 50% of the limit stated in robots.txt)
4. No disallowed paths are requested
5. Extraction is limited to a small sample (≤ 500 products per run)
6. `compliance_status: B` is set in `config/sources.yaml`
7. `enabled: true` is explicitly set by a human reviewer

---

## Class C Sources — Hard Block

Class C sources have a **hard block** in `extractors/source_btech/extractor.py`:

```python
def source_config(self) -> Source:
    # BLOCKED: compliance class C
    return Source(..., enabled=False, compliance_status=ComplianceStatus.DO_NOT_AUTOMATE)
```

The `ComplianceChecker` will refuse to run extraction for any source with
`compliance_status = C`.

---

## Class D — Offline Fixture Mode

Class D sources may be tested using **offline fixtures** only. This means:

- Parsing a saved HTML/JSON fixture file locally
- No live network requests to the source domain
- Fixture data must be clearly labeled (header comment or `synthetic: true` field)

```bash
python run_extraction.py --source two_b --offline-fixture
```

---

## Compliance Audit

Run a full compliance audit at any time:

```bash
python run_extraction.py --audit
```

This will:
1. Check compliance class for each source
2. Fetch and parse `robots.txt` where accessible
3. Report crawl-delay directives
4. Block Class C sources before any extraction

---

## Verifying a New Source

Before enabling any new source:

1. **Fetch robots.txt manually**:
   ```bash
   curl -A "EgyptEcommerceDataPlatform" https://example.com/robots.txt
   ```
2. **Review ToS** — look for "automated access", "scraping", "crawling" clauses
3. **Document findings** in `config/sources.yaml` under `evidence:` block
4. **Set compliance class** based on findings
5. **Update research_status** to `VERIFIED/PARTIAL` or `VERIFIED/FULL`

---

## Evidence Requirements

For a source to be upgraded from D to B:

- `robots.txt` content documented (even if just "no robots.txt found")
- ToS reviewed and relevant clauses noted
- `evidence_url` set in sources.yaml
- `evidence_captured_on` set (ISO date)
- `evidence_summary` notes the key finding

For a source to be upgraded from B to A:

- All D→B requirements, PLUS:
- Explicit written permission or published API terms permitting automated access
- No significant ToS clause restricting it

---

## Currently Classified Sources

| Source | Class | Status |
|--------|-------|--------|
| Jumia Egypt | 🟡 B | Enabled (controlled prototype) |
| 2B Egypt | 🟡 B | Enabled (controlled prototype) |
| B.TECH | 🔴 C | Hard blocked |
| Carrefour Egypt | ❓ D | Disabled |
| Tradeline | ❓ D | Disabled |
| Dream 2000 | ❓ D | Disabled |
| Raya Shop | ❓ D | Disabled |
| All others (12) | ❓ D | Disabled |
