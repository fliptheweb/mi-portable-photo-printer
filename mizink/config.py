"""Resolve the printer address and secret (token or keystream) from CLI/env/config file.

Precedence: explicit argument > environment variable > config file. The config file is
`$MIZINK_CONFIG` or `~/.config/mizink/config.json`::

    {"address": "F0:13:C1:3F:63:94", "token": "0123...."}

`token` is your printer's 12-byte miio token (24 hex chars); alternatively `keystream_file`
points to a file of >=928 raw keystream bytes recovered from a capture. Never commit either.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .crypto import Cipher

ENV_ADDRESS = "MIZINK_ADDRESS"
ENV_TOKEN = "MIZINK_TOKEN"
ENV_KEYSTREAM = "MIZINK_KEYSTREAM"


def _config_path() -> Path:
    return Path(os.environ.get("MIZINK_CONFIG",
                               Path.home() / ".config" / "mizink" / "config.json"))


def _load_file() -> dict:
    p = _config_path()
    if p.is_file():
        try:
            return json.loads(p.read_text())
        except ValueError:
            return {}
    return {}


def resolve_address(cli_address: str | None = None) -> str:
    addr = cli_address or os.environ.get(ENV_ADDRESS) or _load_file().get("address")
    if not addr:
        raise SystemExit("no printer address: pass --address, set MIZINK_ADDRESS, or add it to the config file")
    return addr


def resolve_cipher(cli_token: str | None = None, cli_keystream: str | None = None) -> Cipher:
    fileconf = _load_file()
    token = cli_token or os.environ.get(ENV_TOKEN) or fileconf.get("token")
    if token:
        return Cipher.from_token(token)
    ks_path = cli_keystream or os.environ.get(ENV_KEYSTREAM) or fileconf.get("keystream_file")
    if ks_path:
        data = Path(ks_path).expanduser().read_bytes()
        return Cipher.from_keystream(data)
    raise SystemExit(
        "no key material: provide --token (see docs/GET_KEY.md), MIZINK_TOKEN, "
        "or a --keystream file recovered from a capture")
