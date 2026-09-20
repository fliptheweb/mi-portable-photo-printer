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
    # Return an unconnected Printer; callers use `with _open(a) as p:` which connects
    # via __enter__. (Connecting here too would open ch1 twice and orphan the live one.)
    cipher = resolve_cipher(a.token, a.keystream)
    return Printer(resolve_address(a.address), cipher, verbose=a.verbose)


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
    if a.no_wait and len(a.image) > 1:
        sys.exit("--no-wait only applies to a single image (the printer prints one job at a time)")
    with _open(a) as p:
        st = p.status()
        print(f"printer: {st.get('category')}/{st.get('sub_category')}, battery {st.get('battery')}%")

        def prog(i, n):
            if i % 40 == 0 or i == n:
                print(f"  sending {i}/{n}", flush=True)

        def status(s):
            if "event" not in s:
                print(f"  {s.get('category')}/{s.get('sub_category')}", flush=True)

        if len(a.image) == 1:
            jobs = [p.print_image(a.image[0], copies=a.copies, fit=a.fit,
                                  on_progress=prog, on_status=status, wait=not a.no_wait)]
        else:
            jobs = p.print_many(a.image, copies=a.copies, fit=a.fit,
                                on_progress=prog, on_status=status)
        print(f"done, job_id(s)={jobs}")
        ji = p.last_job_info
        if ji:
            print(f"  last job_state={ji.get('job_state')} copies={ji.get('prt_copies')} "
                  f"print_time={ji.get('print_time')}ms")
        tm = p.last_telemetry
        if tm.get("printed_total") is not None:
            print(f"  lifetime prints: {tm['printed_total']} (finished {tm['finished_total']})")


def cmd_keepalive(a):
    import os

    def paused():
        return bool(a.pause_file) and os.path.exists(a.pause_file)

    while True:
        if paused():
            time.sleep(1)
            continue
        try:
            with _open(a) as p:
                print(f"connected to {p.address}; holding link with retime (Ctrl+C to stop)", flush=True)
                last = None
                while p.conn.is_open and not paused():
                    p.rpc("retime", [])          # reset the ~10-min idle auto-off timer
                    st = p.status()
                    if st.get("battery") != last:
                        last = st.get("battery")
                        print(time.strftime('%H:%M:%S'), st.get("category"),
                              st.get("battery"), "%", flush=True)
                    end = time.time() + a.interval
                    while time.time() < end and not paused():
                        p.conn.pump(0.2)
                if paused():
                    print("pause file present; releasing link", flush=True)
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
    s.add_argument("image", nargs="+", help="one or more image files (printed in sequence)")
    s.add_argument("--copies", type=int, default=1)
    s.add_argument("--fit", choices=["cover", "contain", "stretch"], default="cover")
    s.add_argument("--no-wait", action="store_true",
                   help="single image only: return once sent, don't poll to completion")
    s.set_defaults(fn=cmd_print)

    s = sub.add_parser("keepalive", help="hold the link open and keep the printer awake (retime)")
    _common(s)
    s.add_argument("--interval", type=float, default=30.0)
    s.add_argument("--reconnect", action="store_true", help="auto-reconnect if the link drops")
    s.add_argument("--pause-file", help="release the link while this file exists (lets another "
                                        "process, e.g. `mizink print`, use the single channel)")
    s.set_defaults(fn=cmd_keepalive)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
