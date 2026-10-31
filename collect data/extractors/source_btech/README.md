# B.TECH Connector (`btech`)

- **Implementation Status:** `BLOCKED`
- **Compliance Class:** C (`DO_NOT_AUTOMATE`, `enabled: false`)
- **Robots Status:** `ROBOTS VERIFIED`
- **ToS Status:** `TOS RETRIEVED AND READ` (`https://btech.com/en/terms-and-conditions` explicitly prohibits automated scraping, bots, and data extraction)
- **Behavior:** Hard-blocked in `config/sources.yaml` and `BTechExtractor`; raises `ComplianceError` before any HTTP client initialization.
