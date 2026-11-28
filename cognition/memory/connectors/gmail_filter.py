"""Gmail quality gate (decision 2026-10-02): only human correspondence enters PG.

Gmail stays the archive for everything else (notifications, newsletters, promotions, receipts) and is queried live.
An e-mail is kept when:
  - Monsieur sent it, or it belongs to a thread where he wrote;
  - the sender is someone Monsieur has written to (to/cc of any sent e-mail);
  - the sender uses a personal mailbox (gmail, free, icloud…) and is not an automated / relayed address.
OTP / verification-code mails are never kept, whatever the sender.
"""
from __future__ import annotations

import re

ME = "lucas.jouvencon@gmail.com"
PERSONAL = re.compile(r"@(gmail\.com|googlemail\.com|free\.fr|icloud\.com|me\.com|mac\.com|hotmail\.[a-z.]+|outlook\.[a-z.]+|"
                      r"live\.[a-z.]+|msn\.com|yahoo\.[a-z.]+|orange\.fr|wanadoo\.fr|sfr\.fr|neuf\.fr|laposte\.net|"
                      r"proton\.me|protonmail\.com|pm\.me|gmx\.[a-z]+|aol\.com)$")
AUTOMATED = re.compile(r"(no-?reply|do-?not-?reply|notification|newsletter|mailer|bounce|_at_|privaterelay)")
RELAYED_NAME = re.compile(r"(?i)( on instagram| via |instagram|facebook|linkedin)")
OTP = re.compile(r"(?i)(code de (vérification|connexion|confirmation|sécurité)|verification code|one[- ]time (pass|code)|"
                 r"\bOTP\b|security code|login code|sign[- ]in code|is your .{0,30}code|votre code|mot de passe à usage unique)")


def addr_of(from_header: str | None) -> str:
    m = re.search(r"([^<\s\"]+@[^>\s\"]+)", from_header or "")
    return m.group(1).lower() if m else ""


def keep(*, labels: list[str], from_header: str | None, subject: str | None, snippet: str | None,
         human_thread: bool, correspondents: set[str]) -> bool:
    if OTP.search(f"{subject or ''} {(snippet or '')[:300]}") and "SENT" not in labels:
        return False
    if "SENT" in labels or human_thread:
        return True
    a = addr_of(from_header)
    if not a:
        return False
    if a in correspondents:
        return True
    return bool(PERSONAL.search(a)) and not AUTOMATED.search(a) and not RELAYED_NAME.search(from_header or "")
