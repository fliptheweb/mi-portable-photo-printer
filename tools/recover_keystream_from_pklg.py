#!/usr/bin/env python3
"""Recover the printer's 928-byte keystream from a Bluetooth capture of it printing a
SOLID WHITE page — an alternative to reading the raw token (see docs/GET_KEY.md, Option C).

    python tools/recover_keystream_from_pklg.py white.pklg > my.keystream
    mizink --keystream my.keystream print photo.jpg

Input: an Apple PacketLogger `.pklg` capture (macOS). The capture may be a direct RFCOMM
channel-1 session or an iAP2-wrapped one (iPhone) — both are handled.

How it works: JSON control frames start with known text (`{"id":`, `{"result":{`), which
crib-drags the keystream at low offsets. That decrypts each file chunk's 4-byte job-id prefix
and the JPEG header, revealing where the flat (all-white) scan begins and its repeating byte
pattern. The pattern is known plaintext for the rest of the file, so every keystream offset
0..927 is recovered by majority vote across the chunks.
"""
import struct, sys, collections

# ------------------------------------------------------------------ pklg ---
def read_pklg(path):
    data = open(path, "rb").read(); off = 0; recs = []
    while off + 4 <= len(data):
        ln = struct.unpack("<I", data[off:off + 4])[0]
        if ln < 9 or off + 4 + ln > len(data): break
        s, us = struct.unpack("<II", data[off + 4:off + 12])
        recs.append((s + us / 1e6, data[off + 12], data[off + 13:off + 4 + ln]))
        off += 4 + ln
    return recs

def l2cap_frames(recs):
    buf = {}; out = []
    for _ts, typ, p in recs:
        if typ not in (2, 3): continue
        d = "TX" if typ == 2 else "RX"
        h = struct.unpack("<H", p[:2])[0]; key = (d, h & 0xfff); pb = (h >> 12) & 3
        if pb in (0, 2): buf[key] = bytearray(p[4:])
        else: buf.setdefault(key, bytearray()).extend(p[4:])
        b = buf[key]
        if len(b) >= 4:
            l2len, cid = struct.unpack("<HH", b[:4])
            if len(b) >= 4 + l2len:
                out.append((d, cid, bytes(b[4:4 + l2len]))); del buf[key]
    return out

def rfcomm_streams(frames):
    """Return {'TX': bytes, 'RX': bytes} of reassembled RFCOMM UIH payloads."""
    cids = set()
    for d, cid, b in frames:
        if cid == 1 and b and b[0] == 0x02 and len(b) >= 8 and int.from_bytes(b[4:6], "little") == 3:
            cids.add(int.from_bytes(b[6:8], "little"))
        if cid == 1 and b and b[0] == 0x03 and len(b) >= 6:
            cids.add(int.from_bytes(b[4:6], "little"))
    out = {"TX": bytearray(), "RX": bytearray()}
    for d, cid, b in frames:
        if cid not in cids or len(b) < 3: continue
        addr, ctrl = b[0], b[1]; ln = b[2]
        hlen = 3 if ln & 1 else 4
        ln = ln >> 1 if hlen == 3 else (ln >> 1) | (b[3] << 7)
        if ctrl & 0xEF != 0xEF or (addr >> 2) == 0: continue
        if ctrl & 0x10: hlen += 1
        out[d] += b[hlen:hlen + ln]
    return bytes(out["TX"]), bytes(out["RX"])

def unwrap_iap2(stream):
    """If the stream is iAP2, return the EA-session app bytes; else return it unchanged."""
    if stream[:2] != b"\xff\x55" and stream[:2] != b"\xff\x5a":
        return stream
    out = bytearray(); i = 0
    while i + 9 <= len(stream):
        if stream[i:i + 2] != b"\xff\x5a": i += 1; continue
        ln = struct.unpack(">H", stream[i + 2:i + 4])[0]
        sess = stream[i + 7]; payload = stream[i + 9:i + ln - 1]
        if sess == 0x0c and len(payload) > 2: out += payload[2:]
        i += ln
    return bytes(out)

# --------------------------------------------------------------- frames ---
def split_frames(buf):
    out = []; i = 0
    while i + 22 <= len(buf):
        if buf[i] != 0x7e: i += 1; continue
        attr = int.from_bytes(buf[i + 18:i + 20], "little"); n = attr & 0x3ff
        if i + 22 + n > len(buf) or buf[i + 21 + n] != 0x7e: i += 1; continue
        out.append(dict(channel=buf[i + 3],
                        pkg_total=int.from_bytes(buf[i + 14:i + 16], "little"),
                        pkg_num=int.from_bytes(buf[i + 16:i + 18], "little"),
                        body=bytes(buf[i + 20:i + 20 + n])))
        i += 22 + n
    return out

# ------------------------------------------------------------- recovery ---
def crib_drag(bodies, key, min_votes=3):
    """Anchor keystream at low offsets by voting known JSON frame prefixes against every body.

    Each candidate prefix is XORed against every frame; a wrong (prefix, frame) pairing yields
    scattered one-off keystream guesses, while the right pairing agrees across the many frames
    that share that prefix. Only offsets whose top guess clears `min_votes` are accepted, so
    ambiguous shared prefixes (e.g. two different `{"result":...` replies) cannot corrupt it.
    """
    # Fixed-layout prefixes the printer/app emit. The idle status reply is byte-stable up to
    # the battery field (~70 bytes), which is enough to read the flat file pattern afterwards.
    PREFIXES = [
        b'{"id":',
        b'{"result":["OK"],"id":',
        b'{"result":{"category":"idle","sub_category":"idle","error":0,"battery":',
        b'{"result":{"category":"idle","sub_category":"init","error":0,"battery":',
        b'{"result":[{"fw_ver":"',
    ]
    votes = collections.defaultdict(collections.Counter)
    for body in bodies:
        for crib in PREFIXES:
            if len(body) >= len(crib):
                for o, c in enumerate(crib):
                    votes[o][body[o] ^ c] += 1
    for o in sorted(votes):
        val, n = votes[o].most_common(1)[0]
        if n >= min_votes and val not in (v for v, _ in votes[o].most_common()[1:] if _ == n):
            key.setdefault(o, val)

