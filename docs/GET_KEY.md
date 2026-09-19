# Getting your printer's key

The printer encrypts every message with **RC4**, keyed by its own **12-byte Xiaomi miio
device token** (24 hex characters). The token is unique to your printer and never travels
over Bluetooth, so you have to read it from your Xiaomi account. Any of the routes below work.

> The token is a secret. Don't share it or commit it. `mizink` reads it from `--token`,
> `MIZINK_TOKEN`, or `~/.config/mizink/config.json`.

## Option A — from Home Assistant (easiest if you already use it)

If you added the printer through the **Xiaomi Miot Auto** integration
(`al-one/hass-xiaomi-miot`), the token is cached on disk. This prints the token, MAC and
`did` for every Hannto printer it finds:

```bash
python3 - "$HOME/homeassistant" <<'PY'
import json, sys, glob, os
cfg = sys.argv[1]  # your Home Assistant config dir
def walk(o):
    if isinstance(o, list):
        for x in o: yield from walk(x)
    elif isinstance(o, dict):
        if str(o.get("model", "")).startswith("hannto.printer"):
            yield o
        for v in o.values(): yield from walk(v)
for f in glob.glob(os.path.join(cfg, ".storage/xiaomi_miot/devices-*.json")):
    for d in walk(json.load(open(f))):
        print("model:", d.get("model"), "mac:", d.get("mac"),
              "did:", d.get("did"), "token:", d.get("token"))
PY
```

Replace `$HOME/homeassistant` with your Home Assistant config directory (e.g. `/config` in
the container, or `~/.homeassistant`).

## Option B — from Mi Cloud directly

Use **[Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor)**:
log in with your Xiaomi account, pick the right server (region), and it lists every device with
its `token`. Find the one named "Mi Portable Photo Printer" / model `hannto.printer.basil`.

## Option C — no token, capture a keystream instead

You don't strictly need the raw token: because the cipher restarts for every frame, a single
928-byte **keystream** is an equivalent secret. You can recover it from one Bluetooth capture
of the printer printing a **solid white page** (its compressed data is fully predictable):

1. Print a plain white image from the Mi Home app while capturing Bluetooth
   (macOS: Apple's *PacketLogger*, save a `.pklg`).
2. Recover the keystream:
   ```bash
   python tools/recover_keystream_from_pklg.py white.pklg > my.keystream
   ```
3. Use it: `mizink --keystream my.keystream print photo.jpg`.

This yields the full keystream (enough to print anything); it does **not** reveal the raw
token (RC4 key recovery from a keystream is not feasible), but you don't need it.

## Save it

`~/.config/mizink/config.json`:

```json
{ "address": "F0:13:C1:3F:63:94", "token": "your24hextoken0000000000" }
```
