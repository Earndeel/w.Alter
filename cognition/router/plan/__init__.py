"""Plan: the owner's subscriptions, a part of Walter Router on its own (owner, 2026-10-22).

    declared.py       the plans he has (one writer: CLI `walter-router plans`, the page form, adopted mail proposals)
    subscriptions.py  quota meters, tokens each plan really carried, cost price of a token per plan
    quota_watch.py    service: re-reads a meter after each agent turn (Walter bus)
    mail.py           billing / subscription mails from the vendors (read-only Gmail, no model)
    watch.py          web research on each plan (SemiAnalysis / Tokenomics, vendors' pages, other measurements)
    news.py           a new benefit or change on a plan he owns -> one Telegram notice each

Run with `walter-router research plans` (also every 48 h cycle); routes read the cost price and the meters.
"""
