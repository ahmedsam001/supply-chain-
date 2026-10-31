# Carrefour Egypt Connector (`carrefour`)

- **Implementation Status:** `OFFLINE FIXTURE ONLY` (`HUMAN SIGN-OFF REQUIRED`)
- **Compliance Class:** D (`enabled: false` — live collection gated until MAF Terms of Use legal sign-off)
- **Robots Status:** `ROBOTS VERIFIED` (`https://www.carrefouregypt.com/robots.txt`, captured `2026-09-28`)
- **ToS Status:** `TOS NOT RETRIEVED` (`HUMAN SIGN-OFF REQUIRED`)
- **Location Semantics:** 19 governorate-level retail presence records are modeled as `LocationType.PRESENCE` (`branch_name=None`, `raw_location_name` preserved) and are never misrepresented as verified street-level branches. Real HTML branch cards (when parsed) emit `LocationType.BRANCH`.
