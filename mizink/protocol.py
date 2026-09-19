"""Hannto wire protocol: the 0x7E-delimited frame and the JSON-RPC command layer.

Frame layout (22 + body bytes)::

    off  size  field
    0    1     0x7E  head
    1    1     0x64  version
    2    1     0x00  reserved
    3    1     channel   (1=JSON data, 2=file, 255=auth)
    4    1     interactive (6=request, 7=response)
    5    1     encoding  (2=binary/hex, 3=json)
    6    4     arcMsgSn  u32 LE (0)
    10   4     msgSn     u32 LE (per-side counter)
    14   2     packageTotal u16 LE
    16   2     packageNum   u16 LE (1-based)
    18   2     msgAttribute u16 LE = bodyLen | encType<<10 | 0x2000 if multi-package
    20   N     body (already encrypted when encType != 0)
    20+N 1     checksum = (sum(all bytes, with checksum & tail = 0) - 126) & 0xFF
    21+N 1     0x7E  tail
"""

from __future__ import annotations

import json
from dataclasses import dataclass

HEAD = TAIL = 0x7E
VERSION = 0x64

CH_JSON = 1
CH_FILE = 2
CH_AUTH = 255

REQUEST = 6
RESPONSE = 7

ENC_BINARY = 1
ENC_HEX = 2
ENC_JSON = 3

ENCTYPE_NONE = 0
ENCTYPE_MIJIA = 4  # RC4 with the device token


def build_frame(channel: int, interactive: int, encoding: int, msg_sn: int,
                body: bytes, enctype: int = ENCTYPE_NONE,
                pkg_total: int = 1, pkg_num: int = 1, arc_sn: int = 0) -> bytes:
    """Assemble one wire frame. `body` must already be encrypted if `enctype` says so."""
    n = len(body)
    f = bytearray(22 + n)
    f[0] = HEAD
    f[1] = VERSION
    f[2] = 0
    f[3] = channel
    f[4] = interactive
    f[5] = encoding
    f[6:10] = arc_sn.to_bytes(4, "little")
    f[10:14] = msg_sn.to_bytes(4, "little")
    f[14:16] = pkg_total.to_bytes(2, "little")
    f[16:18] = pkg_num.to_bytes(2, "little")
    attr = n | (enctype << 10) | (0x2000 if pkg_total > 1 else 0)
    f[18:20] = attr.to_bytes(2, "little")
    f[20:20 + n] = body
    f[20 + n] = (sum(f) - 126) & 0xFF
    f[21 + n] = TAIL
    return bytes(f)


@dataclass
class Frame:
    channel: int
    interactive: int
    encoding: int
    msg_sn: int
    pkg_total: int
    pkg_num: int
    enctype: int
    body: bytes
    checksum_ok: bool


def parse_frames(buf: bytes) -> tuple[list[Frame], bytes]:
    """Parse as many complete frames as `buf` holds; return (frames, leftover bytes)."""
    out: list[Frame] = []
    i = 0
    while i + 22 <= len(buf):
        if buf[i] != HEAD:
            i += 1
            continue
        attr = int.from_bytes(buf[i + 18:i + 20], "little")
        n = attr & 0x3FF
        if i + 22 + n > len(buf):
            break
        fr = buf[i:i + 22 + n]
        if fr[-1] != TAIL:
            i += 1
            continue
        out.append(Frame(
            channel=fr[3], interactive=fr[4], encoding=fr[5],
            msg_sn=int.from_bytes(fr[10:14], "little"),
            pkg_total=int.from_bytes(fr[14:16], "little"),
            pkg_num=int.from_bytes(fr[16:18], "little"),
            enctype=(attr >> 10) & 0x7,
            body=bytes(fr[20:20 + n]),
            checksum_ok=fr[20 + n] == ((sum(fr[:20 + n]) - 126) & 0xFF),
        ))
        i += 22 + n
    return out, buf[i:]
