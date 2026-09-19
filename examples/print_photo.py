#!/usr/bin/env python3
"""Minimal example: print an image. Reads address/token from env or ~/.config/mizink/config.json."""
import sys
from mizink import Printer
from mizink.config import resolve_address, resolve_cipher

path = sys.argv[1] if len(sys.argv) > 1 else "photo.jpg"
with Printer(resolve_address(), resolve_cipher()) as p:
    print("status:", p.status())
    job = p.print_image(path, fit="cover",
                        on_progress=lambda i, n: print(f"  {i}/{n}"),
                        on_status=lambda s: print("  ", s.get("category"), s.get("sub_category")))
    print("printed, job", job)
