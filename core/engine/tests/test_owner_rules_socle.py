"""Stable block (owner 2026-11-26): the universal consignes in the cached socle; a consigne the socle already says is left
out only while the quote that covers it is still there; old packs stop showing consignes that may be stale."""
from walter_engine import engine as E

SOUL = 'Always address the user formally, as "Monsieur". Respond in the user\'s language; by default, French.'
ANSWER = {"title": "Consignes universelles de Monsieur à Walter, en vigueur", "epoch": "2026-11-26T10:00:00+00:00",
          "items": [{"id": "1", "line": "- Vouvoie Monsieur. (24/11/2026)",
                     "covered_by": [{"part": "soul", "quote": 'Always address the user formally, as "Monsieur".'}]},
                    {"id": "2", "line": "- Affiche les adresses complètes. (10/11/2026)", "covered_by": []}]}


def test_the_socle_carries_the_block_at_the_end_of_the_shared_socle():
    assert "owner_rules" in E.SOCLE_SHARED
    order = E.SOCLE_FIRST
    assert order.index("conduct") < order.index("skills_map") < order.index("owner_rules")
    assert order.index("owner_rules") == len(E.SOCLE_SHARED) - 1          # last shared part: before the per-session ones
    assert order.index("owner_rules") < order.index("communication") < order.index("environment")


def test_a_covered_consigne_is_left_out_only_while_its_quote_is_there():
    b = E.socle_block(ANSWER, {"soul": SOUL})
    assert "Vouvoie" not in b["text"] and "adresses complètes" in b["text"] and b["left_out"] == 1
    b2 = E.socle_block(ANSWER, {"soul": "Respond in the user's language."})      # the Soul changed: it comes back
    assert "Vouvoie" in b2["text"] and b2["left_out"] == 0 and b2["sha"] != b["sha"]
    assert E.socle_block({"items": []}, {"soul": SOUL}) is None


PACK = ("<walter-context>\nEn-tête\n## Règles durables de Monsieur\n- ancienne règle\n"
        "## Consignes de Monsieur à Walter liées à ce message (…)\n- consigne du projet\n"
        "## Mémoire pertinente\n- un fait\n</walter-context>\n\nBonjour")


def test_old_packs_lose_the_former_formats_always_and_the_related_ones_when_stale():
    epoch = E._epoch_ms("2026-11-26T10:00:00+00:00")
    fresh = E.past_pack(PACK, epoch + 1, epoch)
    assert "ancienne règle" not in fresh and "consigne du projet" in fresh and "un fait" in fresh
    assert fresh.endswith("Bonjour") and E.PAST_RULES_NOTE in fresh
    stale = E.past_pack(PACK, epoch - 1, epoch)
    assert "consigne du projet" not in stale and "un fait" in stale
    assert E.past_pack(PACK, epoch + 1, epoch) == fresh                        # deterministic: the cache holds
    assert E.past_pack("Bonjour", 1, epoch) == "Bonjour"
