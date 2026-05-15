# -*- coding: utf-8 -*-
"""Enable PC server sync against the local Docker service."""

import json
import os


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(ROOT, "config.json")
ENV_PATH = os.path.join(ROOT, ".env")


def read_env(path):
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, "r", encoding="utf-8") as file:
        for raw in file:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def main():
    env = read_env(ENV_PATH)
    token = env.get("SLEEP_AUTH_TOKEN", "")
    port = env.get("SLEEP_server_PORT", "8000")
    if not token:
        raise SystemExit("Missing SLEEP_AUTH_TOKEN. Run scratch/create_server_env_from_local.py first.")

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        cfg = json.load(file)

    cfg["server_sleep_sync"] = {
        "enabled": True,
        "base_url": f"http://127.0.0.1:{port}",
        "auth_token": token,
        "sync_interval_sec": 300,
        "last_sync_at": cfg.get("server_sleep_sync", {}).get("last_sync_at", ""),
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(cfg, file, indent=4, ensure_ascii=False)

    print("Local PC server_sleep_sync enabled for Docker localhost.")


if __name__ == "__main__":
    main()
