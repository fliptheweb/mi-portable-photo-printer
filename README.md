# mizink

<img src="docs/printer.jpg" alt="Xiaomi Mi Portable Photo Printer" width="170" align="right">

Print to the **Xiaomi Mi Portable Photo Printer** over Bluetooth from your Mac -
no Mi Home app, no phone.

- **Full name** - Xiaomi Mi Portable Photo Printer (ZINK)
- **Retail model** - `XMKDDYJ01HM` (firmware `XMKDDYJHT02`)
- **MIoT model** - `hannto.printer.basil`

## Why

The printer only pairs with the Mi Home phone app over Bluetooth - no Wi-Fi, no AirPrint. `mizink`
prints to it from a script, so it can be a Home Assistant action or a "print this" button instead
of a phone-only gadget. [Protocol](docs/PROTOCOL.md) and encryption were reverse-engineered from Bluetooth packet captures, live on-device probing, the official Xiaomi firmware image (unpacking + partial disassembly), and the Mi Home Android plugin. No vendor SDK or documentation.

## What it does

```bash
mizink status                 # battery, state, firmware
mizink print photo.jpg        # resize any image to 1040×1560 and print
mizink print a.jpg b.jpg      # print several in sequence (queued one at a time)
mizink keepalive --reconnect  # hold the idle-dropping link open for a service
```

## Idle shutdown

The printer powers itself off after ~10 minutes of inactivity, and reports the time remaining
before shutdown in its status. Reading status alone does **not** stop it - only the `retime`
method resets the timer. `mizink keepalive --reconnect` sends `retime` on an interval, so a
long-running service (e.g. a Home Assistant print button) keeps the printer awake and reachable.

## Print lifecycle

<img src="docs/lifecycle.svg" alt="Print lifecycle: init → smart_sheet (calibration paper) → decoding → pre_heat → load_paper → printing → idle" width="100%">

## Install

```bash
git clone https://github.com/fliptheweb/mi-portable-photo-printer.git
cd mi-portable-photo-printer
pip install ".[macos]"
```

> [!IMPORTANT]
> Tested on macOS only, with one printer (`hannto.printer.basil`). Other platforms need an
> RFCOMM transport shim - see [Protocol](docs/PROTOCOL.md).

## Setup

The printer encrypts everything with a key that is unique to *your* device - its 12-byte Xiaomi
miio token. You need yours; there is no shared or default key.

1. Get your printer's token - three ways (full guide in [docs/GET_KEY.md](docs/GET_KEY.md)):
   - from **Home Assistant** - [`extract_token_from_ha.py`](tools/extract_token_from_ha.py) (if you have already added your Xiaomi account to Home Assistant)
   - from **Mi Cloud** - [Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor)
   - **without a token** - recover a keystream from a white-page capture with [`recover_keystream_from_pklg.py`](tools/recover_keystream_from_pklg.py)
2. Pair the printer with your Mac's Bluetooth once.
3. Configure - pass `--token`/`--address`, set `MIZINK_TOKEN`/`MIZINK_ADDRESS`, or use
   `~/.config/mizink/config.json` (see `config.example.json`).

```bash
mizink --address F0:13:C1:3F:63:94 --token <token> status
mizink print birthday.jpg
```

## Library

```python
from mizink import Printer, Cipher

with Printer("F0:13:C1:3F:63:94", Cipher.from_token("<token>")) as p:
    p.print_image("photo.jpg")
```

## Home Assistant

Call `mizink print` from a [`shell_command`](https://www.home-assistant.io/integrations/shell_command/),
and run `mizink keepalive --reconnect` as a background service. See [examples/](examples/).

## Other models

Got the **Xiaomi Portable Photo Printer Pro** instead? It speaks the same frame format but a
different cipher (AES-ECB after a Diffie-Hellman handshake) - use
[tuat-yate/xiaomi-photo-printer](https://github.com/tuat-yate/xiaomi-photo-printer), which also
helped confirm the frame format here.

## Notes

Unofficial, reverse-engineered. Not affiliated with Xiaomi or Hannto; their names are trademarks.
Use at your own risk.

## License

MIT - see [LICENSE](LICENSE).
