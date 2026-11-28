#!/usr/bin/env python3
"""Deprecated entry point (2026-10-01): the Raw Vault registry is now core.objects, implemented once in
walter_memory.objects (Walter Memory). This shim keeps the old CLI working:
    rawvault.py put FILE --source S [--link type:id] [--captured ISO]  |  get ID [DEST]  |  search TEXT  |  stats
"""
import os
import sys

args = sys.argv[1:]
if args and args[0] in ("put", "get", "search", "stats"):
    action, rest = args[0], args[1:]
    if action == "get" and len(rest) == 2:
        rest = [rest[0], "--dest", rest[1]]
    os.execvp("walter-memory", ["walter-memory", "objects", action, *rest])
sys.exit(__doc__)
