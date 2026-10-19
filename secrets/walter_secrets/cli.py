#!/usr/bin/env python3
"""walter-secret — shell access to the owner's Bitwarden for W.Alter (root only).

  walter-secret get <item id|name> <field>     print the value (used by {{bw:…}} placeholders in terminal commands)
  walter-secret ref <item> <field>             value-free reference for local binding
  walter-secret exec --bind ENV=<reference> -- command [args...]   status only; outputs discarded
  walter-secret search [words…]                metadata only
  walter-secret file <item> [attachment]       decrypt an attachment to /dev/shm, print the path
  walter-secret otp <site> [minutes] [timeout]  wait for the code <site> sent by e-mail / message, print it
"""
import json
import sys
from pathlib import Path

from .vault import VAULT, SecretError, audit  # noqa: E402


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("ref", "exec"):
        return safe_main(argv)
    if argv and argv[0] in ("vault-export", "vault-prune"):
        # Encrypted full-vault backups, used by the nightly offsite backup (walter-memory).
        from pathlib import Path
        from . import vault_react
        if argv[0] == "vault-export" and len(argv) == 2:
            print(f"bitwarden export: {vault_react.export(Path(argv[1]))} items")
            return 0
        if argv[0] == "vault-prune" and len(argv) == 1:
            print(json.dumps(vault_react.prune_local(), ensure_ascii=False))
            return 0
        print("usage: walter-secret vault-export <dest.json.age> | vault-prune", file=sys.stderr)
        return 2
    if not argv or argv[0] not in ("get", "search", "file", "otp"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        if argv[0] == "get" and len(argv) == 3:
            item = VAULT.find(argv[1])
            print(VAULT.value(item["id"], argv[2]), end="")
            audit("get", item, argv[2], via="cli")
        elif argv[0] == "search":
            print(json.dumps(VAULT.search(" ".join(argv[1:])), ensure_ascii=False, indent=1))
        elif argv[0] == "file" and len(argv) in (2, 3):
            item = VAULT.find(argv[1])
            p = VAULT.attachment(item["id"], argv[2] if len(argv) == 3 else None)
            audit("file", item, p.name, via="cli")
            print(p)
        elif argv[0] == "otp" and 2 <= len(argv) <= 4:
            from . import otp
            got = otp.wait(argv[1], since_minutes=float(argv[2]) if len(argv) > 2 else 10,
                           timeout=float(argv[3]) if len(argv) > 3 else 120)
            print(got.pop("code"), end="")
            audit("otp_get", None, "otp", via="cli", channel=got["channel"], sender=got["sender"], received_at=got["at"])
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except SecretError as e:
        print(f"walter-secret: {e}", file=sys.stderr)
        return 1
    return 0



def safe_main(argv: list[str]) -> int:
    import argparse
    from . import service
    from .masking import public_error
    try:
        if argv[0] == "ref":
            if len(argv) != 3:
                raise ValueError("usage: walter-secret ref ITEM FIELD")
            print(service.reference(argv[1], argv[2])["reference"])
            return 0
        parser = argparse.ArgumentParser(prog="walter-secret exec")
        parser.add_argument("--bind", action="append", required=True)
        parser.add_argument("--timeout", type=float, default=60)
        parser.add_argument("--cwd")
        parser.add_argument("command", nargs=argparse.REMAINDER)
        args = parser.parse_args(argv[1:])
        bindings = {}
        for binding in args.bind:
            name, sep, reference = binding.partition("=")
            if not sep or name in bindings:
                raise ValueError("invalid or duplicate binding")
            bindings[name] = reference
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        result = service.execute(command, bindings, timeout=args.timeout, cwd=args.cwd)
        print(json.dumps(result))
        return 0 if result["success"] else 1
    except (SecretError, ValueError, OSError, TypeError, KeyError) as exc:
        print(json.dumps(public_error(exc, operation="local secret execution")), file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
