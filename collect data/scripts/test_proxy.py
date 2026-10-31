#!/usr/bin/env python3
"""
Test Proxy Verification Tool
============================
Tests HTTP/HTTPS connectivity through a configured proxy URL (e.g. Webshare).
Usage:
    python scripts/test_proxy.py
    python scripts/test_proxy.py "http://user:pass@host:port"
"""

import os
import sys
import httpx


def verify_proxy(proxy_url: str | None = None) -> bool:
    target_proxy = proxy_url or os.getenv("PROXY_URL")
    if not target_proxy:
        print("[INFO] No PROXY_URL provided or configured in environment.")
        return False

    test_endpoints = [
        "https://ipv4.webshare.io/",
        "https://api.ipify.org?format=json",
    ]

    print(f"[TEST] Testing proxy connection: {target_proxy}")
    for endpoint in test_endpoints:
        try:
            with httpx.Client(proxy=target_proxy, timeout=10.0) as client:
                resp = client.get(endpoint)
                if resp.status_code == 200:
                    print(f"  ✓ Connected via {endpoint}: {resp.text.strip()}")
                    return True
                else:
                    print(f"  ✗ {endpoint} responded with status: {resp.status_code}")
        except Exception as e:
            print(f"  ✗ {endpoint} failed: {e}")

    return False


if __name__ == "__main__":
    url_arg = sys.argv[1] if len(sys.argv) > 1 else None
    success = verify_proxy(url_arg)
    sys.exit(0 if success else 1)

