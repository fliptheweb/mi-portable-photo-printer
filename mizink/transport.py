"""Bluetooth Classic transport for macOS via IOBluetooth (pyobjc).

The printer speaks the Hannto protocol over RFCOMM channel 1 (Serial Port Profile).
An idle link is dropped by the printer after ~15 s, so `Connection.keep_alive` pings it.

Linux/Windows are not implemented here; on those platforms bind an RFCOMM serial port
(`rfcomm bind` / an outgoing COM port) and swap this module for a pyserial one — the
protocol layer above is identical.
"""

from __future__ import annotations

import time

try:
    from Foundation import NSObject, NSRunLoop, NSDate
    import IOBluetooth
    import objc
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "mizink transport needs pyobjc on macOS: pip install pyobjc-framework-IOBluetooth"
    ) from e

RFCOMM_CHANNEL = 1


def _pump(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.02))


class _Delegate(NSObject):
    def initWithSink_(self, sink):
        self = objc.super(_Delegate, self).init()
        self._sink = sink
        self.open_status = None
        self.closed = False
        return self

    def rfcommChannelData_data_length_(self, ch, data, length):
        self._sink(bytes(data[:length]))

    def rfcommChannelOpenComplete_status_(self, ch, status):
        self.open_status = status

    def rfcommChannelClosed_(self, ch):
        self.closed = True


class Connection:
    """An open RFCOMM channel to the printer. Use as a context manager."""

    def __init__(self, address: str, on_data=None, verbose: bool = False):
        # IOBluetooth wants a dash-separated address.
        self.address = address.replace(":", "-").lower()
        self.verbose = verbose
        self._external_sink = on_data
        self._rx = bytearray()
        self._dev = None
        self._chan = None
        self._delegate = None

    # -- lifecycle -------------------------------------------------------
    def open(self, timeout: float = 25.0) -> "Connection":
        self._dev = IOBluetooth.IOBluetoothDevice.deviceWithAddressString_(self.address)
        rc = self._dev.openConnection()
        if rc != 0:
            raise ConnectionError(
                f"openConnection failed ({rc}); the pairing may be stale. "
                f"Re-pair, e.g. `blueutil --unpair {self.address} && blueutil --pair {self.address}`.")
        self._delegate = _Delegate.alloc().initWithSink_(self._sink)
        rc, self._chan = self._dev.openRFCOMMChannelSync_withChannelID_delegate_(
            None, RFCOMM_CHANNEL, self._delegate)
        if rc != 0 or self._chan is None:
            raise ConnectionError(f"openRFCOMMChannel(1) failed ({rc}); re-pair the printer.")
        _pump(1.0)
        return self

    def close(self) -> None:
        if self._chan is not None:
            self._chan.closeChannel()
            _pump(0.3)
        self._chan = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    @property
    def is_open(self) -> bool:
        return self._chan is not None and self._chan.isOpen() and not (
            self._delegate and self._delegate.closed)

    # -- io --------------------------------------------------------------
    def _sink(self, data: bytes):
        self._rx.extend(data)
        if self._external_sink:
            self._external_sink(data)

    def write(self, frame: bytes) -> None:
        if self._chan is None:
            raise ConnectionError("channel is not open")
        self._chan.writeSync_length_(frame, len(frame))

    def read_available(self) -> bytes:
        data = bytes(self._rx)
        self._rx.clear()
        return data

    def pump(self, seconds: float) -> None:
        _pump(seconds)

    def keep_alive(self, ping, interval: float = 5.0, on_status=None) -> None:
        """Block forever, sending `ping()` every `interval` seconds so the link stays up.

        `ping` should send a status frame and return the decoded reply (or None).
        Ctrl+C to stop. Raises if the channel drops (the caller may reconnect).
        """
        last = 0.0
        while self.is_open:
            self.pump(0.2)
            now = time.time()
            if now - last >= interval:
                last = now
                reply = ping()
                if on_status:
                    on_status(reply)
        raise ConnectionError("link dropped")
