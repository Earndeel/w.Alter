"""Long owner messages: the end, a negation and a constraint are never lost (the old cut was message[:1500])."""
import random

import pytest

from walter_context import preflight
from walter_context.longtext import represent
from walter_context.preflight import Request

FILLER = ("Le contexte du projet avance normalement, les équipes se coordonnent et le planning reste globalement "
          "stable cette semaine. ")


def filler(n_chars: int, seed=1) -> str:
    out, i = [], 0
    while sum(map(len, out)) < n_chars:
        out.append(FILLER.replace("projet", f"projet{i}"))
        i += 1
    return "".join(out)[:n_chars].rsplit(" ", 1)[0] + ". "


@pytest.mark.parametrize("size", [3000, 8000, 20000])
@pytest.mark.parametrize("where", ["end", "middle", "negation_end", "negation_middle"])
def test_the_decisive_instruction_survives(size, where):
    key = {"end": "Envoie le récapitulatif au comptable avant vendredi.",
           "middle": "Il faut absolument garder la version signée du contrat.",
           "negation_end": "Surtout ne supprime rien du dossier clients.",
           "negation_middle": "N'envoie jamais ce document à Paul."}[where]
    half = filler(size // 2)
    text = (half + key + " " + half) if "middle" in where else (half * 2 + key)
    assert len(text) > 1500
    r = represent(text)
    assert r.truncated and r.length == len(text)
    assert key in r.text                                   # word for word, not paraphrased
    assert f"{len(text)} caractères" in r.text             # the full length is said
    assert "caractères omis, offsets" in r.text            # the gaps are said
    assert len(r.text) < 3200                              # still bounded


def test_offsets_point_into_the_original_text():
    text = filler(6000) + "Ne touche pas au fichier prod.env. " + filler(6000)
    r = represent(text)
    sig = [p for p in r.parts if p["kind"] == "signal" and "négation" in p["flags"]]
    assert any("Ne touche pas" in text[p["a"]:p["b"]] for p in sig)


def test_short_messages_are_unchanged_and_whitespace_collapsed():
    r = represent("  Bonjour   \n tout le monde ")
    assert r.text == "Bonjour tout le monde" and not r.truncated


def test_english_negation_and_amount_and_date_are_kept():
    text = filler(5000) + "Do not exceed 4 500 € for the venue. " + filler(3000) + "The deadline is 2026-12-03. " + filler(5000)
    r = represent(text)
    assert "Do not exceed 4 500 €" in r.text and "2026-12-03" in r.text


def test_the_preflight_state_uses_it_and_the_switch_restores_the_old_cut(monkeypatch):
    text = filler(9000) + "Et surtout ne lance pas le déploiement avant mon feu vert."
    st = preflight._state(Request("t", text))["new_message"]
    assert "ne lance pas le déploiement" in st and st.startswith("[message long")
    monkeypatch.setattr("walter_context.config.longtext_settings",
                        lambda path=None: {"enabled": False, "inline_chars": 1500, "head_chars": 500, "tail_chars": 600,
                                           "signal_chars": 1200, "signal_sentence_chars": 280})
    old = preflight._state(Request("t", text))["new_message"]
    assert len(old) == 1500 and "déploiement" not in old


def test_a_single_huge_sentence_without_punctuation_is_bounded_and_keeps_the_end():
    text = "mot " * 5000 + "ne jamais écraser la base"
    r = represent(text)
    assert r.text.rstrip().endswith("ne jamais écraser la base") and len(r.text) < 3200
