#!/usr/bin/env python3
"""Minimal contract-aware smoke test. Extend per project."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_url", required=True)
    parser.add_argument("--contract_path", default="")
    args = parser.parse_args()

    health = args.base_url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(health, timeout=5) as resp:
            status = resp.status
            body = resp.read().decode()[:200]
            print(json.dumps({"endpoint": health, "status": status, "body": body}))
            return 0 if 200 <= status < 300 else 1
    except Exception as exc:
        print(json.dumps({"error": str(exc), "endpoint": health}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
