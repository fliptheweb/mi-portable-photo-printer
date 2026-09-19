#!/usr/bin/env python3
"""Print the miio token(s) of any Hannto printer cached by the Home Assistant
`xiaomi_miot` (al-one/hass-xiaomi-miot) integration.

    python tools/extract_token_from_ha.py [HA_CONFIG_DIR]

HA_CONFIG_DIR is your Home Assistant config directory (default: ~/homeassistant);
e.g. /config inside the container, or ~/.homeassistant. The token it prints is a
per-device secret — keep it private; feed it to mizink via --token / MIZINK_TOKEN /
your config file (see docs/GET_KEY.md).
"""
import glob
import json
import os
import sys


def walk(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from walk(x)
    elif isinstance(obj, dict):
        if str(obj.get("model", "")).startswith("hannto.printer"):
            yield obj
        for v in obj.values():
            yield from walk(v)


def main():
    cfg = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/homeassistant")
    files = glob.glob(os.path.join(cfg, ".storage/xiaomi_miot/devices-*.json"))
    if not files:
        sys.exit(f"no xiaomi_miot device cache under {cfg!r} — is the integration set up, "
                 f"and is this the right HA config dir?")
    found = False
    for f in files:
        try:
            data = json.load(open(f))
        except (OSError, ValueError):
            continue
        for d in walk(data):
            found = True
            print(f"name : {d.get('name')}")
            print(f"model: {d.get('model')}")
            print(f"mac  : {d.get('mac')}")
            print(f"did  : {d.get('did')}")
            print(f"token: {d.get('token')}")
            print("-")
    if not found:
        sys.exit("no Hannto printer found in the cache (open it once in HA so it gets cached)")


if __name__ == "__main__":
    main()
