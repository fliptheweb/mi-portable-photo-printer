"""High-level driver: connect, query status, print an image."""

from __future__ import annotations

import json
import math
import time

from . import image as _image
from .crypto import Cipher
from .protocol import (
    build_frame, parse_frames, CH_JSON, CH_FILE, REQUEST,
    ENC_JSON, ENC_HEX, ENCTYPE_MIJIA,
)
from .transport import Connection

CHUNK = 924  # JPEG bytes per file frame (4-byte job id is prepended => 928-byte body)


class PrinterError(RuntimeError):
    pass


class Printer:
    """Talks to one Mi Portable Photo Printer.

    cipher: a `mizink.crypto.Cipher` built from your token or a captured keystream.
    """

    def __init__(self, address: str, cipher: Cipher, verbose: bool = False):
        self.address = address
        self.cipher = cipher
        self.verbose = verbose
        self._sn = 0
        self._frames: list = []
        self._buf = bytearray()
        self.conn: Connection | None = None
        self.last_job_info: dict = {}    # job_info result of the most recent print
        self.last_telemetry: dict = {}   # counters from the printer's event.big_data

    # -- connection ------------------------------------------------------
    def connect(self) -> "Printer":
        self.conn = Connection(self.address, verbose=self.verbose)
        self.conn.open()
        return self

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self.connect()

    def __exit__(self, *exc):
        self.close()

    # -- framing ---------------------------------------------------------
    def _drain(self):
        self._buf.extend(self.conn.read_available())
        frames, left = parse_frames(bytes(self._buf))
        self._buf = bytearray(left)
        for f in frames:
            if f.enctype:
                f.body = self.cipher.crypt(f.body)
            self._frames.append(f)
            if self.verbose:
                print("<<", f.channel, f.msg_sn, f.body[:120])

    def _next_sn(self) -> int:
        self._sn += 1
        return self._sn

    def rpc(self, method: str, params, timeout: float = 15.0):
        mid = self._next_sn()
        payload = json.dumps({"id": mid, "method": method, "params": params},
                             separators=(",", ":")).encode()
        self.conn.write(build_frame(CH_JSON, REQUEST, ENC_JSON, mid,
                                    self.cipher.crypt(payload), ENCTYPE_MIJIA))
        end = time.time() + timeout
        while time.time() < end:
            self.conn.pump(0.03)
            self._drain()
            for f in list(self._frames):
                if f.channel == CH_JSON:
                    try:
                        j = json.loads(f.body)
                    except ValueError:
                        continue
                    if j.get("id") == mid:
                        self._frames.remove(f)
                        return j
        raise PrinterError(f"timeout waiting for reply to {method!r}")

    def events(self) -> list:
        """Pop any unsolicited JSON frames (e.g. print-progress events)."""
        self.conn.pump(0.0)
        self._drain()
        out = [f for f in self._frames if f.channel == CH_JSON]
        for f in out:
            self._frames.remove(f)
        decoded = []
        for f in out:
            try:
                decoded.append(json.loads(f.body))
            except ValueError:
                pass
        return decoded

    # -- commands --------------------------------------------------------
    def status(self) -> dict:
        return self.rpc("mixed_status", []).get("result", {})

    def device_info(self) -> dict:
        r = self.rpc("get_prop", ["device_info"]).get("result", [{}])
        return r[0] if isinstance(r, list) and r else {}

    def clean_data(self) -> dict:
        """Reset the data channel before a job. The Mi Home app sends this before every print."""
        return self.rpc("clean_data", {"delay_times": 0})

    def job_info(self, job_id: int) -> dict:
        """Per-job status: job_state, prt_copies, transfer_time, print_time, ..."""
        r = self.rpc("job_info", [job_id]).get("result", [{}])
        return r[0] if isinstance(r, list) and r else {}

    @staticmethod
    def _parse_telemetry(params: dict) -> dict:
        """Flatten a printer `event.big_data` payload into usage counters."""
        total = params.get("total", {}) if isinstance(params, dict) else {}
        return {
            "printed_total": total.get("printed"),
            "finished_total": total.get("finished"),
            "tmd_code": params.get("TMD_code"),
            "did": params.get("did"),
        }

    def keep_alive(self, interval: float = 5.0, on_status=None) -> None:
        """Hold the connection open, pinging status every `interval` s (Ctrl+C to stop)."""
        self.conn.keep_alive(lambda: self.status(), interval=interval, on_status=on_status)

    def _send_file(self, job_id: int, data: bytes, on_progress=None):
        total = math.ceil(len(data) / CHUNK)
        jid = int(job_id).to_bytes(4, "little")
        for i in range(total):
            body = self.cipher.crypt(jid + data[i * CHUNK:(i + 1) * CHUNK])
            self.conn.write(build_frame(CH_FILE, REQUEST, ENC_HEX, self._next_sn(),
                                        body, ENCTYPE_MIJIA, pkg_total=total, pkg_num=i + 1))
            self.conn.pump(0.03)
            if on_progress:
                on_progress(i + 1, total)

    def print_image(self, source, copies: int = 1, fit: str = "cover",
                    on_progress=None, on_status=None, wait: bool = True,
                    timeout: float = 180.0) -> int:
        """Resize `source` to 1040x1560 and print it. Returns the job id.

        If `wait`, block until the printer returns to idle (or `timeout`).
        """
        jpeg = _image.prepare(source, fit=fit)
        self.clean_data()  # the native app resets the data channel before every job
        r = self.rpc("print_job", {"copies": copies, "channel": 64,
                                   "job_type": 0, "file_size": len(jpeg)}, timeout=30)
        res = r.get("result")
        if not isinstance(res, dict) or "job_id" not in res:
            raise PrinterError(f"print_job rejected: {r!r}")
        job_id = res["job_id"]
        self._send_file(job_id, jpeg, on_progress=on_progress)
        ok = self.rpc("confirm_job", [job_id])
        if ok.get("result") != ["OK"]:
            raise PrinterError(f"confirm_job failed: {ok!r}")
        if not wait:
            return job_id
        end = time.time() + timeout
        seen_printing = False
        while time.time() < end:
            self.conn.pump(1.5)
            for ev in self.events():
                if ev.get("method") == "event.big_data":
                    self.last_telemetry = self._parse_telemetry(ev.get("params", {}))
                if on_status:
                    on_status({"event": ev})
            info = self.job_info(job_id)
            if info:
                self.last_job_info = info
            st = self.status()
            if on_status:
                on_status(st)
            cat = st.get("category")
            if cat == "processing":
                seen_printing = True
            # prefer the explicit per-job signal; fall back to the idle-after-printing heuristic
            if info.get("job_state") == "finished" or (cat == "idle" and seen_printing):
                break
        return job_id
