#!/usr/bin/env python3
"""walter-secret — shell access to the owner's Bitwarden for W.Alter (root only).

  walter-secret get <item id|name> <field>     print the value (used by {{bw:…}} placeholders in terminal commands)
  walter-secret ref <item> <field>             value-free reference for local binding
  walter-secret exec --bind ENV=<reference> -- command [args...]   status only; outputs discarded
  walter-secret search [words…]                metadata only
  walter-secret file <item> [attachment]       decrypt an attachment to /dev/shm, print the path
  walter-secret otp <site> [minutes] [timeout]  wait for the code <site> sent by e-mail / message, print it
  walter-secret grants [ID]                     Walter's authorizations: cards and health (metadata only)
  walter-secret grant access <id> [part]        usable secret of a grant (fresh token for OAuth / subscriptions)
  walter-secret fingerprints [status|build]     value-free index of the vault's secret values (log masking)
"""
import json
import os
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
    if argv and argv[0] == "fingerprints":
        # value-free index of the vault's secret values, used to mask them in logs (fingerprints.py)
        from . import fingerprints
        if len(argv) == 2 and argv[1] == "build":
            print(json.dumps(fingerprints.build(), ensure_ascii=False, indent=1))
            return 0
        if len(argv) == 1 or argv[1:] == ["status"]:
            print(json.dumps(fingerprints.status(), ensure_ascii=False, indent=1))
            return 0
        print("usage: walter-secret fingerprints [status|build]", file=sys.stderr)
        return 2
    if argv and argv[0] in ("grants", "grant"):
        from . import grants
        try:
            if argv[0] == "grants" and len(argv) <= 2:
                out = grants.check(argv[1] if len(argv) == 2 else None)
                print(json.dumps(out, ensure_ascii=False, indent=1))
                return 0 if out["ok"] else 1
            if argv[:2] == ["grant", "access"] and len(argv) in (3, 4):
                print(grants.access(argv[2], argv[3] if len(argv) == 4 else "token"), end="")
                return 0
        except (grants.GrantError, SecretError, OSError, ValueError, KeyError) as exc:
            print(f"walter-secret: {type(exc).__name__}: {exc}"[:300], file=sys.stderr)
            return 1
        print("usage: walter-secret grants [ID] | grant access <id> [part]", file=sys.stderr)
        return 2
    if argv and argv[0] == "store":
        return store_main(argv[1:])
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



def store_main(argv: list[str]) -> int:
    """walter-secret store NAME --kind login|api_key|note [--username U] [--uri URL]… [--field K=V]…
    [--stdin (default) | --from-file PATH | --from-env VAR | --generate [N]] [--update] [--reprompt]
    The value never comes on the command line and is never printed: the answer is the item's id and a reference."""
    import argparse
    import secrets as _s
    import string
    p = argparse.ArgumentParser(prog="walter-secret store")
    p.add_argument("name"); p.add_argument("--kind", choices=["login", "api_key", "note"], required=True)
    p.add_argument("--username"); p.add_argument("--uri", action="append", default=[])
    p.add_argument("--field", action="append", default=[], help="K=V metadata (not secret)")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--stdin", action="store_true"); src.add_argument("--from-file")
    src.add_argument("--from-env"); src.add_argument("--generate", nargs="?", const=32, type=int)
    p.add_argument("--update", action="store_true"); p.add_argument("--reprompt", action="store_true")
    a = p.parse_args(argv)
    if a.generate:
        alphabet = string.ascii_letters + string.digits + "-_.!@#%+="
        value = "".join(_s.choice(alphabet) for _ in range(max(16, a.generate)))
    elif a.from_file:
        value = open(a.from_file).read().rstrip("\n")
    elif a.from_env:
        value = os.environ.get(a.from_env, "")
    else:
        value = sys.stdin.read().rstrip("\n")
    try:
        fields = dict(f.split("=", 1) for f in a.field)
        out = VAULT.store(a.name, a.kind, value, username=a.username, uris=a.uri, fields=fields, update=a.update,
                          reprompt=a.reprompt)
    except (SecretError, ValueError) as e:
        print(f"walter-secret: {e}", file=sys.stderr)
        return 1
    finally:
        value = ""
    out["generated"] = bool(a.generate)
    audit("store", {"name": out["name"], "id": out["id"]}, out["field"], via="cli", kind=a.kind,
          result="updated" if out.get("updated") else "created", generated=bool(a.generate))
    print(json.dumps(out, ensure_ascii=False, indent=1))
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
