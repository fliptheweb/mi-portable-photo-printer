"""Command-line interface: `mizink status | info | print | keepalive`."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .config import resolve_address, resolve_cipher
from .printer import Printer


def _common(ap):
    ap.add_argument("--address", help="printer MAC (else MIZINK_ADDRESS / config file)")
    ap.add_argument("--token", help="printer miio token, 24 hex chars (see docs/GET_KEY.md)")
    ap.add_argument("--keystream", help="path to a recovered keystream file (alternative to --token)")
    ap.add_argument("-v", "--verbose", action="store_true")


def _open(a) -> Printer:
    cipher = resolve_cipher(a.token, a.keystream)
    p = Printer(resolve_address(a.address), cipher, verbose=a.verbose)
    return p.connect()


def cmd_status(a):
    with _open(a) as p:
        st = p.status()
        print(f"category   : {st.get('category')} / {st.get('sub_category')}")
        print(f"battery    : {st.get('battery')}%")
        print(f"error      : {st.get('error')}")


def cmd_info(a):
    with _open(a) as p:
        info = p.device_info()
        for k in ("fw_ver", "hw_ver", "mac", "sn_pcba", "sku", "did"):
            if k in info:
                print(f"{k:9}: {info[k]}")


def cmd_print(a):
    with _open(a) as p:
        st = p.status()
        print(f"printer: {st.get('category')}/{st.get('sub_category')}, battery {st.get('battery')}%")

        def prog(i, n):
            if i % 40 == 0 or i == n:
                print(f"  sending {i}/{n}", flush=True)

        def status(s):
            if "event" not in s:
                print(f"  {s.get('category')}/{s.get('sub_category')}", flush=True)

        job = p.print_image(a.image, copies=a.copies, fit=a.fit,
                            on_progress=prog, on_status=status, wait=not a.no_wait)
        print(f"done, job_id={job}")
        ji = p.last_job_info
        if ji:
            print(f"  job_state={ji.get('job_state')} copies={ji.get('prt_copies')} "
                  f"print_time={ji.get('print_time')}ms")
        tm = p.last_telemetry
        if tm.get("printed_total") is not None:
            print(f"  lifetime prints: {tm['printed_total']} (finished {tm['finished_total']})")


def cmd_keepalive(a):
    while True:
        try:
            with _open(a) as p:
                print(f"connected to {p.address}; holding link (Ctrl+C to stop)")
                p.keep_alive(interval=a.interval,
                             on_status=lambda s: print(time.strftime('%H:%M:%S'),
                                                       s.get("category"), s.get("battery"), "%", flush=True))
        except KeyboardInterrupt:
            print("\nstopped")
            return
        except Exception as e:  # link dropped / open failed -> retry
            if not a.reconnect:
                raise
            print(f"link issue ({e}); reconnecting in {a.interval}s", flush=True)
            time.sleep(a.interval)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mizink",
                                 description="Drive the Mi Portable Photo Printer (ZINK) over Bluetooth without Mi Home.")
    ap.add_argument("--version", action="version", version=f"mizink {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="print battery + state"); _common(s); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("info", help="firmware / serial / mac"); _common(s); s.set_defaults(fn=cmd_info)

    s = sub.add_parser("print", help="print an image file")
    _common(s)
    s.add_argument("image")
    s.add_argument("--copies", type=int, default=1)
    s.add_argument("--fit", choices=["cover", "contain", "stretch"], default="cover")
    s.add_argument("--no-wait", action="store_true", help="return once sent, don't poll to completion")
    s.set_defaults(fn=cmd_print)

    s = sub.add_parser("keepalive", help="hold the Bluetooth link open (pings status)")
    _common(s)
    s.add_argument("--interval", type=float, default=5.0)
    s.add_argument("--reconnect", action="store_true", help="auto-reconnect if the link drops")
    s.set_defaults(fn=cmd_keepalive)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
