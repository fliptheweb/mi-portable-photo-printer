# mizink

<table>
<tr>
<td width="180" valign="top">
<img src="docs/printer.jpg" alt="Xiaomi Mi Portable Photo Printer" width="180">
</td>
<td valign="top">

Print to the **Xiaomi Mi Portable Photo Printer** over Bluetooth from your Mac —
no Mi Home app, no phone.

- **Full name** — Xiaomi Mi Portable Photo Printer (ZINK)
- **Retail model** — `XMKDDYJ01HM` (firmware `XMKDDYJHT02`)
- **MIoT model** — `hannto.printer.basil`

</td>
</tr>
</table>

```bash
mizink status                 # battery + state
mizink print photo.jpg        # print any image
mizink keepalive --reconnect  # keep the link warm for a service
```

## Why

The printer only pairs with the Mi Home phone app over Bluetooth — no Wi-Fi, no AirPrint. `mizink`
prints to it from a script, so it can be a Home Assistant action or a "print this" button instead
of a phone-only gadget. Protocol and encryption were reverse-engineered from packet captures.

## What it does

- **status / info** — battery, state, firmware.
- **keepalive** — the printer drops an idle link after ~15 s; holds it open, auto-reconnecting.
- **print** — resizes any image to 1040×1560 and sends it.

## Install

```bash
pip install "mizink[macos]"
```

> [!IMPORTANT]
> Tested on macOS only, with one printer (`hannto.printer.basil`). Other platforms need an
> RFCOMM transport shim — see [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Setup

1. Pair the printer with your Mac's Bluetooth once.
2. Get your printer's 12-byte token — three ways in [docs/GET_KEY.md](docs/GET_KEY.md): from Home
   Assistant ([`extract_token_from_ha.py`](tools/extract_token_from_ha.py)), from
   [Mi Cloud](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor), or without a token
   via a white-page keystream ([`recover_keystream_from_pklg.py`](tools/recover_keystream_from_pklg.py)).
3. Pass `--token`/`--address`, set `MIZINK_TOKEN`/`MIZINK_ADDRESS`, or use
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

## Notes

Unofficial, reverse-engineered. Not affiliated with Xiaomi or Hannto; their names are trademarks.
Use at your own risk.

## License

MIT — see [LICENSE](LICENSE).
