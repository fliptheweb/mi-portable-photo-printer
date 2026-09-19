"""Payload encryption for the Mi Portable Photo Printer (Hannto `mijia` scheme).

Every frame body is RC4-encrypted with a *fresh* key schedule (KSA) each time, keyed
with the printer's 12-byte Xiaomi device token. Because the schedule restarts for every
frame, the RC4 keystream is identical at the same offset across all frames, so a captured
keystream (see `keystream`) is an equivalent secret to the token itself.
"""

from __future__ import annotations


def rc4_keystream(key: bytes, n: int) -> bytes:
    """The first `n` bytes of the RC4 keystream for `key`."""
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray()
    i = j = 0
    for _ in range(n):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out.append(s[(s[i] + s[j]) & 0xFF])
    return bytes(out)


class Cipher:
    """Encrypt/decrypt frame bodies. Construct from a token or a raw keystream.

    RC4 is a symmetric stream cipher, so `crypt` both encrypts and decrypts.
    """

    def __init__(self, keystream: bytes):
        if len(keystream) < 928:
            raise ValueError("keystream must cover at least 928 bytes (one full file chunk)")
        self._ks = keystream

    @classmethod
    def from_token(cls, token: str | bytes, span: int = 1024) -> "Cipher":
        """Build from the printer's miio token (24 hex chars / 12 bytes)."""
        key = bytes.fromhex(token) if isinstance(token, str) else bytes(token)
        return cls(rc4_keystream(key, span))

    @classmethod
    def from_keystream(cls, keystream: bytes) -> "Cipher":
        return cls(keystream)

    def crypt(self, data: bytes) -> bytes:
        return bytes(b ^ self._ks[i] for i, b in enumerate(data))