def recover_from_frames(file_bodies, ch1_bodies):
    """Core recovery from already-extracted frame bodies. Returns 928 keystream bytes."""
    files = list(file_bodies)
    if len(files) < 4:
        sys.exit("too few file chunks — was a full-size page printed?")

    key = {}
    crib_drag(ch1_bodies, key)
    m = 0
    while m in key: m += 1
    if m < 24:
        sys.exit(f"could not bootstrap keystream (only {m} bytes) — capture a session with more "
                 f"control-frame traffic (status polling, device info)")

    # file position where each chunk's JPEG data begins
    datalens = [len(b) - 4 for b in files]
    starts = []; acc = 0
    for dl in datalens: starts.append(acc); acc += dl

    # A solid-white page's entropy scan is one repeating byte pattern. Find a chunk whose
    # known prefix (offsets 4..m, decryptable with the bootstrapped keystream) is cleanly
    # periodic — that is a flat chunk; read the pattern and its period from it.
    def prefix(b):
        return bytes(b[o] ^ key[o] for o in range(4, min(len(b), m)))
    period = base = known = None
    for i in range(1, len(files) - 1):
        pk = prefix(files[i])
        for p in range(1, 33):
            if len(pk) >= 4 * p and all(pk[k] == pk[k - p] for k in range(p, len(pk))):
                period, base, known = p, starts[i], pk
                break
        if period:
            break
    if not period:
        sys.exit("no flat repeating pattern in any chunk — print a *pure white* page "
                 "(no border or text); see white_pure.png")
    pattern = {(base + i) % period: known[i] for i in range(len(known))}
    if len(pattern) < period:
        sys.exit("could not resolve the full repeating pattern")
    job_id = bytes(files[0][o] ^ key[o] for o in range(4))

    # Vote for each keystream offset, but only from chunks that are consistent with the
    # global pattern over their known prefix (i.e. genuinely flat there); this skips the
    # header chunk, the trailer chunk, and any chunk carrying non-white pixels.
    votes = [collections.Counter() for _ in range(max(len(b) for b in files))]
    for i, b in enumerate(files):
        pk = prefix(b)
        flat = len(pk) >= period and all(
            b[4 + k] ^ pattern[(starts[i] + k) % period] == key[4 + k] for k in range(len(pk)))
        if not flat:
            continue
        for o in range(len(b)):
            pt = job_id[o] if o < 4 else pattern[(starts[i] + (o - 4)) % period]
            votes[o][b[o] ^ pt] += 1
    for o, ctr in enumerate(votes):
        if ctr and o not in key:
            key[o] = ctr.most_common(1)[0][0]

    missing = [o for o in range(928) if o not in key]
    if missing:
        sys.exit(f"incomplete keystream, {len(missing)} offsets missing — capture a full-size "
                 f"pure-white page")
    return bytes(key[o] for o in range(928))


def recover(path):
    recs = read_pklg(path)
    tx, rx = rfcomm_streams(l2cap_frames(recs))
    tx, rx = unwrap_iap2(tx), unwrap_iap2(rx)
    tx_frames, rx_frames = split_frames(tx), split_frames(rx)
    ch1 = [f["body"] for f in tx_frames + rx_frames if f["channel"] == 1]
    files = [f["body"] for f in sorted((f for f in tx_frames if f["channel"] == 2),
                                       key=lambda f: f["pkg_num"])]
    if not files:
        sys.exit("no file-channel frames found — the capture must include printing an image")
    ks = recover_from_frames(files, ch1)
    _validate(ks, ch1)
    return ks


def _validate(ks, ch1):
    """Guard against a silently-wrong keystream. The crib bootstrap can be corrupted by
    captures that are not a clean pure-white print (shared `{"result":` prefixes plus many
    identical status-poll frames let a wrong crib win the per-offset majority). Decrypt the
    JSON control frames with the recovered keystream: on a correct keystream they all parse;
    if too few do, abort instead of emitting a bad keystream."""
    import json
    ok = total = 0
    for b in ch1:
        total += 1
        dec = bytes(b[o] ^ ks[o] for o in range(len(b)))
        try:
            json.loads(dec)
            ok += 1
        except ValueError:
            pass
    if total and ok < max(3, total // 2):
        sys.exit(f"recovered keystream fails self-check ({ok}/{total} control frames decrypt to "
                 f"valid JSON) — the capture is likely not a clean pure-white print; recapture "
                 f"printing white_pure.png with nothing else, or supply the token instead")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: recover_keystream_from_pklg.py white.pklg > my.keystream")
    ks = recover(sys.argv[1])
    out = open(sys.argv[2], "wb") if len(sys.argv) > 2 else sys.stdout.buffer
    out.write(ks)
    sys.stderr.write(f"recovered {len(ks)}-byte keystream\n")
