"""Send a test message to the configured Discord webhook.

Usage:  python -m bot.ping [config.yaml]
"""
import sys
from pathlib import Path

import requests

from .config import Config


def main(config_path: str = "config.yaml") -> int:
    if not Path(config_path).exists():
        print(f"config not found: {config_path} (copy config.example.yaml)")
        return 1

    cfg = Config.load(config_path)
    webhook = ((cfg.get("discord", default={}) or {}).get("webhook_url") or "").strip()
    if not webhook:
        print("discord.webhook_url is empty in config.yaml")
        return 1

    r = requests.post(
        webhook,
        json={"content": ":white_check_mark: Job search bot online — webhook test"},
        timeout=15,
    )
    if r.status_code >= 400:
        print(f"webhook failed: HTTP {r.status_code} {r.text[:200]}")
        return 1
    print(f"webhook OK: HTTP {r.status_code} — check your Discord channel")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "config.yaml"))
