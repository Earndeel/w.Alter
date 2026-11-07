"""English library page: same layout, no French left (2026-10-14)."""
import re

from walter_router.store import db
from walter_router.interface import library
from walter_router.interface import translate
from walter_router.interface import page

FRENCH_WORDS = {"le", "la", "les", "des", "du", "et", "pour", "par", "avec", "sur", "dans", "une", "ton", "tes", "mes",
                "choix", "pas", "aucun", "prix", "musique", "secours", "abonnement", "tâche", "modèle"}


def test_english_page_has_no_french_left():
    with db.connect() as conn:
        html = page.render(conn, library.rows(conn), library._context(conn))
    en = translate.to_english(html)
    assert '<html lang="en">' in en and 'data-lang="en" class="on"' in en and 'data-lang="fr" class="on"' not in en
    text = re.sub(r"<style.*?</style>|<script.*?</script>", "", en, flags=re.S)
    text = re.sub(r'data-search="[^"]*"', "", text)
    text = re.sub(r'<span class="raw">[^<]*</span>', "", text)   # data quoted as published (sources, e-mails)
    words = set(re.findall(r"[A-Za-zÀ-ÿ']+", re.sub(r"<[^>]+>", " ", text)))
    leftovers = {w for w in words if (re.search(r"[éèêàùçôîâœ]", w) or w.lower() in FRENCH_WORDS) and w != "Français"}
    assert not leftovers, leftovers
    assert not re.search(r">[^<]*\d,\d", text)   # English decimals in visible text


def test_decimal_and_date_conversion():
    assert translate._text("Kie 0,03/0,15 $/M") == "Kie 0.03/0.15 $/M"
    assert translate._text("le 14/10/2026, 15:22 UTC") .endswith("2026-10-14 15:22 UTC")


def test_unreachable_leaderboard_banner_is_translated():
    """The banner only shows while a board is down (Arena collection failing, 2026-11-07): cover it without live data."""
    from walter_router.analysis import catalog, telegram
    labels = [telegram._board_fr(f"{src} {task}") for src in set(catalog.BOARDS.values()) for task in telegram.BOARD_TASKS]
    en = translate._text("Classement inaccessible : " + "; ".join(labels))
    words = set(re.findall(r"[A-Za-zÀ-ÿ']+", en))
    assert not {w for w in words if re.search(r"[éèêàùçôîâœ]", w) or w.lower() in FRENCH_WORDS}, en
