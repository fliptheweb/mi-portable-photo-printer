# mizink

<table>
<tr>
<td width="180" valign="top">
<img src="docs/printer.jpg" alt="Xiaomi Mi Portable Photo Printer" width="180">
</td>
<td valign="top">

Print to the **Xiaomi Mi Portable Photo Printer** over Bluetooth from your Mac —
no Mi Home app, no phone.

**Supported device**

- **Full name** — Xiaomi Mi Portable Photo Printer (ZINK)
- **Retail model** — `XMKDDYJ01HM` (firmware reports `XMKDDYJHT02`)
- **MIoT model** — `hannto.printer.basil`

</td>
</tr>
</table>

```bash
mizink status                 # battery + state
mizink print photo.jpg        # print any image
mizink keepalive --reconnect  # hold the link open for a home-automation service
```

## Why this exists

The printer has no Wi-Fi, no AirPrint, no USB data port — it only pairs with the Mi Home
phone app over Bluetooth. That makes it impossible to print from a laptop, a server, or a
smart-home setup like Home Assistant. There was no library and no public protocol for this
model, so photos could only come from a phone.

I wanted one thing: **send a picture to this printer from a script**, so it can become a
building block — a Home Assistant action, a photo-booth, a "print this" button — instead of
a phone-only gadget. Getting there meant reverse-engineering the Bluetooth protocol and its
encryption from packet captures. `mizink` is the result, packaged so anyone with the same
printer can reuse it.

## What it does

- **Status** — battery, state, firmware, serial (`mizink status`, `mizink info`).
- **Bluetooth connection with keep-alive** — the printer drops an idle link after ~15 s;
  `mizink keepalive` holds it open (and can auto-reconnect) so a service is always ready.
- **Printing** — resizes any image to the printer's 1040×1560 and sends it
  (`mizink print photo.jpg`).

## Install

Requires Python 3.9+ and, on macOS, Apple's Bluetooth stack via pyobjc.

```bash
pip install mizink                 # + on macOS:
pip install "mizink[macos]"
```

> [!IMPORTANT]
> **Tested on macOS only** (Apple's IOBluetooth stack), against a single printer
> (`hannto.printer.basil`). It has not been run on Linux or Windows, or on other printer
> models. Linux/Windows need a small transport shim over an RFCOMM serial port
> (`rfcomm bind` / an outgoing COM port) — see [docs/PROTOCOL.md](docs/PROTOCOL.md); the
> protocol layer above the transport is identical, so a port should be straightforward.
> Reports and PRs for other platforms and printers are welcome.

## Setup

1. **Pair** the printer with your Mac's Bluetooth once, like any device.
2. **Get your printer's key.** Encryption is tied to *your* device, so you need its 12-byte
   miio token. Three ways — full guide in [docs/GET_KEY.md](docs/GET_KEY.md):
   - **Home Assistant** (if you use `xiaomi_miot`): run
     [`tools/extract_token_from_ha.py`](tools/extract_token_from_ha.py) to read the token from
     its device cache.
   - **Mi Cloud**: log in with
     [Xiaomi-cloud-tokens-extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor)
     and copy the printer's `token`.
   - **No token** — capture one print of a pure-white page and recover the equivalent keystream
     with [`tools/recover_keystream_from_pklg.py`](tools/recover_keystream_from_pklg.py)
     (use `--keystream` instead of `--token`).
3. **Configure** — pass `--address`/`--token`, set `MIZINK_ADDRESS`/`MIZINK_TOKEN`, or drop
   a `~/.config/mizink/config.json` (see `config.example.json`).

```bash
mizink --address F0:13:C1:3F:63:94 --token <your-token> status
mizink print birthday.jpg --fit cover
```

## Use as a library

```python
from mizink import Printer, Cipher

with Printer("F0:13:C1:3F:63:94", Cipher.from_token("<token>")) as p:
    print(p.status())
    p.print_image("photo.jpg", fit="cover")
```

## Home Assistant

Wrap `mizink print` in a [`shell_command`](https://www.home-assistant.io/integrations/shell_command/)
or a command-line script and trigger it from an automation. Run `mizink keepalive --reconnect`
as a background service so the link is warm when an automation fires. Example in
[examples/](examples/).

## Safety & scope

- Your token is a per-device secret. Do not commit it; `config.json` and `*.keystream` are
  git-ignored.
- Reverse-engineered from packet captures. Not affiliated with or endorsed by Xiaomi or
  Hannto. "Xiaomi", "Mijia" and "Hannto" are trademarks of their owners. Use at your own risk.

## License

MIT — see [LICENSE](LICENSE).
