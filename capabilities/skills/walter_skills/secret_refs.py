"""No secret value in a skill: every Bitwarden value found in skill text becomes its placeholder {{bw:<item>:<field>}}.

The placeholder is Walter Secrets' own convention: Hermes resolves it in tool arguments right before execution,
`walter-secret get <item> <field>` resolves it in a terminal, and the model only ever sees the placeholder
(Monsieur, 2026-11-01: « ça doit être le rôle du curateur de faire cela »).

Detection is value-free and cheap (Walter Secrets' fingerprint index); the vault itself is read only when a file
really contains a vault value. A value the index knows but the vault no longer has falls back to the generic mask
«secret:vault», so a secret never stays in clear. Never prints or logs a value.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

MASK = "«secret:vault»"
MIN_LEN = 8
_TEXT_SUFFIXES = {"", ".md", ".txt", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".env", ".cfg",
                  ".ini", ".html", ".css", ".sql", ".plist", ".command", ".jsonc", ".mjs", ".cjs"}
_IGNORED = {".git", ".cache", "__pycache__", ".pytest_cache", "node_modules"}


def _secrets():
    try:
        import walter_secrets  # noqa: F401
    except ImportError:
        root = subprocess.run(["walter", "path", "secrets"], capture_output=True, text=True).stdout.strip()
        sys.path.insert(0, root or "/walter/secrets")
    from walter_secrets import fingerprints, vault
    return fingerprints, vault


def available() -> bool:
    """The value-free index is there: detection works (the vault is needed only to name the item)."""
    try:
        return bool(_secrets()[0].status().get("ok"))
    except Exception:
        return False


def has_vault_value(text: str) -> bool:
    fp, _ = _secrets()
    return fp.scrub(text) != text


def _item_ref(item: dict, items: list[dict]) -> str:
    """The item's name when it is unique and placeholder-safe (readable), else its id."""
    name = item.get("name") or ""
    same = sum(1 for i in items if (i.get("name") or "").lower() == name.lower())
    return name if name and same == 1 and not re.search(r"[:{}\n]", name) else item["id"]


CONFIG_MAX = 12   # a VISIBLE text field shorter than this is configuration (e.g. an AWS region), not a secret
_ignored: set[str] = set()


def _is_config(field_type, value: str) -> bool:
    return field_type == 0 and len(value.strip()) < CONFIG_MAX


def placeholders() -> dict[str, str]:
    """value → {{bw:<item>:<field>}} for every value Walter Secrets fingerprints (same fields as its index), except
    short visible fields (configuration such as a region), which stay readable in skills."""
    fp, vault = _secrets()
    items = vault.VAULT.items()
    out: dict[str, str] = {}
    _ignored.clear()
    for i in items:
        for f in i.get("fields") or []:
            v = f.get("value")
            if isinstance(v, str) and _is_config(f.get("type"), v):
                _ignored.add(v.strip())
    for i in items:
        ref = _item_ref(i, items)
        login, card, ident = i.get("login") or {}, i.get("card") or {}, i.get("identity") or {}
        cand = [("password", login.get("password")), ("totp", login.get("totp")),
                ("number", card.get("number")), ("code", card.get("code")),
                ("ssn", ident.get("ssn")), ("passportNumber", ident.get("passportNumber")),
                ("licenseNumber", ident.get("licenseNumber"))]
        cand += [(f"field:{f.get('name')}", f.get("value")) for f in i.get("fields") or [] if f.get("type") in (0, 1)]
        for field, v in cand:
            if isinstance(v, str) and fp.worth_indexing(v) and v.strip() not in _ignored:
                out.setdefault(v.strip(), "{{bw:%s:%s}}" % (ref, field))
    return out


def rewrite(text: str, ph: dict[str, str]) -> tuple[str, int]:
    """Replace every vault value (whole token, longest first) by its placeholder; leftovers known to the index
    become the generic mask. Returns (text, number of replacements)."""
    n = 0
    for v in sorted((v for v in ph if len(v) >= MIN_LEN and v in text), key=len, reverse=True):
        rx = re.compile(r"(?<![A-Za-z0-9_\-])" + re.escape(v) + r"(?![A-Za-z0-9_\-])")
        text, k = rx.subn(lambda m, p=ph[v]: p, text)
        n += k
    masked = _mask_rest(text)
    if masked != text:
        fp, _ = _secrets()
        n += masked.count(fp.MASK) - text.count(fp.MASK)
        text = masked
    return text, n


def _mask_rest(text: str) -> str:
    """Walter Secrets' generic mask for any vault value still left (same tokenisation), configuration values kept."""
    fp, _ = _secrets()
    m = fp._matcher
    if not m._load():
        return text

    def token(tok: str) -> str:
        if len(tok) < fp.MIN_LEN or tok in _ignored:
            return tok
        if m._hit(tok):
            return fp.MASK
        for sep in fp._SPLIT:
            if sep in tok:
                return sep.join(token(part) for part in tok.split(sep))
        return tok
    return fp._TOKEN.sub(lambda x: token(x.group()), text)


def to_placeholders(text: str) -> tuple[str, int]:
    """For the write door: the text with its vault values turned into placeholders (vault read only if needed)."""
    if not text or not has_vault_value(text):
        return text, 0
    return rewrite(text, placeholders())


def text_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (set(p.parts) & _IGNORED) and p.name != ".walter.json" \
                and p.suffix.lower() in _TEXT_SUFFIXES and p.stat().st_size <= 3_000_000:
            yield p


def scan(roots: list[Path]) -> list[Path]:
    """Files that contain a vault value (value-free check)."""
    out = []
    for root in roots:
        for p in text_files(root) if root.exists() else []:
            try:
                if has_vault_value(p.read_text()):
                    out.append(p)
            except UnicodeDecodeError:
                continue
    return out


def fix(paths: list[Path], ph: dict[str, str] | None = None) -> dict:
    """Rewrite the given files in place. Returns counts only (never values)."""
    ph = ph if ph is not None else placeholders()
    files, refs, masked = 0, 0, 0
    fp, _ = _secrets()
    for p in paths:
        t = p.read_text()
        new, n = rewrite(t, ph)
        if new != t:
            p.write_text(new)
            files += 1
            m = new.count(fp.MASK) - t.count(fp.MASK)
            refs, masked = refs + n - m, masked + m
    return {"files": files, "placeholders": refs, "generic_masks": masked}
